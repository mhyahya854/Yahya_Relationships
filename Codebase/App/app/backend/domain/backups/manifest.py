"""Portable backup manifest creation and strict validation."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

from ... import config
from ...data_root.errors import BackupManifestInvalidError

BACKUP_KIND = "people-relationships-backup"
BACKUP_FORMAT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_NEW_REQUIRED = {
    "kind",
    "backup_format_version",
    "created_at",
    "category",
    "label",
    "sqlite_schema_version",
    "app_version",
    "data_root_format_version",
    "file_count",
    "total_size_bytes",
    "person_count",
    "journal_count",
    "files",
}
_LEGACY_REQUIRED = {
    "created_at",
    "file_count",
    "total_size_bytes",
    "person_count",
    "journal_count",
    "files",
}


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _database_metadata(database: Path) -> tuple[int, int]:
    connection = sqlite3.connect(str(database))
    try:
        person_count = int(connection.execute("SELECT COUNT(*) FROM people").fetchone()[0])
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'app_schema_version'"
        ).fetchone()
        schema_version = int(row[0]) if row else int(connection.execute("PRAGMA user_version").fetchone()[0])
        return person_count, schema_version
    finally:
        connection.close()


def build_backup_manifest(
    backup_dir: Path,
    label: str,
    source_root: Path,
    *,
    category: str,
    safety_reason: str | None,
    created_at: datetime | None = None,
) -> Dict[str, Any]:
    """Write a deterministic v1 manifest for a staged portable snapshot."""
    backup_dir = backup_dir.resolve()
    database = backup_dir / "data" / "family.db"
    person_count, schema_version = _database_metadata(database)
    journal_count = sum(1 for path in (backup_dir / "people").rglob("journal.md") if path.is_file())

    file_entries: List[Dict[str, Any]] = []
    for file_path in sorted(backup_dir.rglob("*"), key=lambda value: value.as_posix()):
        if file_path.is_symlink():
            raise BackupManifestInvalidError(
                f"Symbolic links are not allowed in backups: {file_path.relative_to(backup_dir).as_posix()}"
            )
        if file_path.is_file() and file_path.name != "manifest.json":
            file_entries.append(
                {
                    "path": file_path.relative_to(backup_dir).as_posix(),
                    "sha256": file_sha256(file_path),
                    "size_bytes": file_path.stat().st_size,
                }
            )

    manifest: Dict[str, Any] = {
        "kind": BACKUP_KIND,
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "created_at": (created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category": category,
        "safety_reason": safety_reason,
        "label": label,
        "sqlite_schema_version": schema_version,
        "schema_version": schema_version,
        "app_version": config.APP_VERSION,
        "data_root_format_version": 1,
        "file_count": len(file_entries),
        "total_size_bytes": sum(entry["size_bytes"] for entry in file_entries),
        "person_count": person_count,
        "journal_count": journal_count,
        # Informational only. Restore never reads this to choose a destination.
        "source_root": str(source_root.resolve()),
        "files": file_entries,
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _validated_relative_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw:
        raise BackupManifestInvalidError("Manifest contains an empty or non-portable file path.")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise BackupManifestInvalidError(f"Manifest contains an unsafe file path: {raw}")
    return path.as_posix()


def validate_backup_manifest(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise BackupManifestInvalidError("Manifest root must be an object.")

    legacy = "kind" not in data and data.get("format") == BACKUP_KIND
    kind = data.get("kind", data.get("format"))
    if kind != BACKUP_KIND:
        raise BackupManifestInvalidError("Manifest kind is not supported.")
    version = data.get("backup_format_version", 1 if legacy else None)
    if type(version) is not int or version != BACKUP_FORMAT_VERSION:
        raise BackupManifestInvalidError("Backup format version is not supported.")

    required = _LEGACY_REQUIRED if legacy else _NEW_REQUIRED
    missing = sorted(required.difference(data))
    if missing:
        raise BackupManifestInvalidError(f"Manifest is missing required keys: {', '.join(missing)}")
    if not legacy and data.get("category") not in {"manual", "automatic", "safety"}:
        raise BackupManifestInvalidError("Manifest category is invalid.")
    if not legacy and data.get("category") == "safety" and not isinstance(data.get("safety_reason"), str):
        raise BackupManifestInvalidError("Safety manifest is missing its safety reason.")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise BackupManifestInvalidError("Manifest files must be a non-empty array.")
    normalized_files: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise BackupManifestInvalidError("Every manifest file entry must be an object.")
        path = _validated_relative_path(entry.get("path"))
        folded = path.casefold()
        if folded in seen:
            raise BackupManifestInvalidError(f"Manifest contains a duplicate file path: {path}")
        seen.add(folded)
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise BackupManifestInvalidError(f"Manifest contains an invalid SHA-256 for {path}.")
        if type(size) is not int or size < 0:
            raise BackupManifestInvalidError(f"Manifest contains an invalid size for {path}.")
        normalized_files.append({"path": path, "sha256": digest.lower(), "size_bytes": size})

    if "data/family.db" not in {entry["path"] for entry in normalized_files}:
        raise BackupManifestInvalidError("Manifest does not include data/family.db.")
    for key in ("file_count", "total_size_bytes", "person_count", "journal_count", "sqlite_schema_version"):
        value = data.get(key)
        if key == "sqlite_schema_version" and legacy and value is None:
            continue
        if type(value) is not int or value < 0:
            raise BackupManifestInvalidError(f"Manifest {key} must be a non-negative integer.")
    if data["file_count"] != len(normalized_files):
        raise BackupManifestInvalidError("Manifest file_count does not match files array.")
    if data["total_size_bytes"] != sum(entry["size_bytes"] for entry in normalized_files):
        raise BackupManifestInvalidError("Manifest total_size_bytes does not match file entries.")

    normalized = dict(data)
    normalized["kind"] = BACKUP_KIND
    normalized["backup_format_version"] = version
    normalized["files"] = normalized_files
    normalized["legacy"] = legacy
    return normalized


def read_backup_manifest(backup_dir: Path) -> Dict[str, Any]:
    manifest_file = backup_dir.resolve() / "manifest.json"
    if not manifest_file.is_file():
        raise BackupManifestInvalidError(f"No manifest.json found at '{backup_dir}'.")
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupManifestInvalidError(f"Failed to parse manifest: {exc}") from exc
    return validate_backup_manifest(data)
