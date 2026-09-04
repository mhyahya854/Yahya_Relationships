"""Backups Service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..data_root.manager import DataRootManager
from ..domain.backups import create_backup, read_backup_manifest, restore_backup, verify_backup


def list_backups(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all available local backups with verification status and metadata."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    backups_dir = DataRootManager.get_backups_dir(active_root)

    if not backups_dir.exists():
        return []

    results: List[Dict[str, Any]] = []
    for item in sorted(backups_dir.iterdir(), reverse=True):
        if item.is_dir() and not item.name.startswith("."):
            manifest_file = item / "manifest.json"
            if manifest_file.exists():
                try:
                    m = read_backup_manifest(item)
                    # Run lightweight verification check
                    v = verify_backup(item)
                    results.append({
                        "id": item.name,
                        "name": item.name,
                        "timestamp": m.get("created_at", ""),
                        "label": m.get("label", "Snapshot"),
                        "app_version": m.get("app_version", "1.0.0"),
                        "schema_version": m.get("sqlite_schema_version", 1),
                        "data_root_version": m.get("data_root_format_version", 1),
                        "file_count": m.get("file_count", 0),
                        "total_size_bytes": m.get("total_size_bytes", 0),
                        "person_count": m.get("person_count", 0),
                        "journal_count": m.get("journal_count", 0),
                        "verified": v["ok"],
                        "integrity_status": v["status"],
                        "path": str(item),
                    })
                except Exception:
                    results.append({
                        "id": item.name,
                        "name": item.name,
                        "timestamp": "",
                        "label": "Corrupted Snapshot",
                        "verified": False,
                        "integrity_status": "corrupted",
                        "path": str(item),
                    })
    return results


def get_backup_details(backup_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    backups_dir = DataRootManager.get_backups_dir(active_root)
    b_path = backups_dir / backup_id
    verification = verify_backup(b_path)
    return {
        "id": backup_id,
        "path": str(b_path),
        "verification": verification,
    }


def execute_create_backup(label: str = "manual", root: Optional[Path] = None) -> Dict[str, Any]:
    return create_backup(label=label, root=root)


def execute_verify_backup(backup_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    backups_dir = DataRootManager.get_backups_dir(active_root)
    b_path = backups_dir / backup_id
    return verify_backup(b_path)


def execute_restore_backup(
    backup_id: str,
    confirmation_token: str = "RESTORE",
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    return restore_backup(
        backup_id_or_path=backup_id,
        confirmation_token=confirmation_token,
        root=root,
    )
