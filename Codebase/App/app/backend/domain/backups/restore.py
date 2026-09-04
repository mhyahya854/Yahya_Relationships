"""Guided Atomic Backup Restore Engine."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ...data_root.errors import (
    BackupDatabaseInvalidError,
    BackupManifestInvalidError,
    RestoreError,
)
from ...data_root.manager import DataRootManager
from ..maintenance import MaintenanceLockContext
from .create import create_backup
from .verify import verify_backup


def restore_backup(
    backup_id_or_path: str,
    confirmation_token: str = "RESTORE",
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute guided atomic backup restore with automatic pre-restore safety backup and rollback capability."""
    if confirmation_token.strip() != "RESTORE":
        raise RestoreError("Confirmation token 'RESTORE' is required to proceed with restore.")

    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    backups_dir = DataRootManager.get_backups_dir(active_root)

    # 1. Resolve Backup Directory
    backup_path = Path(backup_id_or_path)
    if not backup_path.is_absolute():
        backup_path = backups_dir / backup_id_or_path
    backup_path = backup_path.resolve()

    if not backup_path.exists() or not backup_path.is_dir():
        raise RestoreError(f"Backup directory '{backup_path}' does not exist.")

    # 2. Precheck Backup Verification
    verification = verify_backup(backup_path)
    if not verification["ok"]:
        raise RestoreError(
            f"Backup verification failed: {', '.join(verification.get('issues', []))}",
            code="BACKUP_CORRUPTED",
            detail=verification,
        )

    manifest = verification["manifest"]

    # 3. Create Pre-Restore Safety Backup
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safety_label = f"pre-restore-{stamp}"
    try:
        safety_backup = create_backup(label=safety_label, root=active_root)
    except Exception as exc:
        raise RestoreError(
            f"Pre-restore safety backup failed: {exc}. Restore aborted for data safety.",
            code="SAFETY_BACKUP_FAILED",
        ) from exc

    # 4. Execute Atomic Staged Restore under Maintenance Lock
    with MaintenanceLockContext(f"RESTORE_BACKUP:{backup_path.name}"):
        staging_dir = active_root / f".restore_staging_{uuid.uuid4().hex[:8]}"
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)

            # Copy backup into staging
            for item in backup_path.iterdir():
                if item.name == "manifest.json":
                    continue
                dst = staging_dir / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dst))
                else:
                    shutil.copy2(str(item), str(dst))

            # Validate Staged DB & Files
            staged_db = DataRootManager.get_database_path(staging_dir)
            if staged_db.exists():
                conn = sqlite3.connect(str(staged_db))
                staged_integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                conn.close()
                if staged_integrity != "ok":
                    raise BackupDatabaseInvalidError(f"Staged database integrity failed: {staged_integrity}")

            # Switch Active Files safely
            # Replace database
            active_db = DataRootManager.get_database_path(active_root)
            staged_db_src = DataRootManager.get_database_path(staging_dir)
            if staged_db_src.exists():
                active_db.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(staged_db_src), str(active_db))

            # Replace people directory
            active_people = DataRootManager.get_people_dir(active_root)
            staged_people = DataRootManager.get_people_dir(staging_dir)
            if staged_people.exists():
                if active_people.exists():
                    shutil.rmtree(str(active_people))
                shutil.copytree(str(staged_people), str(active_people))

            # Replace config directory (preserve active root pointer)
            active_config = DataRootManager.get_config_dir(active_root)
            staged_config = DataRootManager.get_config_dir(staging_dir)
            if staged_config.exists():
                for cfg_item in staged_config.iterdir():
                    dst_cfg = active_config / cfg_item.name
                    if cfg_item.is_dir():
                        if dst_cfg.exists():
                            shutil.rmtree(str(dst_cfg))
                        shutil.copytree(str(cfg_item), str(dst_cfg))
                    else:
                        shutil.copy2(str(cfg_item), str(dst_cfg))

            # Cleanup staging
            if staging_dir.exists():
                shutil.rmtree(str(staging_dir))

            # Record Restore History Entry
            restore_history_file = active_config / "restore-history.json"
            history_entries = []
            if restore_history_file.exists():
                try:
                    history_entries = json.loads(restore_history_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            history_entries.append({
                "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "restored_backup_id": backup_path.name,
                "safety_backup_id": safety_backup["id"],
                "manifest_label": manifest.get("label"),
                "person_count": manifest.get("person_count"),
                "journal_count": manifest.get("journal_count"),
            })
            restore_history_file.write_text(json.dumps(history_entries, indent=2), encoding="utf-8")

            return {
                "ok": True,
                "restored_backup_id": backup_path.name,
                "safety_backup_id": safety_backup["id"],
                "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "manifest": manifest,
            }

        except Exception as exc:
            # Clean up staging dir
            if staging_dir.exists():
                try:
                    shutil.rmtree(str(staging_dir))
                except Exception:
                    pass

            # Roll back using safety backup
            try:
                safety_path = Path(safety_backup["path"])
                safety_db = DataRootManager.get_database_path(safety_path)
                active_db = DataRootManager.get_database_path(active_root)
                if safety_db.exists():
                    shutil.copy2(str(safety_db), str(active_db))

                safety_people = DataRootManager.get_people_dir(safety_path)
                active_people = DataRootManager.get_people_dir(active_root)
                if safety_people.exists():
                    if active_people.exists():
                        shutil.rmtree(str(active_people))
                    shutil.copytree(str(safety_people), str(active_people))
            except Exception as rollback_exc:
                raise RestoreError(
                    f"Restore failed ({exc}) AND safety rollback failed: {rollback_exc}",
                    code="RESTORE_ROLLBACK_FAILED",
                ) from exc

            raise RestoreError(
                f"Restore failed ({exc}). Active data was safely rolled back using safety backup '{safety_backup['id']}'.",
                code="RESTORE_FAILED",
            ) from exc
