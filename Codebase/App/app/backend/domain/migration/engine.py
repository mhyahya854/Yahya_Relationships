"""Deterministic, failure-atomic migration to Phase 11 Canonical Data Foundation.

Transforms legacy family.db (schema 1/2) and legacy People layout into:
- Single authoritative SQLite database: Database/relationships.db (schema 3)
- Canonical person IDs: normalized_full_name--INITIALS##
- Canonical top-level filesystem: People/Me, People/Family, People/Friends
- Folder template: facts-and-about.md, journal(personal thoughts).md, subdirectories
- Exact byte-for-byte journal prose migration
- Deterministic ID mapping preserved in identifier_aliases table
- Pre-migration safety backup in Backups/Safety/Pre-Upgrade/
- Non-destructive rollback on any failure
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ... import config, db
from ...data_root.errors import DataRootError, DataRootInvalidError, DataRootReadOnlyError
from ...data_root.manager import DataRootManager
from ...data_root.validation import audit_data_root
from ..backups import BackupCategory, SafetyReason, create_backup, verify_backup
from ..backups.paths import remove_tree
from ..canonical.ids import generate_canonical_person_id, is_valid_canonical_person_id
from ..canonical.template import (
    canonical_facts_filename,
    canonical_journal_filename,
    generate_facts_and_about,
    initialize_person_folder,
)
from ..family import engine as family_engine
from ..maintenance import MaintenanceLockContext


_MIGRATION_FAILPOINT: str | None = None


def _check_failpoint(name: str) -> None:
    if _MIGRATION_FAILPOINT == name:
        raise RuntimeError(f"Injected canonical migration failure at: {name}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_operation_marker(path: Path, payload: Dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _recover_interrupted_migration(active_root: Path) -> None:
    """Remove only artifacts named by Mosaic's own Phase-11 marker."""
    marker = active_root / ".migration_incomplete.json"
    if not marker.is_file():
        return
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataRootInvalidError(
            "Migration recovery marker is unreadable; refusing automatic cleanup.",
            detail={"code": "MIGRATION_MARKER_INVALID", "path": str(marker)},
        ) from exc
    if payload.get("kind") != "mosaic-phase11-migration":
        raise DataRootInvalidError(
            "Migration recovery marker is not recognized; refusing automatic cleanup.",
            detail={"code": "MIGRATION_MARKER_INVALID", "path": str(marker)},
        )
    target_db = active_root / "Database" / "relationships.db"
    target_people = active_root / "People"
    if payload.get("target_db_created") and target_db.is_file():
        target_db.unlink()
    if payload.get("target_people_created") and target_people.is_dir():
        remove_tree(target_people)
    for path in active_root.glob(".migration_staging_*"):
        if path.is_dir() and path.resolve().parent == active_root:
            remove_tree(path)
    marker.unlink()


