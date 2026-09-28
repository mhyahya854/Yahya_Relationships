"""Canonical backup discovery and safe ID resolution."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from ...data_root.errors import BackupError
from ...data_root.manager import DataRootManager


def native_io_path(path: Path) -> Path:
    """Return a Windows extended-length path without resolving symlinks.

    Backup payloads include intentionally descriptive directory names.  Their
    fully qualified paths can exceed the legacy MAX_PATH limit, especially in
    test roots and restored snapshots.  The prefix is a transport detail only;
    manifests continue to contain portable POSIX-relative paths.
    """
    if os.name != "nt":
        return path
    raw = os.path.abspath(str(path))
    if raw.startswith("\\\\?\\"):
        return Path(raw)
    if raw.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + raw[2:])
    return Path("\\\\?\\" + raw)


def sqlite_read_only_uri(path: Path) -> str:
    """Build a read-only SQLite URI that also accepts Windows long paths."""
    native = native_io_path(path)
    return f"file:{quote(str(native), safe=':/')}?mode=ro"


def remove_tree(path: Path, *, ignore_errors: bool = False) -> None:
    """Remove a directory tree using extended-length paths on Windows."""
    shutil.rmtree(native_io_path(path), ignore_errors=ignore_errors)


def iter_backup_directories(root: Path) -> Iterator[Path]:
    backups = DataRootManager.get_backups_dir(root).resolve()
    if not backups.is_dir():
        return
    for item in sorted(backups.iterdir(), key=lambda value: value.name.casefold()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        if item.name in {"Manual", "Automatic"}:
            for backup in sorted(item.iterdir(), key=lambda value: value.name.casefold()):
                if backup.is_dir() and not backup.name.startswith("."):
                    yield backup
        elif item.name == "Safety":
            for reason in sorted(item.iterdir(), key=lambda value: value.name.casefold()):
                if not reason.is_dir() or reason.name.startswith("."):
                    continue
                for backup in sorted(reason.iterdir(), key=lambda value: value.name.casefold()):
                    if backup.is_dir() and not backup.name.startswith("."):
                        yield backup
        else:
            # Pre-category snapshots remain in place and are treated as Legacy.
            yield item


def classify_backup_path(path: Path, root: Path) -> tuple[str, str | None]:
    backups = DataRootManager.get_backups_dir(root).resolve()
    relative = path.resolve().relative_to(backups)
    if relative.parts[0] == "Manual":
        return "manual", None
    if relative.parts[0] == "Automatic":
        return "automatic", None
    if relative.parts[0] == "Safety" and len(relative.parts) >= 3:
        reason = relative.parts[1].replace("-", "_").lower()
        return "safety", reason
    return "legacy", None


def resolve_backup_reference(reference: str | Path, root: Path, *, allow_path: bool = False) -> Path:
    """Resolve an opaque public ID, or an explicit path for trusted internal callers."""
    backups = DataRootManager.get_backups_dir(root).resolve()
    if isinstance(reference, Path) or allow_path:
        candidate = Path(reference).resolve()
        return candidate

    if not reference or Path(reference).is_absolute() or "/" in reference or "\\" in reference or reference in {".", ".."}:
        raise BackupError("Backup ID is not a safe opaque identifier.", code="BACKUP_ID_INVALID")
    matches = [path for path in iter_backup_directories(root) if path.name == reference]
    if len(matches) != 1:
        code = "BACKUP_NOT_FOUND" if not matches else "BACKUP_ID_AMBIGUOUS"
        raise BackupError("Backup ID could not be resolved uniquely.", code=code)
    return matches[0].resolve()
