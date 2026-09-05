"""Filesystem-Aware Mutation History & Single-Step / Short-History Undo Manager.

Captures state snapshots of both SQLite database tables AND filesystem folder/journal
manifests before executing mutations. Guarantees that database undo operations and
filesystem person folder states remain strictly synchronized.
"""

from __future__ import annotations

import copy
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ... import config, db
from ...data_root.errors import UndoFilesystemConflictError
from ...data_root.manager import DataRootManager
from ...model import _model_from_connection, run_family_audits, validate_model
from ...services import errors

# Stack of previous snapshots for undo capability
_MUTATION_STACK: List[Dict[str, Any]] = []
MAX_HISTORY_DEPTH = 10


def _file_hash(path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    if not path.exists() or not path.is_file():
        return ""
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def record_pre_mutation_snapshot(
    description: str,
    filesystem_manifest: Optional[Dict[str, Any]] = None,
) -> None:
    """Capture complete snapshot of database state and initial filesystem manifest before a mutation."""
    connection = db.get_connection()
    try:
        # Extract full DB table data
        people = [dict(r) for r in connection.execute("SELECT * FROM people").fetchall()]
        aliases = [dict(r) for r in connection.execute("SELECT * FROM aliases").fetchall()]
        parent_child = [dict(r) for r in connection.execute("SELECT * FROM parent_child").fetchall()]
        marriages = [dict(r) for r in connection.execute("SELECT * FROM marriages").fetchall()]
        sibling_groups = [dict(r) for r in connection.execute("SELECT * FROM sibling_groups").fetchall()]
        sibling_members = [dict(r) for r in connection.execute("SELECT * FROM sibling_group_members").fetchall()]
        general_rels = [dict(r) for r in connection.execute("SELECT * FROM general_relationships").fetchall()]
        person_groups = [dict(r) for r in connection.execute("SELECT * FROM person_groups").fetchall()]
        groups = [dict(r) for r in connection.execute("SELECT * FROM groups").fetchall()]

        # Capture active filesystem manifest of person folders
        fs_manifest = filesystem_manifest or {"moves": [], "created_paths": [], "hashes": {}}
        
        snapshot = {
            "description": description,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "people": people,
            "aliases": aliases,
            "parent_child": parent_child,
            "marriages": marriages,
            "sibling_groups": sibling_groups,
            "sibling_group_members": sibling_members,
            "general_relationships": general_rels,
            "person_groups": person_groups,
            "groups": groups,
            "filesystem": fs_manifest,
        }

        evicted = None
        if len(_MUTATION_STACK) >= MAX_HISTORY_DEPTH:
            evicted = _MUTATION_STACK.pop(0)
        snapshot["_evicted_prior"] = evicted
        _MUTATION_STACK.append(snapshot)
    finally:
        connection.close()


def update_latest_filesystem_manifest(manifest_update: Dict[str, Any]) -> None:
    """Attach or update filesystem manifest metadata on the most recent snapshot."""
    if not _MUTATION_STACK:
        return
    snapshot = _MUTATION_STACK[-1]
    fs = snapshot.get("filesystem", {})
    if "created_paths" in manifest_update:
        created = fs.get("created_paths", [])
        for p in manifest_update["created_paths"]:
            if str(p) not in created:
                created.append(str(p))
            # Record initial file hash
            p_obj = Path(p)
            if p_obj.exists() and p_obj.is_file():
                fs.setdefault("hashes", {})[str(p)] = _file_hash(p_obj)
        fs["created_paths"] = created

    if "moves" in manifest_update:
        moves = fs.get("moves", [])
        moves.extend(manifest_update["moves"])
        fs["moves"] = moves

    snapshot["filesystem"] = fs


def can_undo() -> bool:
    return len(_MUTATION_STACK) > 0


def get_last_mutation_description() -> Optional[str]:
    if not _MUTATION_STACK:
        return None
    return _MUTATION_STACK[-1]["description"]


def pop_latest_snapshot() -> Optional[Dict[str, Any]]:
    """Remove and return the most recent snapshot without applying it (e.g. on operation failure/rollback).

    Restores any prior snapshot evicted by capacity if this popped snapshot caused eviction.
    """
    if _MUTATION_STACK:
        popped = _MUTATION_STACK.pop()
        evicted = popped.pop("_evicted_prior", None)
        if evicted is not None:
            _MUTATION_STACK.insert(0, evicted)
        return popped
    return None


def undo_last_mutation(force_archive_conflicts: bool = False) -> Dict[str, Any]:
    """Restore database AND filesystem to snapshot state prior to the last mutation.

    If a newly created person folder/journal was modified externally after creation,
    blocks deletion and raises `UndoFilesystemConflictError` unless `force_archive_conflicts`
    is explicitly set to True.
    """
    if not _MUTATION_STACK:
        raise errors.InvalidOperationError("No mutations available to undo.", code="NO_UNDO_AVAILABLE")

    snapshot = _MUTATION_STACK[-1]
    description = snapshot["description"]
    fs = snapshot.get("filesystem", {})

    created_paths = [Path(p) for p in fs.get("created_paths", [])]
    recorded_hashes = fs.get("hashes", {})

    # 1. Conflict Check: Verify if created files/journals were modified externally
    conflicted_paths: List[str] = []
    for cp in created_paths:
        if cp.exists() and cp.is_file():
            current_hash = _file_hash(cp)
            initial_hash = recorded_hashes.get(str(cp))
            if initial_hash and current_hash != initial_hash:
                conflicted_paths.append(str(cp))

    if conflicted_paths and not force_archive_conflicts:
        raise UndoFilesystemConflictError(
            message=f"Cannot undo '{description}': Person journal was modified externally after the mutation.",
            detail={
                "code": "UNDO_FILESYSTEM_CONFLICT",
                "affected_paths": conflicted_paths,
                "description": description,
                "suggested_actions": ["cancel", "archive_and_undo"],
            },
        )

    # Pop snapshot now that pre-checks passed
    _MUTATION_STACK.pop()

    # 2. Revert Filesystem Actions
    try:
        # Move back archived/relocated folders
        moves = fs.get("moves", [])
        for m in reversed(moves):
            src = Path(m["to"])
            dst = Path(m["from"])
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
                shutil.move(str(src), str(dst))

        # Handle created paths (delete unedited, or archive if force_archive_conflicts)
        for cp in reversed(created_paths):
            if cp.exists():
                if str(cp) in conflicted_paths and force_archive_conflicts:
                    # Archive modified journal instead of deleting
                    people_dir = DataRootManager.get_people_dir()
                    archive_dest = people_dir / "_archived" / f"conflict_{cp.parent.name}_{uuid_hex()}"
                    archive_dest.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(cp.parent), str(archive_dest))
                else:
                    parent_dir = cp.parent
                    if cp.is_file():
                        cp.unlink()
                    elif cp.is_dir():
                        shutil.rmtree(cp)
                    # Clean up empty parent person folder if empty
                    if parent_dir.exists() and parent_dir.is_dir() and not list(parent_dir.iterdir()):
                        parent_dir.rmdir()

    except Exception as exc:
        # Re-push snapshot if filesystem restoration failed
        _MUTATION_STACK.append(snapshot)
        raise errors.ValidationError(
            f"Failed filesystem rollback during undo: {exc}", code="UNDO_FS_FAILED"
        ) from exc

    # 3. Revert Database Tables Transactionally
    connection = db.get_connection()
    try:
        connection.execute("BEGIN")

        # Clear current tables
        connection.execute("DELETE FROM general_relationships")
        connection.execute("DELETE FROM sibling_group_members")
        connection.execute("DELETE FROM sibling_groups")
        connection.execute("DELETE FROM marriages")
        connection.execute("DELETE FROM parent_child")
        connection.execute("DELETE FROM aliases")
        connection.execute("DELETE FROM person_groups")
        connection.execute("DELETE FROM people")

        # Restore people
        for p in snapshot["people"]:
            cols = list(p.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO people ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(p.values()))

        # Restore aliases
        for a in snapshot["aliases"]:
            cols = list(a.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO aliases ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(a.values()))

        # Restore parent_child
        for pc in snapshot["parent_child"]:
            cols = list(pc.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO parent_child ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(pc.values()))

        # Restore marriages
        for m in snapshot["marriages"]:
            cols = list(m.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO marriages ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(m.values()))

        # Restore sibling_groups
        for sg in snapshot["sibling_groups"]:
            cols = list(sg.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO sibling_groups ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(sg.values()))

        # Restore sibling_group_members
        for sgm in snapshot["sibling_group_members"]:
            cols = list(sgm.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO sibling_group_members ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(sgm.values()))

        # Restore general_relationships
        for gr in snapshot["general_relationships"]:
            cols = list(gr.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO general_relationships ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(gr.values()))

        # Restore person_groups
        for pg in snapshot["person_groups"]:
            cols = list(pg.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO person_groups ({', '.join(cols)}) VALUES ({placeholders})"
            connection.execute(sql, list(pg.values()))

        # Validate restored model
        restored_model = _model_from_connection(connection)
        validate_model(restored_model)
        run_family_audits(restored_model)

        connection.commit()
        return {
            "ok": True,
            "undone_description": description,
            "can_undo_more": can_undo(),
        }
    except Exception as exc:
        connection.rollback()
        # Re-insert the snapshot if DB undo failed
        _MUTATION_STACK.append(snapshot)
        raise errors.ValidationError(f"Failed to undo database state: {exc}", code="UNDO_FAILED") from exc
    finally:
        connection.close()


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
