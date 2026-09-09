"""Transactional backup restore with exact three-component rollback."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ... import config
from ...data_root.errors import DataRootReadOnlyError, RestoreError
from ...data_root.manager import DataRootManager
from ...data_root.validation import audit_data_root
from ...model import load_model, validate_model
from ..maintenance import MaintenanceLockContext
from .create import BackupCategory, SafetyReason, _copy_tree_safe, create_backup
from .paths import resolve_backup_reference
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
    if not rollback.exists():
        return
    if active.exists():
        recovery.parent.mkdir(parents=True, exist_ok=True)
        active.rename(recovery)
    rollback.rename(active)


def _post_restore_health(root: Path, expected_people: int) -> Dict[str, Any]:
    database = DataRootManager.get_database_path(root)
    connection = sqlite3.connect(str(database))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        person_count = int(connection.execute("SELECT COUNT(*) FROM people").fetchone()[0])
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'app_schema_version'"
        ).fetchone()
        schema_version = int(row[0]) if row else int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()
    if integrity != "ok" or person_count != expected_people or not (1 <= schema_version <= config.APP_SCHEMA_VERSION):
        raise RestoreError("Restored database failed post-restore validation.", code="POST_RESTORE_HEALTH_FAILED")

    people_dir = DataRootManager.get_people_dir(root)
    for journal in people_dir.rglob("journal.md"):
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


def restore_backup(
    backup_id_or_path: str | Path,
    confirmation_token: str = "RESTORE",
    root: Optional[Path] = None,
    *,
    _allow_path: bool = False,
    _require_safety_backup: bool = True,
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
    safety_backup: Dict[str, Any] | None = None
    operation_id = uuid.uuid4().hex
    staging_dir = active_root / f".restore_staging_{operation_id}"
    rollback_dir = active_root / f".restore_rollback_{operation_id}"

    with MaintenanceLockContext(f"RESTORE_BACKUP:{backup_path.name}"):
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

            active_db = DataRootManager.get_database_path(active_root)
            active_people = DataRootManager.get_people_dir(active_root)
            active_config = DataRootManager.get_config_dir(active_root)
            staged_db = staged_snapshot / "data" / "family.db"
            staged_people = staged_snapshot / "people"
            staged_config = staged_snapshot / "config"
            rollback_db = rollback_dir / "database" / "family.db"
            rollback_people = rollback_dir / "people"
            rollback_config = rollback_dir / "config"

            _switch_component(active_db, staged_db, rollback_db)
            _switch_component(active_people, staged_people, rollback_people)
            _switch_component(active_config, staged_config, rollback_config)

            post_health = _post_restore_health(active_root, manifest["person_count"])
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
        except Exception as exc:
            if not rollback_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
                if isinstance(exc, RestoreError):
                    raise
                raise RestoreError(f"Restore staging failed: {exc}", code="RESTORE_FAILED") from exc
            try:
                recovery_dir = staging_dir / "failed-active"
                _rollback_component(active_config, rollback_dir / "config", recovery_dir / "config")
                _rollback_component(active_people, rollback_dir / "people", recovery_dir / "people")
                _rollback_component(active_db, rollback_dir / "database" / "family.db", recovery_dir / "family.db")
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
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(rollback_dir, ignore_errors=True)
            raise RestoreError(
                "Restore failed; database, People, and Config were rolled back exactly.",
                code="RESTORE_FAILED",
                detail={"cause": str(exc), "safety_backup_id": safety_backup["id"] if safety_backup else None},
            ) from exc

    shutil.rmtree(staging_dir, ignore_errors=True)
    shutil.rmtree(rollback_dir, ignore_errors=True)
    return {
        "ok": True,
        "restored_backup_id": backup_path.name,
        "safety_backup_id": safety_backup["id"] if safety_backup else None,
        "restored_at": restored_at,
        "manifest": manifest,
        "post_restore_health": post_health,
    }