def detect_migration_status(root: Optional[Path] = None) -> Dict[str, Any]:
    """Detect whether the Data Root is legacy, partially migrated, or already canonical."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    canonical_db = active_root / "Database" / "relationships.db"
    legacy_db = active_root / "Database" / "Main" / "family.db"
    if not legacy_db.exists():
        legacy_db = active_root / "family.db"

    has_canonical = canonical_db.is_file()
    has_legacy = legacy_db.is_file()

    people_top = active_root / "People"
    has_canonical_people = people_top.is_dir() and (
        (people_top / "Me").is_dir() or (people_top / "Family").is_dir()
    )

    if has_canonical:
        try:
            con = sqlite3.connect(f"{canonical_db.as_uri()}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            try:
                ver = db.get_current_schema_version(con)
                p_count = con.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            finally:
                con.close()
            if ver >= 3 and has_canonical_people:
                return {
                    "status": "already_canonical",
                    "can_migrate": False,
                    "schema_version": ver,
                    "people_count": p_count,
                    "db_path": str(canonical_db),
                }
        except Exception as exc:
            return {
                "status": "corrupt_canonical",
                "can_migrate": False,
                "error": str(exc),
                "db_path": str(canonical_db),
            }

    if DataRootManager.is_canonical_root(active_root):
        return {
            "status": "canonical_repair_required",
            "can_migrate": False,
            "error": "Canonical root is missing a valid Database/relationships.db.",
            "db_path": str(canonical_db),
        }

    if has_legacy:
        try:
            con = sqlite3.connect(f"{legacy_db.as_uri()}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            try:
                ver = db.get_current_schema_version(con)
                p_count = con.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            finally:
                con.close()
            return {
                "status": "legacy_requires_migration",
                "can_migrate": True,
                "schema_version": ver,
                "people_count": p_count,
                "db_path": str(legacy_db),
            }
        except Exception as exc:
            return {
                "status": "corrupt_legacy",
                "can_migrate": False,
                "error": str(exc),
                "db_path": str(legacy_db),
            }

    return {
        "status": "unconfigured_or_missing",
        "can_migrate": False,
        "db_path": None,
    }


def plan_migration(root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspect existing state and compute deterministic migration plan without mutating any files."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    detection = detect_migration_status(active_root)

    if detection["status"] == "already_canonical":
        return {
            "can_migrate": False,
            "already_migrated": True,
            "message": "Data Root is already on the canonical Phase 11 structure.",
            "detection": detection,
            "mappings": [],
            "warnings": [],
            "conflicts": [],
        }

    if not detection["can_migrate"]:
        return {
            "can_migrate": False,
            "already_migrated": False,
            "message": f"Cannot migrate: {detection.get('status')}",
            "detection": detection,
            "mappings": [],
            "warnings": [detection.get("error", "Source database not ready for migration.")],
            "conflicts": [],
        }

    source_db = Path(detection["db_path"])
    con = sqlite3.connect(f"{source_db.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            return {
                "can_migrate": False,
                "already_migrated": False,
                "message": f"SQLite integrity check failed on source database: {integrity}",
                "conflicts": [f"Source database corrupt: {integrity}"],
                "warnings": [],
                "mappings": [],
            }

        people_rows = con.execute(
            "SELECT * FROM people ORDER BY display_order, id"
        ).fetchall()

        meta_rows = {
            r["key"]: r["value"] for r in con.execute("SELECT key, value FROM metadata")
        }
        focus_person = meta_rows.get("focus_person")
        people_ids = {row["id"] for row in people_rows}
        if not focus_person or focus_person not in people_ids:
            return {
                "can_migrate": False,
                "already_migrated": False,
                "message": "Cannot identify the owner from metadata.focus_person.",
                "conflicts": ["A valid metadata.focus_person is required; owner identity will not be guessed."],
                "warnings": [],
                "mappings": [],
            }

        id_map: Dict[str, str] = {}
        assigned_canonical: set[str] = set()
        person_mappings: List[Dict[str, Any]] = []
        has_group_tables = all(
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()
            for table in ("groups", "person_groups")
        )

        for p in people_rows:
            old_id = p["id"]
            name = p["name"]
            can_id = generate_canonical_person_id(name, assigned_canonical)
            assigned_canonical.add(can_id)
            id_map[old_id] = can_id

            is_owner = old_id == focus_person
            category = "Me" if is_owner else "Family"
            aliases = [
                row[0]
                for row in con.execute(
                    "SELECT alias FROM aliases WHERE person_id = ? ORDER BY display_order, alias",
                    (old_id,),
                )
            ]
            groups = [
                row[0]
                for row in con.execute(
                    """
                    SELECT g.name FROM groups g
                    JOIN person_groups pg ON pg.group_id = g.id
                    WHERE pg.person_id = ?
                    ORDER BY pg.is_primary DESC, g.display_order, g.name
                    """,
                    (old_id,),
                )
            ] if has_group_tables else []

            person_mappings.append(
                {
                    "old_id": old_id,
                    "canonical_id": can_id,
                    "name": name,
                    "category": category,
                    "is_owner": is_owner,
                    "aliases": aliases,
                    "groups": groups,
                    "birth_year": p["birth_year"],
                    "gender": p["gender"],
                }
            )

        # Plan filesystem moves & journal inspection
        fs_moves: List[Dict[str, Any]] = []
        warnings: List[str] = []
        conflicts: List[str] = []

        people_dir = DataRootManager.get_people_dir(active_root)
        target_people_dir = active_root / "People"

        for m in person_mappings:
            old_id = m["old_id"]
            can_id = m["canonical_id"]
            cat = m["category"]

            old_folder = db.find_person_folder(con, old_id, root=active_root)
            target_folder = target_people_dir / cat / can_id

            old_journal = old_folder / "journal.md" if old_folder else None
            journal_exists = bool(old_journal and old_journal.is_file())
            journal_bytes = old_journal.stat().st_size if journal_exists else 0
            journal_hash = _file_sha256(old_journal) if journal_exists else None

            fs_moves.append(
                {
                    "person_id": can_id,
                    "old_id": old_id,
                    "source_folder": str(old_folder) if old_folder else None,
                    "target_folder": str(target_folder),
                    "journal_exists": journal_exists,
                    "journal_bytes": journal_bytes,
                    "journal_sha256": journal_hash,
                }
            )

        table_counts = {}
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        for t in tables:
            table_counts[t] = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]

        return {
            "can_migrate": True,
            "already_migrated": False,
            "source_db_path": str(source_db),
            "target_db_path": str(active_root / "Database" / "relationships.db"),
            "source_schema_version": detection["schema_version"],
            "target_schema_version": config.CANONICAL_SCHEMA_VERSION,
            "people_count": len(people_rows),
            "mappings": person_mappings,
            "filesystem_moves": fs_moves,
            "source_table_counts": table_counts,
            "warnings": warnings,
            "conflicts": conflicts,
        }
    finally:
        con.close()


def _populate_canonical_database(
    source_con: sqlite3.Connection,
    target_con: sqlite3.Connection,
    id_map: Dict[str, str],
    owner_canonical_id: str,
) -> None:
    """Build all canonical tables in target_con and migrate all records atomically."""
    # 1. Base legacy family schema
    family_engine.create_sqlite_schema(target_con)
    # 2. Schema extensions
    schema_sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    target_con.executescript(schema_sql)

    db._ensure_column(target_con, "people", "category", "ALTER TABLE people ADD COLUMN category TEXT")
    db._ensure_column(target_con, "people", "created_at", "ALTER TABLE people ADD COLUMN created_at TEXT")
    db._ensure_column(target_con, "people", "updated_at", "ALTER TABLE people ADD COLUMN updated_at TEXT")

    # 3. Migrate data inside transaction
    target_con.isolation_level = None
    target_con.execute("BEGIN IMMEDIATE")

    # Copy sources
    for row in source_con.execute("SELECT * FROM sources"):
        target_con.execute(
            """
            INSERT OR IGNORE INTO sources (id, batch_number, file_path, title, kind, recorded_on)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["batch_number"],
                row["file_path"],
                row["title"],
                row["kind"],
                row["recorded_on"],
            ),
        )

    # Copy review_notes
    for row in source_con.execute("SELECT * FROM review_notes"):
        target_con.execute(
            """
            INSERT OR IGNORE INTO review_notes (id, status, text, display_order)
            VALUES (?, ?, ?, ?)
            """,
            (row["id"], row["status"], row["text"], row["display_order"]),
        )

    # Copy groups
    has_groups = source_con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='groups'"
    ).fetchone()
    if has_groups:
        for row in source_con.execute("SELECT * FROM groups"):
            target_con.execute(
                """
                INSERT OR IGNORE INTO groups (id, name, slug, kind, display_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (row["id"], row["name"], row["slug"], row["kind"], row["display_order"]),
            )
    else:
        db._seed_groups_and_assignments(target_con)

    # Insert canonical people
    now_str = _utc_now()
    for row in source_con.execute("SELECT * FROM people ORDER BY display_order, id"):
        old_id = row["id"]
        can_id = id_map[old_id]
        is_owner = (can_id == owner_canonical_id)
        cat = "Me" if is_owner else "Family"
        target_con.execute(
            """
            INSERT INTO people (
              id, name, birth_year, gender, marital_status, branch,
              legacy_relation_en, legacy_relation_ur, note_en, note_ur,
              photo_path, display_order, category, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                can_id,
                row["name"],
                row["birth_year"],
                row["gender"],
                row["marital_status"],
                row["branch"],
                row["legacy_relation_en"],
                row["legacy_relation_ur"],
                row["note_en"],
                row["note_ur"],
                row["photo_path"],
                row["display_order"],
                cat,
                now_str,
                now_str,
            ),
        )

    # Populate identifier_aliases with historical mappings
    for old_id, can_id in id_map.items():
        target_con.execute(
            """
            INSERT INTO identifier_aliases (old_identifier, canonical_id, entity_type, notes, created_at)
            VALUES (?, ?, 'person', 'Migrated from Phase 10 baseline', ?)
            """,
            (old_id, can_id, now_str),
        )

    # Migrate aliases
    for row in source_con.execute("SELECT * FROM aliases"):
        can_id = id_map.get(row["person_id"], row["person_id"])
        target_con.execute(
            "INSERT INTO aliases (person_id, alias, display_order) VALUES (?, ?, ?)",
            (can_id, row["alias"], row["display_order"]),
        )

    # Migrate parent_child
    for row in source_con.execute("SELECT * FROM parent_child ORDER BY id"):
        p_id = id_map.get(row["parent_id"], row["parent_id"])
        c_id = id_map.get(row["child_id"], row["child_id"])
        target_con.execute(
            """
            INSERT INTO parent_child (parent_id, child_id, role, kind)
            VALUES (?, ?, ?, ?)
            """,
            (p_id, c_id, row["role"], row["kind"]),
        )

    # Migrate marriages (strictly ensuring spouse_a < spouse_b)
    for row in source_con.execute("SELECT * FROM marriages ORDER BY display_order, id"):
        sp_a = id_map.get(row["spouse_a"], row["spouse_a"])
        sp_b = id_map.get(row["spouse_b"], row["spouse_b"])
        sp_1 = min(sp_a, sp_b)
        sp_2 = max(sp_a, sp_b)
        target_con.execute(
            """
            INSERT INTO marriages (spouse_a, spouse_b, status, year, children_status, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sp_1,
                sp_2,
                row["status"],
                row["year"],
                row["children_status"],
                row["display_order"],
            ),
        )

    # Migrate sibling_groups
    for row in source_con.execute("SELECT * FROM sibling_groups ORDER BY display_order, id"):
        target_con.execute(
            """
            INSERT INTO sibling_groups (id, is_ordered, type, label_en, label_ur, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["is_ordered"],
                row["type"],
                row["label_en"],
                row["label_ur"],
                row["display_order"],
            ),
        )

    # Migrate sibling_group_members
    for row in source_con.execute("SELECT * FROM sibling_group_members"):
        p_id = id_map.get(row["person_id"], row["person_id"])
        target_con.execute(
            """
            INSERT INTO sibling_group_members (group_id, person_id, member_order)
            VALUES (?, ?, ?)
            """,
            (row["group_id"], p_id, row["member_order"]),
        )

    # Migrate person_groups
    has_person_groups = source_con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='person_groups'"
    ).fetchone()
    if has_person_groups:
        for row in source_con.execute("SELECT * FROM person_groups"):
            can_id = id_map.get(row["person_id"], row["person_id"])
            target_con.execute(
                """
                INSERT OR IGNORE INTO person_groups (person_id, group_id, is_primary)
                VALUES (?, ?, ?)
                """,
                (can_id, row["group_id"], row["is_primary"]),
            )
    else:
        for can_id in id_map.values():
            target_con.execute(
                """
                INSERT OR IGNORE INTO person_groups (person_id, group_id, is_primary)
                VALUES (?, 'family', 1)
                """,
                (can_id,),
            )

    # Migrate general_relationships (ensuring person_a < person_b)
    has_gen = source_con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='general_relationships'"
    ).fetchone()
    if has_gen:
        for row in source_con.execute("SELECT * FROM general_relationships"):
            p_a = id_map.get(row["person_a"], row["person_a"])
            p_b = id_map.get(row["person_b"], row["person_b"])
            p_1 = min(p_a, p_b)
            p_2 = max(p_a, p_b)
            d_from = id_map.get(row["direction_from"], row["direction_from"]) if row["direction_from"] else None
            label_a_to_b = row["label_a_to_b"]
            label_b_to_a = row["label_b_to_a"]
            if (p_1, p_2) != (p_a, p_b):
                label_a_to_b, label_b_to_a = label_b_to_a, label_a_to_b
            target_con.execute(
                """
                INSERT INTO general_relationships (
                  person_a, person_b, type, directionality, direction_from,
                  label_a_to_b, label_b_to_a, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p_1,
                    p_2,
                    row["type"],
                    row["directionality"],
                    d_from,
                    label_a_to_b,
                    label_b_to_a,
                    row["notes"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )

    # Migrate fact_sources
    for row in source_con.execute("SELECT * FROM fact_sources"):
        e_type = row["entity_type"]
        e_key = row["entity_key"]
        note = row["note"]
        source_id = row["source_id"]

        if e_type == "people":
            e_key = id_map.get(e_key, e_key)
        elif e_type == "aliases":
            parts = e_key.split("|", 1)
            p_id = id_map.get(parts[0], parts[0])
            e_key = f"{p_id}|{parts[1]}" if len(parts) > 1 else p_id
        elif e_type == "parent_child":
            parts = e_key.split("|", 1)
            p_id = id_map.get(parts[0], parts[0])
            c_id = id_map.get(parts[1], parts[1]) if len(parts) > 1 else ""
            e_key = f"{p_id}|{c_id}"
        elif e_type == "marriages":
            parts = e_key.split("|", 1)
            m_a = id_map.get(parts[0], parts[0])
            m_b = id_map.get(parts[1], parts[1]) if len(parts) > 1 else ""
            e_key = f"{min(m_a, m_b)}|{max(m_a, m_b)}"
        elif e_type == "sibling_group_members":
            parts = e_key.split("|", 1)
            g_id = parts[0]
            m_id = id_map.get(parts[1], parts[1]) if len(parts) > 1 else ""
            e_key = f"{g_id}|{m_id}"

        target_con.execute(
            """
            INSERT OR IGNORE INTO fact_sources (source_id, entity_type, entity_key, note)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, e_type, e_key, note),
        )

    # Migrate metadata
    for row in source_con.execute("SELECT * FROM metadata"):
        key = row["key"]
        val = row["value"]
        if key == "focus_person":
            val = id_map.get(val, val)
        target_con.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, val),
        )

    target_con.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', ?)",
        (str(config.CANONICAL_SCHEMA_VERSION),),
    )
    target_con.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_name', ?)",
        (config.APP_NAME,),
    )
    target_con.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_version', ?)",
        (config.APP_VERSION,),
    )
    target_con.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('_source_of_truth', 'relationships.db')"
    )
    target_con.execute(f"PRAGMA user_version = {int(config.CANONICAL_SCHEMA_VERSION)}")

    # Verify integrity and foreign keys
    integrity = target_con.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"Target integrity check failed: {integrity}")

    fk_violations = target_con.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        raise RuntimeError(f"Target foreign key check failed: {fk_violations}")

    target_con.execute("COMMIT")


