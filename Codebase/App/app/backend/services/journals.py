"""Per-person Markdown journals.

``journal.md`` is the canonical prose source. Reads always re-check the file
so external editors (VS Code, Obsidian, Notepad) are honoured; writes use an
atomic replace and refuse to clobber a file that changed since it was read.
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .. import config, db
from . import errors


def _read_text(path: Path) -> tuple[str, str, str]:
    content = path.read_text(encoding="utf-8")
    stat = path.stat()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, str(int(stat.st_mtime_ns)), digest


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".journal-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
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


def _ensure_journal_path(person_id: str) -> Path:
    if not person_id or not person_id.replace("_", "").replace("-", "").isalnum():
        raise errors.ValidationError(f"Unsafe person id: {person_id!r}")
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT id, name FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        return db.ensure_journal(connection, person_id)
    finally:
        connection.close()


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
    expected_modified_ns: str | None = None,
    expected_sha256: str | None = None,
    origin: str = "user",
) -> dict:
    path = _ensure_journal_path(person_id)
    if path.exists():
        current, modified_ns, digest = _read_text(path)
        changed_externally = False
        if expected_sha256 is not None and digest != expected_sha256:
            changed_externally = True
        elif (
            expected_modified_ns is not None
            and modified_ns != expected_modified_ns
            and digest != expected_sha256
        ):
            changed_externally = True
        if changed_externally:
            raise errors.JournalConflictError(
                "journal.md changed on disk since it was last read. "
                "Reload the file and merge before saving again.",
                details={
                    "path": str(path),
                    "current_sha256": digest,
                    "expected_sha256": expected_sha256,
                },
            )
    _atomic_write(path, content)
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
    content = current["content"].rstrip("\n")
    if content:
        content += "\n"
    if not content.endswith(f"## {section}\n"):
        content += f"\n## {section}\n\n"
    content += entry.replace("\r\n", "\n").strip("\n") + "\n"
    return save_journal(
        person_id,
        content,
        expected_sha256=current["sha256"],
        origin=origin,
    )


def journal_summaries() -> list[dict]:
    """Lightweight in-memory journal scan (single-user scale)."""
    config.ensure_root_dirs()
    results = []
    if not config.PEOPLE_DIR.exists():
        return results
    connection = db.get_connection()
    try:
        names = {
            row["id"]: row["name"]
            for row in connection.execute("SELECT id, name FROM people")
        }
    finally:
        connection.close()
    for journal in config.PEOPLE_DIR.rglob("journal.md"):
        person_id = journal.parent.name
        if person_id not in names:
            continue
        try:
            content = journal.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        results.append(
            {
                "person_id": person_id,
                "name": names[person_id],
                "path": str(journal),
                "modified_ns": str(int(journal.stat().st_mtime_ns)),
                "content": content,
            }
        )
    return results
