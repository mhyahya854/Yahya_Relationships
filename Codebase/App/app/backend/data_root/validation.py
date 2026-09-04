"""Data Root Health & Reconciliation Validator."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import DataRootManager
from .models import (
    DatabaseHealth,
    DataRootHealth,
    FilesystemHealth,
    ValidationIssue,
)


def audit_data_root(root: Optional[Path] = None) -> DataRootHealth:
    """Read-only audit of Data Root structure, SQLite integrity, and journal alignment."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    issues: List[ValidationIssue] = []

    if not active_root.exists():
        issues.append(
            ValidationIssue(
                code="DATA_ROOT_MISSING",
                severity="error",
                message=f"Data Root directory does not exist at '{active_root}'.",
                suggested_action="Reconnect external drive or select an existing data root.",
            )
        )
        return DataRootHealth(
            ok=False,
            read_only=False,
            layout_mode="missing",
            root_path=str(active_root),
            issues=issues,
        )

    read_only = DataRootManager.is_read_only(active_root)
    if read_only:
        issues.append(
            ValidationIssue(
                code="DATA_ROOT_READ_ONLY",
                severity="warning",
                message=f"Data Root directory at '{active_root}' is read-only.",
                suggested_action="Editing disabled. Grant write permissions to enable mutations.",
            )
        )

    db_path = DataRootManager.get_database_path(active_root)
    layout_mode = "portable" if (active_root / "data" / "family.db").exists() else "legacy_repo_root"

    db_health: Optional[DatabaseHealth] = None
    fs_health = FilesystemHealth()

    if not db_path.exists():
        issues.append(
            ValidationIssue(
                code="DATABASE_MISSING",
                severity="error",
                message=f"Database file not found at '{db_path}'.",
                suggested_action="Restore from backup or verify active root location.",
            )
        )
    else:
        # Check SQLite Database
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

            if integrity != "ok":
                issues.append(
                    ValidationIssue(
                        code="DATABASE_CORRUPT",
                        severity="error",
                        message=f"SQLite integrity check failed: {integrity}",
                        suggested_action="Restore from the most recent safe backup.",
                    )
                )

            p_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            pc_count = conn.execute("SELECT COUNT(*) FROM parent_child").fetchone()[0]
            m_count = conn.execute("SELECT COUNT(*) FROM marriages").fetchone()[0]
            s_row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'app_schema_version'"
            ).fetchone()
            schema_ver = int(s_row["value"]) if s_row else 1

            db_health = DatabaseHealth(
                integrity=integrity,
                people_count=p_count,
                parent_child_count=pc_count,
                marriages_count=m_count,
                schema_version=schema_ver,
            )

            # Reconcile Database People with Filesystem Folders
            people_rows = conn.execute(
                """
                SELECT p.id, p.name, g.slug AS group_slug
                FROM people p
                LEFT JOIN person_groups pg ON pg.person_id = p.id AND pg.is_primary = 1
                LEFT JOIN groups g ON g.id = pg.group_id
                """
            ).fetchall()
            conn.close()

            people_dir = DataRootManager.get_people_dir(active_root)
            db_person_ids = {r["id"] for r in people_rows}

            for p_row in people_rows:
                pid = p_row["id"]
                p_name = p_row["name"]
                group_slug = p_row["group_slug"] or "Other"

                expected_folder = people_dir / group_slug / pid
                archived_folder = people_dir / "_archived" / pid

                # Check if folder exists anywhere under people/
                matching_folders = list(people_dir.rglob(pid))
                matching_folders = [f for f in matching_folders if f.is_dir()]

                if not matching_folders:
                    fs_health.missing_person_folders.append(pid)
                    issues.append(
                        ValidationIssue(
                            code="MISSING_PERSON_FOLDER",
                            severity="error",
                            message=f"No folder exists for active person '{p_name}' ({pid}).",
                            person_id=pid,
                            suggested_action="Use safe repair to create missing folder and journal.",
                        )
                    )
                else:
                    # Folder exists, check journal.md
                    primary_f = matching_folders[0]
                    journal_file = primary_f / "journal.md"
                    if not journal_file.exists():
                        fs_health.missing_journals.append(pid)
                        issues.append(
                            ValidationIssue(
                                code="MISSING_JOURNAL",
                                severity="warning",
                                message=f"Journal missing for '{p_name}' at {primary_f.name}.",
                                person_id=pid,
                                path=str(primary_f),
                                suggested_action="Recreate initial journal header file.",
                            )
                        )

                    # Check if DB person is active but folder is in _archived
                    if archived_folder.exists() and not (people_dir / group_slug / pid).exists():
                        fs_health.archived_active_mismatches.append(pid)
                        issues.append(
                            ValidationIssue(
                                code="ARCHIVED_ACTIVE_MISMATCH",
                                severity="error",
                                message=f"DB says person '{p_name}' is active, but folder is archived.",
                                person_id=pid,
                                path=str(archived_folder),
                                suggested_action="Move folder back from _archived to active group.",
                            )
                        )

                    if len(matching_folders) > 1:
                        fs_health.duplicate_folder_identities.append(pid)
                        issues.append(
                            ValidationIssue(
                                code="DUPLICATE_PERSON_FOLDERS",
                                severity="warning",
                                message=f"Multiple folders exist for person '{p_name}': {[str(f) for f in matching_folders]}",
                                person_id=pid,
                                suggested_action="Consolidate duplicate person folders.",
                            )
                        )

            # Check for Orphan Folders (Folders on disk that are NOT in DB)
            if people_dir.exists():
                for group_dir in people_dir.iterdir():
                    if not group_dir.is_dir() or group_dir.name == "_archived":
                        continue
                    for p_dir in group_dir.iterdir():
                        if p_dir.is_dir():
                            pid = p_dir.name
                            if pid not in db_person_ids:
                                fs_health.orphan_person_folders.append(pid)
                                issues.append(
                                    ValidationIssue(
                                        code="ORPHAN_PERSON_FOLDER",
                                        severity="info",
                                        message=f"Orphan folder '{pid}' exists at {p_dir} but is absent from database.",
                                        person_id=pid,
                                        path=str(p_dir),
                                        suggested_action="Review and archive or restore orphan folder.",
                                    )
                                )

        except Exception as exc:
            issues.append(
                ValidationIssue(
                    code="DATABASE_ERROR",
                    severity="error",
                    message=f"Failed to inspect SQLite database: {exc}",
                    suggested_action="Verify database file accessibility.",
                )
            )

    is_ok = not any(i.severity == "error" for i in issues)
    return DataRootHealth(
        ok=is_ok,
        read_only=read_only,
        layout_mode=layout_mode,
        root_path=str(active_root),
        database=db_health,
        filesystem=fs_health,
        issues=issues,
    )


