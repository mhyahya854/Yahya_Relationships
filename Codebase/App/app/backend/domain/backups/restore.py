"""Transactional backup restore with exact three-component rollback."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ...data_root.errors import DataRootReadOnlyError, RestoreError
from ...data_root.manager import DataRootManager
from ...data_root.validation import audit_data_root
from ...model import load_model, validate_model
from ..maintenance import MaintenanceLockContext
from .create import BackupCategory, SafetyReason, _copy_tree_safe, create_backup
from .paths import native_io_path, remove_tree, resolve_backup_reference, sqlite_read_only_uri
from .verify import verify_backup


def _messages(verification: Dict[str, Any]) -> str:
    return "; ".join(issue.get("message", str(issue)) for issue in verification.get("issues", []))


def _switch_component(active: Path, staged: Path, rollback: Path) -> None:
    rollback.parent.mkdir(parents=True, exist_ok=True)
    active.parent.mkdir(parents=True, exist_ok=True)
    if active.exists():
        active.rename(rollback)
    staged.rename(active)


def _rollback_component(active: Path, rollback: Path, recovery: Path) -> None:
    if active.exists():
        recovery.parent.mkdir(parents=True, exist_ok=True)
        active.rename(recovery)
    if rollback.exists():
        active.parent.mkdir(parents=True, exist_ok=True)
        rollback.rename(active)


def _post_restore_health(
    root: Path,
    expected_people: int,
    *,
    expected_schema: int,
) -> Dict[str, Any]:
    database = DataRootManager.get_database_path(root)
    connection = sqlite3.connect(sqlite_read_only_uri(database), uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        person_count = int(connection.execute("SELECT COUNT(*) FROM people").fetchone()[0])
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'app_schema_version'"
        ).fetchone()
        metadata_schema = int(row[0]) if row else 0
        pragma_schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if metadata_schema and pragma_schema and metadata_schema != pragma_schema:
            raise RestoreError("Restored database schema authorities disagree.", code="POST_RESTORE_HEALTH_FAILED")
        schema_version = metadata_schema or pragma_schema
    finally:
        connection.close()
    if (
        integrity != "ok"
        or foreign_key_violations
        or person_count != expected_people
        or schema_version != expected_schema
    ):
        raise RestoreError("Restored database failed post-restore validation.", code="POST_RESTORE_HEALTH_FAILED")

    people_dir = DataRootManager.get_people_dir(root)
    for journal in native_io_path(people_dir).rglob("*"):
        if journal.is_file() and journal.name in ("journal.md", "journal(personal thoughts).md"):
            journal.read_bytes()
    health = audit_data_root(root)
    if not health.ok:
        raise RestoreError(
            "Restored Data Root failed filesystem reconciliation.",
            code="POST_RESTORE_HEALTH_FAILED",
            detail=health.to_dict(),
        )
    model = load_model(database)
    if model.get("metadata", {}).get("focus_person"):
        validate_model(model)
    return health.to_dict()


def _write_restore_marker(path: Path, *, canonical: bool) -> None:
    payload = {
        "kind": "mosaic-backup-restore",
        "target_layout": "canonical" if canonical else "legacy",
    }
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _rollback_paths(
    switched: list[tuple[Path, Path]], recovery_root: Path
) -> None:
    for index, (active, rollback) in enumerate(reversed(switched)):
        _rollback_component(active, rollback, recovery_root / f"component-{index}")


def restore_backup(
    backup_id_or_path: str | Path,
    confirmation_token: str = "RESTORE",
    root: Optional[Path] = None,
    *,
    _allow_path: bool = False,
    _require_safety_backup: bool = True,
    _maintenance_held: bool = False,
) -> Dict[str, Any]:
    """Restore DB, People, and portable Config as one reversible transaction."""
    if confirmation_token != "RESTORE":
        raise RestoreError("Confirmation token 'RESTORE' is required.", code="RESTORE_CONFIRMATION_REQUIRED")
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    backup_path = resolve_backup_reference(
        backup_id_or_path,
        active_root,
        allow_path=_allow_path or isinstance(backup_id_or_path, Path),
    )

    verification = verify_backup(backup_path)
    if not verification["ok"]:
        raise RestoreError(
            f"Backup verification failed: {_messages(verification)}",
            code="BACKUP_CORRUPTED" if verification["status"] != "incompatible" else "BACKUP_SCHEMA_UNSUPPORTED",
            detail=verification,
        )
    if DataRootManager.is_read_only(active_root):
        raise DataRootReadOnlyError("Data root is read-only; restore is blocked.")

    manifest = verification["manifest"]
    canonical_backup = (backup_path / "data" / "relationships.db").is_file()
    safety_backup: Dict[str, Any] | None = None
    operation_id = uuid.uuid4().hex
    staging_dir = active_root / f".restore_staging_{operation_id}"
    rollback_dir = active_root / f".restore_rollback_{operation_id}"
    marker_path = active_root / ".restore_incomplete.json"
    switched: list[tuple[Path, Path]] = []

    lock = nullcontext() if _maintenance_held else MaintenanceLockContext(f"RESTORE_BACKUP:{backup_path.name}")
    with lock:
        try:
            # Recheck under the exclusive mutation lock before creating recovery state.
            verification = verify_backup(backup_path)
            if not verification["ok"]:
                raise RestoreError("Backup changed during restore precheck.", code="BACKUP_CORRUPTED", detail=verification)
            if _require_safety_backup:
                try:
                    safety_backup = create_backup(
                        label=f"Before restoring {manifest.get('label') or backup_path.name}",
                        category=BackupCategory.SAFETY,
                        safety_reason=SafetyReason.PRE_RESTORE,
                        root=active_root,
                        _maintenance_held=True,
                    )
                    safety_verification = verify_backup(Path(safety_backup["path"]))
                    if not safety_verification["ok"]:
                        raise RestoreError("Safety backup verification failed.", code="SAFETY_BACKUP_FAILED")
                except Exception as exc:
                    if isinstance(exc, RestoreError) and exc.code == "SAFETY_BACKUP_FAILED":
                        raise
                    raise RestoreError(
                        "Pre-restore safety backup failed; active data was not changed.",
                        code="SAFETY_BACKUP_FAILED",
                    ) from exc

            staged_snapshot = staging_dir / "snapshot"
            _copy_tree_safe(backup_path, staged_snapshot)
            staged_verification = verify_backup(staged_snapshot)
            if not staged_verification["ok"]:
                raise RestoreError("Staged restore failed verification.", code="RESTORE_STAGING_INVALID")

            staged_db_filename = "relationships.db" if canonical_backup else "family.db"
            staged_db = staged_snapshot / "data" / staged_db_filename
            staged_people = staged_snapshot / "people"
            staged_config = staged_snapshot / "config"
            staged_raw_history = staged_snapshot / "data" / "raw_processing_history.md"
            if canonical_backup:
                active_db = active_root / "Database" / "relationships.db"
                active_people = active_root / "People"
            else:
                active_db = active_root / "Database" / "Main" / "family.db"
                active_people = active_root / "Database" / "People"
            active_config = active_root / "Database" / "Config"
            active_raw_history = active_root / "Database" / "raw_processing_history.md"

            _write_restore_marker(marker_path, canonical=canonical_backup)

            if not canonical_backup:
                # A legacy restore must cease being canonical. Move both
                # canonical authority components aside before publishing legacy.
                for active, rollback in (
                    (active_root / "Database" / "relationships.db", rollback_dir / "obsolete" / "relationships.db"),
                    (
                        active_root / "Database" / "HISTORICAL_FAMILY_DB.md",
                        rollback_dir / "obsolete" / "HISTORICAL_FAMILY_DB.md",
                    ),
                    (active_root / "People", rollback_dir / "obsolete" / "People"),
                ):
                    if active.exists():
                        rollback.parent.mkdir(parents=True, exist_ok=True)
                        active.rename(rollback)
                        switched.append((active, rollback))

            components = [
                (active_db, staged_db, rollback_dir / "active" / staged_db_filename),
                (active_people, staged_people, rollback_dir / "active" / "people"),
                (active_config, staged_config, rollback_dir / "active" / "config"),
            ]
            if canonical_backup and staged_raw_history.is_file():
                components.append((active_raw_history, staged_raw_history, rollback_dir / "active" / "raw_processing_history.md"))
            elif canonical_backup and active_raw_history.exists():
                # A pre-Phase-12 canonical snapshot has no Raw projection;
                # retain the old bytes only in the rollback area, never mix
                # them into the restored generation.
                obsolete_history = rollback_dir / "obsolete" / "raw_processing_history.md"
                obsolete_history.parent.mkdir(parents=True, exist_ok=True)
                active_raw_history.rename(obsolete_history)
                switched.append((active_raw_history, obsolete_history))
            for active, staged, rollback in components:
                _switch_component(active, staged, rollback)
                switched.append((active, rollback))

            root_metadata = DataRootManager.read_root_metadata(active_root)
            if canonical_backup:
                root_metadata.update(
                    {
                        "storage_layout": DataRootManager.CANONICAL_LAYOUT,
                        "canonical_database": "Database/relationships.db",
                    }
                )
            else:
                root_metadata.pop("storage_layout", None)
                root_metadata.pop("canonical_database", None)
            active_config.mkdir(parents=True, exist_ok=True)
            (active_config / "data-root.json").write_text(
                json.dumps(root_metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            post_health = _post_restore_health(
                active_root,
                manifest["person_count"],
                expected_schema=manifest["sqlite_schema_version"],
            )
            history_path = active_config / "restore-history.json"
            history: list[Dict[str, Any]] = []
            if history_path.exists():
                parsed = json.loads(history_path.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    history = parsed
            restored_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            history.append(
                {
                    "restored_at": restored_at,
                    "restored_backup_id": backup_path.name,
                    "safety_backup_id": safety_backup["id"] if safety_backup else None,
                    "backup_label": manifest.get("label"),
                    "category": manifest.get("category", "legacy"),
                    "person_count": manifest["person_count"],
                    "journal_count": manifest["journal_count"],
                    "result": "success",
                }
            )
            history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            marker_path.unlink()
        except Exception as exc:
            if not switched:
                remove_tree(staging_dir, ignore_errors=True)
                if marker_path.exists():
                    marker_path.unlink()
                if isinstance(exc, RestoreError):
                    raise
                raise RestoreError(f"Restore staging failed: {exc}", code="RESTORE_FAILED") from exc
            try:
                _rollback_paths(switched, staging_dir / "failed-active")
                if marker_path.exists():
                    marker_path.unlink()
                rollback_health = audit_data_root(active_root)
                if not rollback_health.ok:
                    raise RuntimeError("Rolled-back Data Root failed validation.")
            except Exception as rollback_exc:
                raise RestoreError(
                    f"Restore failed and exact rollback also failed: {rollback_exc}",
                    code="RESTORE_ROLLBACK_FAILED",
                    detail={
                        "staging_path": str(staging_dir),
                        "rollback_path": str(rollback_dir),
                        "safety_backup_id": safety_backup["id"] if safety_backup else None,
                    },
                ) from exc
            remove_tree(staging_dir, ignore_errors=True)
            remove_tree(rollback_dir, ignore_errors=True)
            raise RestoreError(
                "Restore failed; database, People, and Config were rolled back exactly.",
                code="RESTORE_FAILED",
                detail={"cause": str(exc), "safety_backup_id": safety_backup["id"] if safety_backup else None},
            ) from exc

    remove_tree(staging_dir, ignore_errors=True)
    remove_tree(rollback_dir, ignore_errors=True)
    return {
        "ok": True,
        "restored_backup_id": backup_path.name,
        "safety_backup_id": safety_backup["id"] if safety_backup else None,
        "restored_at": restored_at,
        "manifest": manifest,
        "post_restore_health": post_health,
    }
