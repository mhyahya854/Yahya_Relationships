"""Backup Verification System."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from ...data_root.errors import (
    BackupDatabaseInvalidError,
    BackupHashMismatchError,
    BackupManifestInvalidError,
)
from ...data_root.manager import DataRootManager
from .manifest import file_sha256, read_backup_manifest


def verify_backup(backup_dir: str | Path, root: Path | None = None) -> Dict[str, Any]:
    """Verify backup files, SHA-256 hashes, and SQLite integrity."""
    if isinstance(backup_dir, str):
        active_root = root.resolve() if root else DataRootManager.resolve_active_root()
        candidate = Path(backup_dir)
        if not candidate.is_absolute() and not candidate.exists():
            backup_path = DataRootManager.get_backups_dir(active_root) / backup_dir
        else:
            backup_path = candidate
    else:
        backup_path = backup_dir

    backup_path = backup_path.resolve()
    if not backup_path.exists() or not backup_path.is_dir():
        return {
            "ok": False,
            "status": "corrupted",
            "error": f"Backup directory '{backup_path}' does not exist.",
        }

    try:
        manifest = read_backup_manifest(backup_path)
    except BackupManifestInvalidError as exc:
        return {
            "ok": False,
            "status": "corrupted",
            "error": str(exc),
        }

    issues: List[str] = []

    # 1. Verify files and SHA-256 hashes
    for entry in manifest.get("files", []):
        rel_path = entry["path"]
        expected_hash = entry["sha256"]
        f_path = backup_path / rel_path

        if not f_path.exists():
            issues.append(f"Missing file: {rel_path}")
            continue

        actual_hash = file_sha256(f_path)
        if actual_hash != expected_hash:
            issues.append(f"Hash mismatch for {rel_path} (expected {expected_hash[:8]}, got {actual_hash[:8]})")

    # 2. Verify SQLite Database Integrity
    db_path = DataRootManager.get_database_path(backup_path)
    db_integrity = "missing"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            db_integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if db_integrity != "ok":
                issues.append(f"Database integrity check failed: {db_integrity}")
        except Exception as exc:
            db_integrity = f"error: {exc}"
            issues.append(f"Failed to open database: {exc}")
    else:
        issues.append("Database file missing in backup.")

    is_ok = len(issues) == 0 and db_integrity == "ok"
    return {
        "ok": is_ok,
        "status": "ok" if is_ok else "corrupted",
        "manifest": manifest,
        "db_integrity": db_integrity,
        "issues": issues,
    }