def safe_repair_data_root(root: Optional[Path] = None) -> Dict[str, Any]:
    """Deterministically repair non-destructive issues (create missing folders/journals).

    NEVER automatically deletes orphan folders.
    """
    health = audit_data_root(root)
    if not health.database:
        return {"ok": False, "repaired": 0, "errors": ["Database unavailable for repair."]}

    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    db_path = DataRootManager.get_database_path(active_root)

    repaired_count = 0
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Repair missing person folders & journals
        from ..db import ensure_person_folder, ensure_journal

        for pid in health.filesystem.missing_person_folders:
            ensure_person_folder(conn, pid)
            repaired_count += 1

        for pid in health.filesystem.missing_journals:
            ensure_journal(conn, pid)
            repaired_count += 1

        # Move back archived-active mismatches
        people_dir = DataRootManager.get_people_dir(active_root)
        archived_dir = people_dir / "_archived"

        for pid in health.filesystem.archived_active_mismatches:
            archived_f = archived_dir / pid
            if archived_f.exists():
                row = conn.execute(
                    """
                    SELECT g.slug FROM groups g
                    JOIN person_groups pg ON pg.group_id = g.id
                    WHERE pg.person_id = ? AND pg.is_primary = 1
                    """,
                    (pid,),
                ).fetchone()
                target_slug = row["slug"] if row else "Other"
                dest_f = people_dir / target_slug / pid
                dest_f.parent.mkdir(parents=True, exist_ok=True)
                archived_f.rename(dest_f)
                repaired_count += 1

        return {
            "ok": True,
            "repaired": repaired_count,
            "post_repair_health": audit_data_root(root).to_dict(),
        }
    finally:
        conn.close()
