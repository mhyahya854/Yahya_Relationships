"""Atomic, SQLite-safe backup creation."""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from ...data_root.errors import BackupError, DataRootReadOnlyError
from ...data_root.manager import DataRootManager
from ..maintenance import MaintenanceLockContext
from .manifest import build_backup_manifest
from .verify import verify_backup


class BackupCategory(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    SAFETY = "safety"


class SafetyReason(str, Enum):
    PRE_RESTORE = "pre_restore"
    PRE_UPGRADE = "pre_upgrade"
    PRE_ORGANIZATION = "pre_organization"
    PRE_REPAIR = "pre_repair"


_CATEGORY_DIRS = {
    BackupCategory.MANUAL: ("Manual",),
    BackupCategory.AUTOMATIC: ("Automatic",),
}
_SAFETY_DIRS = {
    SafetyReason.PRE_RESTORE: "Pre-Restore",
    SafetyReason.PRE_UPGRADE: "Pre-Upgrade",
    SafetyReason.PRE_ORGANIZATION: "Pre-Organization",
    SafetyReason.PRE_REPAIR: "Pre-Repair",
}


def _clean_slug(text: str) -> str:
    clean = "".join(c.lower() if c.isalnum() else "-" for c in text.strip())
    return "-".join(part for part in clean.split("-") if part)[:60] or "snapshot"


def _category_dir(
    backups_dir: Path,
    category: BackupCategory,
    safety_reason: SafetyReason | None,
) -> Path:
    if category is BackupCategory.SAFETY:
        if safety_reason is None:
            raise BackupError("Safety backups require a safety reason.", code="BACKUP_CATEGORY_INVALID")
        return backups_dir / "Safety" / _SAFETY_DIRS[safety_reason]
    if safety_reason is not None:
        raise BackupError("A safety reason is valid only for safety backups.", code="BACKUP_CATEGORY_INVALID")
    return backups_dir.joinpath(*_CATEGORY_DIRS[category])


def _is_temporary(path: Path) -> bool:
    return (
        "__pycache__" in path.parts
        or path.name.endswith(".tmp")
        or (path.name.startswith(".journal-") and path.name.endswith(".tmp"))
    )


def _copy_tree_safe(source: Path, destination: Path) -> None:
    """Copy a tree without following links or copying known temporary files."""
    destination.mkdir(parents=True, exist_ok=False)
    for item in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
        relative = item.relative_to(source)
        if _is_temporary(relative):
            continue
        if item.is_symlink():
            raise BackupError(
                f"Backup input contains an unsupported symbolic link: {relative.as_posix()}",
                code="BACKUP_SYMLINK_UNSAFE",
            )
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError("The active SQLite database is missing.", code="BACKUP_DATABASE_MISSING")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(str(source))
    destination_connection = sqlite3.connect(str(destination))
    try:
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise BackupError(
                f"SQLite snapshot integrity check failed: {integrity}",
                code="BACKUP_DATABASE_INVALID",
            )
    finally:
        destination_connection.close()
        source_connection.close()


def create_backup(
    label: str = "Snapshot",
    category: BackupCategory | str = BackupCategory.MANUAL,
    safety_reason: SafetyReason | str | None = None,
    root: Optional[Path] = None,
    *,
    _maintenance_held: bool = False,
) -> Dict[str, Any]:
    """Create, verify, then atomically publish a portable snapshot."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    category = BackupCategory(category)
    reason = SafetyReason(safety_reason) if safety_reason is not None else None
    if DataRootManager.is_read_only(active_root):
        raise DataRootReadOnlyError("Data root is read-only; a backup cannot be created.")

    backups_dir = DataRootManager.get_backups_dir(active_root)
    destination_parent = _category_dir(backups_dir, category, reason)
    destination_parent.mkdir(parents=True, exist_ok=True)
    display_label = (label or "Snapshot").strip() or "Snapshot"
    created = datetime.now(timezone.utc)
    backup_id = (
        f"backup-{created.strftime('%Y%m%dT%H%M%S%f')[:-3]}Z-"
        f"{uuid.uuid4().hex[:8]}-{_clean_slug(display_label)}"
    )
    final_dir = destination_parent / backup_id
    staging_dir = destination_parent / f".backup_staging_{uuid.uuid4().hex}"

    lock = nullcontext() if _maintenance_held else MaintenanceLockContext("CREATE_BACKUP")
    with lock:
        try:
            staging_dir.mkdir(parents=True, exist_ok=False)
            _snapshot_sqlite(
                DataRootManager.get_database_path(active_root),
                staging_dir / "data" / "family.db",
            )
            people_source = DataRootManager.get_people_dir(active_root)
            if not people_source.is_dir():
                raise BackupError("The active People directory is missing.", code="BACKUP_PEOPLE_MISSING")
            _copy_tree_safe(people_source, staging_dir / "people")

            config_source = DataRootManager.get_config_dir(active_root)
            if config_source.exists():
                _copy_tree_safe(config_source, staging_dir / "config")
            else:
                (staging_dir / "config").mkdir()

            manifest = build_backup_manifest(
                staging_dir,
                display_label,
                active_root,
                category=category.value,
                safety_reason=reason.value if reason else None,
                created_at=created,
            )
            verification = verify_backup(staging_dir)
            if not verification["ok"]:
                raise BackupError(
                    "Backup verification failed before publication.",
                    code="BACKUP_VERIFICATION_FAILED",
                    detail=verification,
                )
            if final_dir.exists():
                raise BackupError("Backup ID collision; refusing to overwrite.", code="BACKUP_ID_COLLISION")
            staging_dir.rename(final_dir)
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    return {
        "id": backup_id,
        "name": backup_id,
        "kind": "people-relationships-backup",
        "category": category.value,
        "safety_reason": reason.value if reason else None,
        "path": str(final_dir),
        "files": manifest["file_count"],
        "manifest": manifest,
        "verification": verification,
    }
