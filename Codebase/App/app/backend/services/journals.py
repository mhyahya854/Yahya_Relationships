"""Per-person Markdown journals.

``journal.md`` is the canonical prose source. Reads always re-check the file
so external editors (VS Code, Obsidian, Notepad) are honoured; writes use an
atomic replace and refuse to clobber a file that changed since it was read.
"""

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .. import config, db
from . import errors


def _normalize_lf(content: str) -> str:
    return str(content).replace("\r\n", "\n").replace("\r", "\n")


def _read_text(path: Path) -> tuple[str, str, str]:
    raw = path.read_bytes()
    content = raw.decode("utf-8")
    stat = path.stat()
    digest = hashlib.sha256(raw).hexdigest()
    return content, str(int(stat.st_mtime_ns)), digest


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".journal-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_normalize_lf(content))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _resolve_journal_path_readonly(person_id: str) -> tuple[Path, bool]:
    if not person_id or not person_id.replace("_", "").replace("-", "").isalnum():
        raise errors.ValidationError(f"Unsafe person id: {person_id!r}")
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT id, name FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        return db.find_journal_path(connection, person_id)
    finally:
        connection.close()


def _check_write_allowed() -> None:
    from ..data_root.errors import DataRootReadOnlyError
    from ..data_root.manager import DataRootManager
    from ..domain.maintenance import check_maintenance_lock

    check_maintenance_lock()
    if DataRootManager.is_read_only():
        raise DataRootReadOnlyError()


def _conflict(path: Path, expected_exists: bool | None) -> errors.JournalConflictError:
    exists = path.is_file()
    content = ""
    modified_ns = None
    digest = None
    if exists:
        content, modified_ns, digest = _read_text(path)
    return errors.JournalConflictError(
        "journal.md changed on disk since it was last read. Resolve the conflict before saving.",
        details={
            "path": str(path),
            "expected_exists": expected_exists,
            "current_exists": exists,
            "current_content": content,
            "current_sha256": digest,
            "current_modified_ns": modified_ns,
        },
    )


def read_journal(person_id: str) -> dict:
    path, exists = _resolve_journal_path_readonly(person_id)
    if not exists or not path.exists():
        return {
            "person_id": person_id,
            "path": str(path),
            "content": "",
            "modified_ns": None,
            "sha256": None,
            "exists": False,
        }
    content, modified_ns, digest = _read_text(path)
    return {
        "person_id": person_id,
        "path": str(path),
        "content": content,
        "modified_ns": modified_ns,
        "sha256": digest,
        "exists": True,
    }


def save_journal(
    person_id: str,
    content: str,
    *,
    expected_exists: bool | None = None,
    expected_modified_ns: str | None = None,
    expected_sha256: str | None = None,
    force: bool = False,
    origin: str = "user",
) -> dict:
    path, current_exists = _resolve_journal_path_readonly(person_id)
    _check_write_allowed()

    if not force:
        inferred_expected_exists = expected_exists
        if inferred_expected_exists is None and expected_sha256 is not None:
            inferred_expected_exists = True
        if (
            inferred_expected_exists is not None
            and current_exists != inferred_expected_exists
        ):
            raise _conflict(path, inferred_expected_exists)
        if current_exists:
            _, modified_ns, digest = _read_text(path)
            if expected_sha256 is not None and digest != expected_sha256:
                raise _conflict(path, inferred_expected_exists)
            if (
                expected_sha256 is None
                and expected_modified_ns is not None
                and modified_ns != expected_modified_ns
            ):
                raise _conflict(path, inferred_expected_exists)
        elif expected_sha256 is not None or expected_modified_ns is not None:
            raise _conflict(path, inferred_expected_exists)

    _atomic_write(path, _normalize_lf(content))
    result = read_journal(person_id)
    result["saved"] = True
    return result


def append_journal(
    person_id: str,
    entry: str,
    *,
    heading: str | None = None,
    origin: str = "user",
) -> dict:
    entry = str(entry).strip()
    if not entry:
        raise errors.ValidationError("Journal entry text is required.")
    current = read_journal(person_id)
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    section = heading or today
    section = str(section).strip()
    if section.startswith("## "):
        section = section[3:].strip()
    if not section or "\n" in section or "\r" in section:
        raise errors.ValidationError("Journal entry heading must be one non-empty line.")
    content = _normalize_lf(current["content"]).rstrip("\n")
    heading_line = f"## {section}"
    has_heading = heading_line in content.splitlines()
    if content:
        content += "\n\n"
    if not has_heading:
        content += heading_line + "\n\n"
    content += _normalize_lf(entry).strip("\n") + "\n"
    return save_journal(
        person_id,
        content,
        expected_exists=current["exists"],
        expected_modified_ns=current["modified_ns"],
        expected_sha256=current["sha256"],
        origin=origin,
    )


def journal_summaries() -> list[dict]:
    """Lightweight in-memory journal scan (single-user scale)."""
    results = []
    people_dir = config.PEOPLE_DIR
    if not people_dir.exists():
        return results
    connection = db.get_connection()
    try:
        candidates = []
        for row in connection.execute("SELECT id, name FROM people ORDER BY id"):
            path, exists = db.find_journal_path(connection, row["id"])
            if exists:
                candidates.append((row["id"], row["name"], path))
    finally:
        connection.close()
    for person_id, name, journal in candidates:
        try:
            content, modified_ns, _ = _read_text(journal)
        except (OSError, UnicodeDecodeError):
            continue
        results.append(
            {
                "person_id": person_id,
                "name": name,
                "path": str(journal),
                "modified_ns": modified_ns,
                "content": content,
            }
        )
    return results
