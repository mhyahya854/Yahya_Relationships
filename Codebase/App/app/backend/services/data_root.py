"""Data Root Service."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from ..data_root import (
    DataRootManager,
    audit_data_root,
    safe_repair_data_root,
)
from ..data_root.errors import (
    DataRootDestinationConflictError,
    DataRootInvalidError,
    DataRootNotFoundError,
    DataRootReadOnlyError,
)
from ..domain.backups import create_backup, verify_backup
from ..domain.maintenance import MaintenanceLockContext, is_maintenance_locked


def get_data_root_status() -> Dict[str, Any]:
    active_root = DataRootManager.resolve_active_root()
    health = audit_data_root(active_root)
    locked, op_name = is_maintenance_locked()

    return {
        "active_root": str(active_root),
        "database_path": str(DataRootManager.get_database_path(active_root)),
        "people_dir": str(DataRootManager.get_people_dir(active_root)),
        "backups_dir": str(DataRootManager.get_backups_dir(active_root)),
        "config_dir": str(DataRootManager.get_config_dir(active_root)),
        "read_only": DataRootManager.is_read_only(active_root),
        "maintenance_locked": locked,
        "maintenance_operation": op_name,
        "health": health.to_dict(),
    }


def validate_active_data_root() -> Dict[str, Any]:
    health = audit_data_root()
    return health.to_dict()


def safe_repair_active_data_root() -> Dict[str, Any]:
    return safe_repair_data_root()


def move_data_root(destination_path: str) -> Dict[str, Any]:
    """Move active Data Root to a new directory/drive safely with copy-verify-switch staging."""
    active_root = DataRootManager.resolve_active_root()
    dest = Path(destination_path).resolve()

    if active_root in dest.parents or active_root == dest:
        raise DataRootDestinationConflictError("Destination path cannot be inside the current active Data Root.")

    if dest.exists() and any(dest.iterdir()):
        raise DataRootDestinationConflictError(f"Destination path '{dest}' already exists and is not empty.")

    with MaintenanceLockContext(f"MOVE_DATA_ROOT:{dest.name}"):
        # 1. Create Pre-Move Safety Backup
        safety_backup = create_backup(label=f"pre-move-{dest.name}", root=active_root)

        # 2. Stage Copy to Destination
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            str(active_root),
            str(dest),
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".tmp", "*.tmp", "__pycache__"),
        )

        # 3. Ensure structure & metadata in new location
        DataRootManager.ensure_structure(dest)

        # 4. Validate Staged Root
        staged_health = audit_data_root(dest)
        if not staged_health.ok:
            # Clean up copied destination on failure
            if dest.exists():
                try:
                    shutil.rmtree(str(dest))
                except Exception:
                    pass
            raise DataRootInvalidError(
                f"Moved data root failed health validation: {[i.message for i in staged_health.issues]}",
                detail={"issues": [i.to_dict() for i in staged_health.issues]},
            )

        # 5. Switch Bootstrap Pointer to New Location
        DataRootManager.set_active_root_pointer(dest)

        return {
            "ok": True,
            "previous_root": str(active_root),
            "new_root": str(dest),
            "safety_backup_id": safety_backup["id"],
            "health": staged_health.to_dict(),
        }


def switch_data_root(target_path: str) -> Dict[str, Any]:
    """Switch active data root pointer to an already-existing valid Data Root."""
    target = Path(target_path).resolve()
    if DataRootManager.is_backup_snapshot(target):
        raise DataRootInvalidError(
            f"Path '{target}' is a backup snapshot directory, not an active Data Root.",
            detail={"code": "BACKUP_SNAPSHOT_REJECTED"},
        )

    # Validate before switching
    DataRootManager.validate_data_root_structure(target)
    target_health = audit_data_root(target)

    if not target_health.database or target_health.database.integrity != "ok":
        raise DataRootInvalidError(f"Target data root at '{target}' has invalid database integrity.")

    with MaintenanceLockContext(f"SWITCH_DATA_ROOT:{target.name}"):
        DataRootManager.set_active_root_pointer(target)
        return {
            "ok": True,
            "active_root": str(target),
            "health": target_health.to_dict(),
        }
