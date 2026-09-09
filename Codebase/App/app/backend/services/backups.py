"""Safe backup application service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..data_root.manager import DataRootManager
from ..domain.backups import create_backup, restore_backup
from ..domain.backups import verify_backup as _verify_backup
from ..domain.backups.paths import (
    classify_backup_path,
    iter_backup_directories,
    resolve_backup_reference,
)


def _backup_info(path: Path, root: Path) -> Dict[str, Any]:
    category, reason = classify_backup_path(path, root)
    verification = _verify_backup(path)
    manifest = verification.get("manifest") or {}
    return {
        "id": path.name,
        "name": path.name,
        "category": manifest.get("category", category),
        "safety_reason": manifest.get("safety_reason", reason),
        "timestamp": manifest.get("created_at", ""),
        "created": manifest.get("created_at", ""),
        "label": manifest.get("label") or manifest.get("purpose") or "Snapshot",
        "app_version": manifest.get("app_version"),
        "backup_format_version": manifest.get("backup_format_version"),
        "schema_version": manifest.get("sqlite_schema_version"),
        "data_root_version": manifest.get("data_root_format_version"),
        "file_count": manifest.get("file_count", 0),
        "files": manifest.get("file_count", 0),
        "total_size_bytes": manifest.get("total_size_bytes", 0),
        "person_count": manifest.get("person_count", 0),
        "journal_count": manifest.get("journal_count", 0),
        "verified": verification["ok"],
        "integrity_status": verification["status"],
        "compatibility": verification["compatibility"],
        "has_manifest": (path / "manifest.json").is_file(),
        "path": str(path),
    }


def list_backups(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Discover canonical category snapshots plus unchanged legacy top-level snapshots."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    results = [_backup_info(path, active_root) for path in iter_backup_directories(active_root)]
    return sorted(results, key=lambda item: (item["created"], item["id"]), reverse=True)


def get_backup_details(backup_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    path = resolve_backup_reference(backup_id, active_root)
    info = _backup_info(path, active_root)
    info["verification"] = _verify_backup(path)
    info["replaces"] = ["SQLite database", "People folders and Journals", "portable Config"]
    return info


def execute_create_backup(label: str = "Snapshot", root: Optional[Path] = None) -> Dict[str, Any]:
    return create_backup(label=label or "Snapshot", category="manual", root=root)


def execute_verify_backup(backup_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    path = resolve_backup_reference(backup_id, active_root)
    return _verify_backup(path)


def verify_backup(backup_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Backward-compatible service entry point using safe ID resolution."""
    return execute_verify_backup(backup_id, root=root)


def execute_restore_backup(
    backup_id: str,
    confirmation_token: str = "RESTORE",
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    path = resolve_backup_reference(backup_id, active_root)
    return restore_backup(
        path,
        confirmation_token=confirmation_token,
        root=active_root,
        _allow_path=True,
    )
