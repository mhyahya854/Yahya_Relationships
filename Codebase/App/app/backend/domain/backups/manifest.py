"""Backup Manifest Utilities."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ...data_root.errors import BackupManifestInvalidError
from ...data_root.manager import DataRootManager


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def build_backup_manifest(
    backup_dir: Path,
    label: str,
    source_root: Path,
) -> Dict[str, Any]:
    """Generate manifest.json with normalized relative paths and SHA-256 hashes."""
    backup_dir = backup_dir.resolve()
    db_path = DataRootManager.get_database_path(backup_dir)

    person_count = 0
    journal_count = 0
    schema_ver = 1

    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            person_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            s_row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'app_schema_version'"
            ).fetchone()
            if s_row:
                schema_ver = int(s_row["value"])
            conn.close()
        except Exception:
            pass

    people_dir = DataRootManager.get_people_dir(backup_dir)
    if people_dir.exists():
        journal_count = len(list(people_dir.rglob("journal.md")))

    file_entries: List[Dict[str, Any]] = []
    total_bytes = 0

    for file_path in backup_dir.rglob("*"):
        if file_path.is_file() and file_path.name != "manifest.json":
            rel_path = file_path.relative_to(backup_dir).as_posix()
            size = file_path.stat().st_size
            total_bytes += size
            file_entries.append(
                {
                    "path": rel_path,
                    "sha256": file_sha256(file_path),
                    "size_bytes": size,
                }
            )

    manifest = {
        "kind": "people-relationships-backup",
        "backup_format_version": 1,
        "app_version": "1.0.0",
        "data_root_format_version": 1,
        "sqlite_schema_version": schema_ver,
        "schema_version": schema_ver,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label": label,
        "file_count": len(file_entries),
        "total_size_bytes": total_bytes,
        "person_count": person_count,
        "journal_count": journal_count,
        "source_root": str(source_root.resolve()),
        "files": file_entries,
    }

    manifest_file = backup_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def read_backup_manifest(backup_dir: Path) -> Dict[str, Any]:
    manifest_file = backup_dir.resolve() / "manifest.json"
    if not manifest_file.exists():
        raise BackupManifestInvalidError(f"No manifest.json found at '{backup_dir}'.")
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "files" not in data:
            raise BackupManifestInvalidError("Invalid manifest structure.")
        return data
    except Exception as exc:
        raise BackupManifestInvalidError(f"Failed to parse manifest: {exc}") from exc
