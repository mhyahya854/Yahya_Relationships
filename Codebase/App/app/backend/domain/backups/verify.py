"""Complete deterministic backup verification."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from ... import config
from ...data_root.errors import BackupManifestInvalidError
from ...data_root.manager import DataRootManager
from .manifest import file_sha256, read_backup_manifest


def _issue(code: str, message: str, path: str | None = None) -> Dict[str, str]:
    value = {"code": code, "message": message}
    if path is not None:
        value["path"] = path
    return value


def _base_result(path: Path) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "corrupted",
        "issues": [],
        "manifest": None,
        "db_integrity": "not_checked",
        "compatibility": {
            "ok": False,
            "status": "unknown",
            "backup_schema": None,
            "current_schema": config.APP_SCHEMA_VERSION,
        },
        "path": str(path),
    }


def verify_backup(backup_dir: str | Path, root: Path | None = None) -> Dict[str, Any]:
    """Verify manifest, payload, SQLite integrity, counts, and compatibility."""
    if isinstance(backup_dir, str):
        candidate = Path(backup_dir)
        if not candidate.is_absolute() and candidate.parent == Path("."):
            active_root = root.resolve() if root else DataRootManager.resolve_active_root()
            candidate = DataRootManager.get_backups_dir(active_root) / backup_dir
    else:
        candidate = backup_dir
    backup_path = candidate.resolve()
    result = _base_result(backup_path)
    issues: List[Dict[str, str]] = result["issues"]
    if not backup_path.is_dir():
        issues.append(_issue("BACKUP_NOT_FOUND", "Backup directory does not exist."))
        return result

    try:
        manifest = read_backup_manifest(backup_path)
    except BackupManifestInvalidError as exc:
        issues.append(_issue("BACKUP_MANIFEST_INVALID", str(exc)))
        return result
    result["manifest"] = manifest

    actual_files: set[str] = set()
    for item in sorted(backup_path.rglob("*"), key=lambda value: value.as_posix()):
        relative = item.relative_to(backup_path).as_posix()
        if item.is_symlink():
            issues.append(_issue("BACKUP_SYMLINK_UNSAFE", "Backup payload contains a symbolic link.", relative))
        elif item.is_file() and relative != "manifest.json":
            actual_files.add(relative)

    expected_files = {entry["path"] for entry in manifest["files"]}
    for unexpected in sorted(actual_files - expected_files):
        issues.append(_issue("BACKUP_UNEXPECTED_FILE", "Unexpected payload file is not in manifest.", unexpected))
    for entry in manifest["files"]:
        relative = entry["path"]
        file_path = backup_path.joinpath(*relative.split("/"))
        try:
            file_path.resolve().relative_to(backup_path)
        except ValueError:
            issues.append(_issue("BACKUP_PATH_UNSAFE", "Manifest path escapes the backup root.", relative))
            continue
        if relative not in actual_files:
            issues.append(_issue("BACKUP_MISSING_FILE", "Manifest payload file is missing.", relative))
            continue
        actual_size = file_path.stat().st_size
        if actual_size != entry["size_bytes"]:
            issues.append(_issue("BACKUP_SIZE_MISMATCH", "Payload size does not match manifest.", relative))
            continue
        if file_sha256(file_path) != entry["sha256"]:
            issues.append(_issue("BACKUP_HASH_MISMATCH", "Payload hash does not match manifest.", relative))

    for required_dir in ("people", "config"):
        if not (backup_path / required_dir).is_dir():
            issues.append(_issue("BACKUP_COMPONENT_MISSING", f"Required {required_dir} directory is missing.", required_dir))

    database = backup_path / "data" / "family.db"
    db_integrity = "missing"
    database_schema: int | None = None
    person_count: int | None = None
    if database.is_file() and "data/family.db" in actual_files:
        try:
            connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
            try:
                db_integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                person_count = int(connection.execute("SELECT COUNT(*) FROM people").fetchone()[0])
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'app_schema_version'"
                ).fetchone()
                database_schema = int(row[0]) if row else int(connection.execute("PRAGMA user_version").fetchone()[0])
            finally:
                connection.close()
        except Exception as exc:
            db_integrity = "error"
            issues.append(_issue("BACKUP_DB_INVALID", f"SQLite database could not be validated: {exc}"))
    else:
        issues.append(_issue("BACKUP_DB_INVALID", "Required SQLite database is missing."))
    result["db_integrity"] = db_integrity
    if db_integrity not in ("ok", "missing", "error"):
        issues.append(_issue("BACKUP_DB_INVALID", f"SQLite integrity check failed: {db_integrity}"))

    manifest_schema = manifest.get("sqlite_schema_version")
    if database_schema is not None and manifest_schema != database_schema:
        issues.append(_issue("BACKUP_SCHEMA_MISMATCH", "Manifest schema does not match the database schema."))
    compatibility_ok = database_schema is not None and 1 <= database_schema <= config.APP_SCHEMA_VERSION
    compatibility_status = "supported" if compatibility_ok else "unknown"
    if database_schema is not None and database_schema > config.APP_SCHEMA_VERSION:
        compatibility_status = "too_new"
        issues.append(_issue("BACKUP_SCHEMA_TOO_NEW", "Backup schema is newer than this application supports."))
    elif database_schema is not None and database_schema < 1:
        compatibility_status = "unsupported"
        issues.append(_issue("BACKUP_SCHEMA_UNSUPPORTED", "Backup schema has no supported migration path."))
    result["compatibility"] = {
        "ok": compatibility_ok,
        "status": compatibility_status,
        "backup_schema": database_schema,
        "current_schema": config.APP_SCHEMA_VERSION,
    }

    if person_count is not None and person_count != manifest["person_count"]:
        issues.append(_issue("BACKUP_PERSON_COUNT_MISMATCH", "Database person count does not match manifest."))
    journal_count = sum(1 for path in (backup_path / "people").rglob("journal.md") if path.is_file())
    if journal_count != manifest["journal_count"]:
        issues.append(_issue("BACKUP_JOURNAL_COUNT_MISMATCH", "Journal count does not match manifest."))

    result["ok"] = not issues and db_integrity == "ok" and compatibility_ok
    result["status"] = "verified" if result["ok"] else (
        "incompatible" if compatibility_status in {"too_new", "unsupported"} else "corrupted"
    )
    result["files_checked"] = len(expected_files)
    return result