def execute_migration(
    root: Optional[Path] = None,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute complete Phase 11 canonical migration with full safety guarantees."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()

    if DataRootManager.is_read_only(active_root):
        raise DataRootReadOnlyError("Data root is read-only; migration is blocked.")

    _recover_interrupted_migration(active_root)

    plan = plan_migration(active_root)
    if not plan["can_migrate"]:
        if plan.get("already_migrated"):
            return {"ok": True, "already_migrated": True, "plan": plan}
        raise DataRootInvalidError(f"Migration cannot proceed: {plan.get('message')}", detail=plan)

    if dry_run:
        return {"ok": True, "dry_run": True, "plan": plan}

    id_map = {m["old_id"]: m["canonical_id"] for m in plan["mappings"]}
    owner_entry = next((m for m in plan["mappings"] if m["is_owner"]), plan["mappings"][0])
    owner_can_id = owner_entry["canonical_id"]

    source_db_path = Path(plan["source_db_path"])
    target_db_path = active_root / "Database" / "relationships.db"
    target_people_dir = active_root / "People"

    if target_db_path.exists() or target_people_dir.exists():
        raise DataRootInvalidError(
            "Canonical publication targets already exist without a valid completed migration.",
            detail={
                "code": "MIGRATION_TARGET_CONFLICT",
                "database": str(target_db_path),
                "people": str(target_people_dir),
            },
        )

    staging_dir = active_root / f".migration_staging_{uuid.uuid4().hex[:8]}"
    marker_path = active_root / ".migration_incomplete.json"
    marker_payload: Dict[str, Any] = {
        "kind": "mosaic-phase11-migration",
        "state": "preparing",
        "target_db_created": False,
        "target_people_created": False,
    }
    marker_created = False
    root_metadata_path = DataRootManager.get_config_dir(active_root) / "data-root.json"
    state_file = DataRootManager.get_config_dir(active_root) / "state.json"
    hist_note = active_root / "Database" / "HISTORICAL_FAMILY_DB.md"
    original_root_metadata = root_metadata_path.read_bytes() if root_metadata_path.is_file() else None
    original_state = state_file.read_bytes() if state_file.is_file() else None
    original_hist_note = hist_note.read_bytes() if hist_note.is_file() else None

    with MaintenanceLockContext("MIGRATE_CANONICAL_PHASE11"):
        # 1. Pre-migration Safety Backup
        safety_backup = create_backup(
            label="Pre-Phase11",
            category=BackupCategory.SAFETY,
            safety_reason=SafetyReason.PRE_UPGRADE,
            root=active_root,
            _maintenance_held=True,
        )
        safety_ver = verify_backup(Path(safety_backup["path"]))
        if not safety_ver["ok"]:
            raise DataRootError("Pre-migration safety backup verification failed. Aborting migration without changes.")

        try:
            _check_failpoint("before_db_staging")
            staging_dir.mkdir(parents=True, exist_ok=False)
            staged_db = staging_dir / "relationships.db"
            staged_people = staging_dir / "People"

            # 2. Build target database in staging
            src_con = sqlite3.connect(f"{source_db_path.as_uri()}?mode=ro", uri=True)
            src_con.row_factory = sqlite3.Row
            target_con = sqlite3.connect(str(staged_db))
            target_con.row_factory = sqlite3.Row
            target_con.execute("PRAGMA foreign_keys = ON")
            target_con.execute("PRAGMA busy_timeout = 5000")

            try:
                _check_failpoint("during_db_migration")
                _populate_canonical_database(src_con, target_con, id_map, owner_can_id)
            finally:
                src_con.close()
                target_con.close()
            _check_failpoint("after_db_transformation")

            # 3. Build canonical filesystem in staging
            (staged_people / "Me").mkdir(parents=True, exist_ok=True)
            (staged_people / "Family").mkdir(parents=True, exist_ok=True)
            (staged_people / "Friends").mkdir(parents=True, exist_ok=True)
            for m in plan["mappings"]:
                _check_failpoint("during_folder_staging")
                can_id = m["canonical_id"]
                old_id = m["old_id"]
                name = m["name"]
                cat = m["category"]

                folder = staged_people / cat / can_id
                folder.mkdir(parents=True, exist_ok=True)

                # Locate old journal if available
                src_journal_bytes: Optional[bytes] = None
                move_info = next((f for f in plan["filesystem_moves"] if f["canonical_id" if "canonical_id" in f else "person_id"] == can_id), None)
                if move_info and move_info.get("source_folder"):
                    src_j_file = Path(move_info["source_folder"]) / "journal.md"
                    if src_j_file.is_file():
                        _check_failpoint("during_journal_copy")
                        raw_bytes = src_j_file.read_bytes()
                        raw_bytes.decode("utf-8")
                        src_journal_bytes = raw_bytes
                        # Verify hash matches
                        src_hash = hashlib.sha256(raw_bytes).hexdigest()
                        if move_info.get("journal_sha256") and src_hash != move_info["journal_sha256"]:
                            raise RuntimeError(f"Journal hash mismatch during migration for {old_id}")

                initialize_person_folder(
                    folder,
                    can_id,
                    name,
                    primary_category=cat,
                    initial_journal_bytes=src_journal_bytes,
                    aliases=m.get("aliases"),
                    groups=m.get("groups"),
                    birth_year=m.get("birth_year"),
                    gender=m.get("gender"),
                )

                if src_journal_bytes is not None:
                    migrated_journal = folder / canonical_journal_filename()
                    if migrated_journal.read_bytes() != src_journal_bytes:
                        raise RuntimeError(f"Journal byte mismatch after staging for {old_id}")

            # Validate the complete staged payload before any publication.
            staged_con = sqlite3.connect(f"{staged_db.as_uri()}?mode=ro", uri=True)
            staged_con.row_factory = sqlite3.Row
            try:
                if staged_con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Staged canonical database failed integrity_check.")
                if staged_con.execute("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("Staged canonical database failed foreign_key_check.")
                if db.get_current_schema_version(staged_con) != config.CANONICAL_SCHEMA_VERSION:
                    raise RuntimeError("Staged canonical database schema version is incoherent.")
                if staged_con.execute("SELECT COUNT(*) FROM people").fetchone()[0] != len(plan["mappings"]):
                    raise RuntimeError("Staged canonical database person count is incomplete.")
            finally:
                staged_con.close()

            _check_failpoint("after_validation_before_publish")

            # 4. Recoverable publication. The marker makes every runtime path
            # fail closed until both components and final verification succeed.
            target_db_path.parent.mkdir(parents=True, exist_ok=True)
            _write_operation_marker(marker_path, marker_payload)
            marker_created = True

            staged_people.rename(target_people_dir)
            marker_payload.update(state="people_published", target_people_created=True)
            _write_operation_marker(marker_path, marker_payload)
            _check_failpoint("after_people_publish_before_db_publish")

            os.replace(staged_db, target_db_path)
            marker_payload.update(state="database_published", target_db_created=True)
            _write_operation_marker(marker_path, marker_payload)
            _check_failpoint("during_publication")

            family_engine.rebind_active_root()
            post_health = audit_data_root(active_root)
            if not post_health.ok:
                raise RuntimeError(f"Post-migration audit failed: {post_health.issues}")
            _check_failpoint("during_final_verification")

            # Preserve historical family.db documentation
            if not hist_note.exists():
                hist_note.write_text(
                    "# Historical Family Database Note\n\n"
                    "As of Phase 11 (Canonical Data Foundation & Migration), "
                    "`Database/relationships.db` is the single runtime authoritative "
                    "SQLite store for Mosaic.\n\n"
                    "The legacy `Database/Main/family.db` is superseded and retained "
                    "for historical provenance, safety audits, and baseline comparisons.\n"
                    f"- Migrated on: {_utc_now()}\n"
                    f"- Pre-migration safety backup: {safety_backup['id']}\n",
                    encoding="utf-8",
                )

            root_metadata = DataRootManager.read_root_metadata(active_root)
            root_metadata.update(
                {
                    "format": "people-relationships-data-root",
                    "version": 1,
                    "storage_layout": DataRootManager.CANONICAL_LAYOUT,
                    "canonical_database": "Database/relationships.db",
                }
            )
            root_metadata_path.parent.mkdir(parents=True, exist_ok=True)
            root_metadata_path.write_text(
                json.dumps(root_metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # Update state.json with canonical perspective
            if state_file.exists():
                try:
                    s_data = json.loads(state_file.read_text(encoding="utf-8"))
                    if isinstance(s_data, dict):
                        old_p = s_data.get("perspective_person_id")
                        if old_p in id_map:
                            s_data["perspective_person_id"] = id_map[old_p]
                            state_file.write_text(
                                json.dumps(s_data, indent=2) + "\n", encoding="utf-8"
                            )
                except Exception:
                    pass

            marker_path.unlink()
            marker_created = False
        except Exception:
            if target_db_path.is_file():
                target_db_path.unlink()
            if target_people_dir.is_dir():
                remove_tree(target_people_dir)
            for path, original in (
                (root_metadata_path, original_root_metadata),
                (state_file, original_state),
                (hist_note, original_hist_note),
            ):
                if original is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original)
            if marker_created and marker_path.exists():
                marker_path.unlink()
            family_engine.rebind_active_root()
            raise
        finally:
            remove_tree(staging_dir, ignore_errors=True)

    return {
        "ok": True,
        "already_migrated": False,
        "safety_backup_id": safety_backup["id"],
        "target_db_path": str(target_db_path),
        "migrated_people_count": len(plan["mappings"]),
        "mappings": plan["mappings"],
        "post_health": post_health.to_dict(),
    }


class CanonicalMigrationEngine:
    """Convenience class wrapper for migration planning and execution."""

    def __init__(self, root: Optional[Path] = None, dry_run: bool = False):
        self.root = Path(root) if root else None
        self.dry_run = dry_run

    def plan(self) -> Dict[str, Any]:
        return plan_migration(self.root)

    def migrate(self) -> Dict[str, Any]:
        return execute_migration(self.root, dry_run=self.dry_run)
