"""Backup Creation Engine."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ...data_root.manager import DataRootManager
from .manifest import build_backup_manifest
from .verify import verify_backup


def _clean_slug(text: str) -> str:
    clean = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text.strip().lower())
    return clean.strip("_") or "snapshot"


def create_backup(
    label: str = "manual",
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create a complete, verifiable snapshot backup of active data root."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    backups_dir = DataRootManager.get_backups_dir(active_root)
    backups_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    clean_label = _clean_slug(label)
    backup_id = f"backup-{stamp}-{clean_label}"
    dest_dir = backups_dir / backup_id

    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy SQLite database
    db_src = DataRootManager.get_database_path(active_root)
    if db_src.exists():
        db_dest_dir = dest_dir / "data"
        db_dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(db_src), str(db_dest_dir / "family.db"))

    # 2. Copy people directory
    people_src = DataRootManager.get_people_dir(active_root)
    if people_src.exists():
        shutil.copytree(
            str(people_src),
            str(dest_dir / "people"),
            ignore=shutil.ignore_patterns(".tmp", "*.tmp", "__pycache__"),
        )

    # 3. Copy config directory
    config_src = DataRootManager.get_config_dir(active_root)
    if config_src.exists():
        shutil.copytree(
            str(config_src),
            str(dest_dir / "config"),
            ignore=shutil.ignore_patterns("*.tmp"),
        )

    # 4. Generate Manifest
    manifest = build_backup_manifest(dest_dir, label, active_root)

    # 5. Verify Backup
    verification = verify_backup(dest_dir)

    return {
        "id": backup_id,
        "name": backup_id,
        "kind": "people-relationships-backup",
        "path": str(dest_dir),
        "manifest": manifest,
        "verification": verification,
    }
