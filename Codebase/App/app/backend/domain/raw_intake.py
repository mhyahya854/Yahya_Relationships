"""Phase 12's generic, local-only Raw intake foundation.

This module intentionally stops at safe intake orchestration.  It never
unpacks archives, calls an AI service, identifies a person, creates a media
event, or silently moves/deletes a source.  ``Raw/`` is treated as untrusted
input; SQLite is the structured authority and the Markdown history is a
recoverable human-readable projection of its event outbox.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import stat
import threading
import unicodedata
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from .. import db
from ..data_root.errors import DataRootError, DataRootReadOnlyError
from ..data_root.manager import DataRootManager

HASH_ALGORITHM = "sha256"
HASH_CHUNK_SIZE = 1024 * 1024
HISTORY_FILENAME = "raw_processing_history.md"
RAW_STAGING_PREFIX = ".raw_move_staging_"

CLASSIFICATIONS = {
    "image", "video", "audio", "document", "archive",
    "social_export_candidate", "location_export_candidate",
    "phone_backup_candidate", "folder/container", "unknown",
}
ENTRY_KINDS = {"file", "directory", "archive", "unknown"}
_RESERVED_WINDOWS = {
    "con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
_ROOT_LOCKS: dict[str, threading.RLock] = {}
_ROOT_LOCKS_GUARD = threading.Lock()
_RAW_FAILPOINT: str | None = None


class RawIntakeError(DataRootError):
    def __init__(self, message: str, code: str = "RAW_INTAKE_ERROR", detail: Any = None):
        super().__init__(message, code=code, detail=detail)


class SourceChangedError(RawIntakeError):
    def __init__(self, message: str = "Raw source changed while it was being read."):
        super().__init__(message, "RAW_SOURCE_CHANGED")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _failpoint(name: str) -> None:
    if _RAW_FAILPOINT == name:
        raise RuntimeError(f"Injected Phase 12 failure at failpoint: {name}")


def _root_lock(root: Path) -> threading.RLock:
    key = str(root.resolve()).casefold()
    with _ROOT_LOCKS_GUARD:
        return _ROOT_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    lock = _root_lock(root)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_component(component: str) -> str:
    normalized = unicodedata.normalize("NFC", component)
    if not normalized or normalized in {".", ".."}:
        raise RawIntakeError("Path contains an empty or traversal component.", "RAW_PATH_UNSAFE")
    if any(ord(char) < 32 for char in normalized) or "\x00" in normalized:
        raise RawIntakeError("Path contains a control character.", "RAW_PATH_UNSAFE")
    if normalized.rstrip(". ") != normalized:
        raise RawIntakeError("Path component has Windows-ambiguous trailing punctuation.", "RAW_PATH_UNSAFE")
    if normalized.split(".", 1)[0].casefold() in _RESERVED_WINDOWS:
        raise RawIntakeError("Path contains a reserved Windows device name.", "RAW_PATH_UNSAFE")
    return normalized


def validate_relative_path(raw: str, *, allowed_prefix: str | None = None) -> str:
    """Validate a portable, data-root-relative POSIX path.

    Backslashes, drives, absolute paths, traversal, controls, and Windows
    device aliases are rejected before anything reaches the filesystem.
    """
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise RawIntakeError("A portable relative path is required.", "RAW_PATH_UNSAFE")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RawIntakeError("Absolute or traversal paths are not allowed.", "RAW_PATH_UNSAFE")
    normalized = "/".join(_safe_component(part) for part in path.parts)
    if allowed_prefix and not (
        normalized == allowed_prefix or normalized.startswith(f"{allowed_prefix}/")
    ):
        raise RawIntakeError("Path is outside its permitted canonical area.", "RAW_PATH_OUTSIDE_ROOT")
    return normalized


def _within(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RawIntakeError("Resolved path escapes the Data Root.", "RAW_PATH_ESCAPE") from exc
    return resolved


def _ensure_no_link_ancestors(root: Path, candidate: Path) -> None:
    current = root.resolve()
    relative = candidate.relative_to(root)
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RawIntakeError("Symbolic links and junctions are not valid Raw paths.", "RAW_LINK_UNSAFE")


def raw_directory(root: Path | None = None, *, create: bool = False) -> Path:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    target = active_root / "Raw"
    if target.exists():
        if not target.is_dir() or target.is_symlink():
            raise RawIntakeError("Raw must be a real directory inside the Data Root.", "RAW_DIRECTORY_UNSAFE")
        return target
    if not create:
        return target
    if DataRootManager.is_read_only(active_root):
        raise DataRootReadOnlyError("Data root is read-only; Raw cannot be created.")
    target.mkdir(parents=False, exist_ok=False)
    return target


def history_path(root: Path) -> Path:
    return root / "Database" / HISTORY_FILENAME


def ensure_history_file(root: Path) -> Path:
    """Create only the human-readable projection file, never a Raw source."""
    path = history_path(root)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Mosaic Raw Processing History\n\n")
        handle.write("SQLite `relationships.db` is authoritative. This file is an append-oriented, recoverable human-readable projection.\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path


def _connection(root: Path):
    return db.get_connection(DataRootManager.get_database_path(root))


def _fingerprint(path: Path) -> dict[str, int | None]:
    data = path.stat()
    return {
        "size_bytes": int(data.st_size),
        "mtime_ns": int(data.st_mtime_ns),
        "device": getattr(data, "st_dev", None),
        "inode": getattr(data, "st_ino", None),
    }


def hash_file(path: Path) -> tuple[str, dict[str, int | None]]:
    """Stream SHA-256 and reject a result if the file changes underneath us."""
    before = _fingerprint(path)
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            hasher.update(chunk)
    after = _fingerprint(path)
    if before != after:
        raise SourceChangedError()
    return hasher.hexdigest(), after


def _signature_classification(path: Path, extension: str) -> tuple[str, str | None, float]:
    try:
        with path.open("rb") as handle:
            signature = handle.read(16)
    except OSError:
        raise
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png", 1.0
    if signature.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg", 1.0
    if signature.startswith(b"%PDF-"):
        return "document", "application/pdf", 1.0
    if signature.startswith(b"PK\x03\x04") or signature.startswith(b"PK\x05\x06"):
        return "archive", "application/zip", 1.0
    # Names cannot prove an export's contents, but they are useful deterministic
    # coarse candidates. Keep the candidate state visibly provisional rather
    # than treating a generic JSON/TXT extension as a confirmed document type.
    name = path.name.casefold()
    if any(token in name for token in ("whatsapp", "instagram", "snapchat", "messenger", "facebook")):
        return "social_export_candidate", mimetypes.types_map.get(extension.casefold()), 0.45
    if any(token in name for token in ("location", "timeline", "takeout", "gps", "places")):
        return "location_export_candidate", mimetypes.types_map.get(extension.casefold()), 0.45
    if any(token in name for token in ("backup", "iphone", "android", "dcim")):
        return "phone_backup_candidate", mimetypes.types_map.get(extension.casefold()), 0.4
    ext = extension.casefold()
    image = {".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
    video = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
    audio = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}
    document = {".pdf", ".txt", ".md", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".json", ".html", ".xml"}
    archive = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz"}
    if ext in image:
        return "image", mimetypes.types_map.get(ext, "image/*"), 0.7
    if ext in video:
        return "video", mimetypes.types_map.get(ext, "video/*"), 0.7
    if ext in audio:
        return "audio", mimetypes.types_map.get(ext, "audio/*"), 0.7
    if ext in document:
        return "document", mimetypes.types_map.get(ext, "application/octet-stream"), 0.65
    if ext in archive:
        return "archive", mimetypes.types_map.get(ext, "application/octet-stream"), 0.65
    return "unknown", mimetypes.types_map.get(ext), 0.0


def _archive_inventory(path: Path) -> dict[str, Any] | None:
    if path.suffix.casefold() != ".zip":
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        return {"safety_status": "MALFORMED", "error": str(exc), "members": []}
    sample: list[dict[str, Any]] = []
    unsafe = False
    compressed = 0
    uncompressed = 0
    for info in members:
        name = info.filename.replace("\\", "/")
        normalized = PurePosixPath(name)
        invalid = (
            normalized.is_absolute()
            or any(part in {"", ".", ".."} for part in normalized.parts)
            or any(ord(char) < 32 for char in name)
        )
        unsafe = unsafe or invalid
        compressed += int(info.compress_size)
        uncompressed += int(info.file_size)
        if len(sample) < 200:
            sample.append({"name": name, "size_bytes": int(info.file_size), "unsafe_path": invalid})
    suspicious_ratio = uncompressed > 0 and (compressed == 0 or uncompressed / max(compressed, 1) > 1000)
    suspicious_size = uncompressed > 4 * 1024 * 1024 * 1024
    status = "UNSAFE_PATH" if unsafe else "SUSPICIOUS" if suspicious_ratio or suspicious_size else "SAFE_METADATA_ONLY"
    return {
        "safety_status": status,
        "member_count": len(members),
        "compressed_bytes": compressed,
        "uncompressed_bytes": uncompressed,
        "members": sample,
    }


def _event(connection, item_id: str | None, event_type: str, payload: dict[str, Any]) -> str:
    event_id = uuid.uuid4().hex
    connection.execute(
        """INSERT INTO raw_processing_events
           (id, raw_item_id, event_type, payload_json, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (event_id, item_id, event_type, _json(payload), utc_now()),
    )
    return event_id


def _history_entry(event: Any) -> str:
    payload = _parse_json(event["payload_json"], {})
    lines = [
        f"## {event['created_at']} — {event['event_type']}",
        f"<!-- raw-event:{event['id']} -->",
    ]
    if event["raw_item_id"]:
        lines.append(f"- Item ID: `{event['raw_item_id']}`")
    for key in ("original_path", "current_path", "sha256", "classification", "proposal", "decision", "final_path", "error"):
        value = payload.get(key)
        if value is not None:
            lines.append(f"- {key.replace('_', ' ').title()}: `{value}`")
    remaining = {key: value for key, value in payload.items() if key not in {"original_path", "current_path", "sha256", "classification", "proposal", "decision", "final_path", "error"}}
    if remaining:
        lines.append(f"- Details: `{_json(remaining)}`")
    return "\n".join(lines) + "\n\n"


def flush_history(root: Path) -> int:
    """Atomically publish pending event rows and then acknowledge them.

    The stable HTML-style event marker makes a crash between filesystem publish
    and database acknowledgement idempotent: a retry sees the marker and does
    not append the event twice.
    """
    with _locked(root):
        connection = _connection(root)
        try:
            pending = connection.execute(
                "SELECT * FROM raw_processing_events WHERE history_written_at IS NULL ORDER BY created_at, id"
            ).fetchall()
            if not pending:
                return 0
            path = ensure_history_file(root)
            existing = path.read_text(encoding="utf-8")
            append = "".join(
                _history_entry(event)
                for event in pending
                if f"<!-- raw-event:{event['id']} -->" not in existing
            )
            if append:
                temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
                with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(existing)
                    handle.write(append)
                    handle.flush()
                    os.fsync(handle.fileno())
                _failpoint("history_before_replace")
                os.replace(temporary, path)
                _failpoint("history_after_replace")
            now = utc_now()
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "UPDATE raw_processing_events SET history_written_at = ? WHERE id = ? AND history_written_at IS NULL",
                [(now, event["id"]) for event in pending],
            )
            connection.commit()
            return len(pending)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _find_item(connection, relative_path: str):
    return connection.execute(
        "SELECT * FROM raw_items WHERE current_relative_path = ? COLLATE NOCASE",
        (relative_path,),
    ).fetchone()


def _new_item_id() -> str:
    return f"raw_{uuid.uuid4().hex}"


def _proposal_for(classification: str, *, now: str) -> tuple[str, str]:
    if classification in {"image", "video", "audio", "archive", "social_export_candidate", "location_export_candidate", "phone_backup_candidate"}:
        return "BLOCKED_BY_FUTURE_PHASE", "Canonical organization requires a later phase; the source stays in Raw."
    if classification == "folder/container":
        return "UNKNOWN", "Folder/container is recorded but no canonical destination is inferred."
    return "NEEDS_USER_INPUT", "A human may provide a currently-authorized Database/Sources destination."


def _write_proposal(connection, item_id: str, classification: str, fingerprint: dict[str, Any], *, now: str) -> None:
    state, reason = _proposal_for(classification, now=now)
    connection.execute(
        """INSERT INTO raw_proposals
           (id, raw_item_id, destination_relative_path, proposal_state, reason, source, source_fingerprint_json, stale, created_at, updated_at)
           VALUES (?, ?, NULL, ?, ?, 'deterministic', ?, 0, ?, ?)""",
        (uuid.uuid4().hex, item_id, state, reason, _json(fingerprint), now, now),
    )
    _event(connection, item_id, "PROPOSAL_CREATED", {"proposal": state, "reason": reason})


def _refresh_duplicate_group(connection, item_id: str, sha256: str | None, *, now: str) -> None:
    if not sha256:
        return
    group = connection.execute(
        "SELECT id FROM raw_duplicate_groups WHERE hash_algorithm = ? AND content_hash = ?",
        (HASH_ALGORITHM, sha256),
    ).fetchone()
    if group is None:
        group_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO raw_duplicate_groups (id, hash_algorithm, content_hash, created_at) VALUES (?, ?, ?, ?)",
            (group_id, HASH_ALGORITHM, sha256, now),
        )
    else:
        group_id = group["id"]
    connection.execute(
        "INSERT OR IGNORE INTO raw_duplicate_members (duplicate_group_id, raw_item_id) VALUES (?, ?)",
        (group_id, item_id),
    )


def _upsert_archive_inventory(connection, item_id: str, inventory: dict[str, Any] | None) -> None:
    if inventory is None:
        return
    connection.execute(
        """INSERT INTO raw_archive_inventory
          (raw_item_id, member_count, compressed_bytes, uncompressed_bytes, safety_status, inventory_json, inspected_at)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(raw_item_id) DO UPDATE SET
            member_count=excluded.member_count, compressed_bytes=excluded.compressed_bytes,
            uncompressed_bytes=excluded.uncompressed_bytes, safety_status=excluded.safety_status,
            inventory_json=excluded.inventory_json, inspected_at=excluded.inspected_at""",
        (
            item_id, inventory.get("member_count"), inventory.get("compressed_bytes"),
            inventory.get("uncompressed_bytes"), inventory["safety_status"],
            _json(inventory), utc_now(),
        ),
    )


def _relative_raw(root: Path, path: Path) -> str:
    return validate_relative_path(f"Raw/{path.relative_to(root / 'Raw').as_posix()}", allowed_prefix="Raw")


def _record_observation(
    connection,
    *,
    root: Path,
    path: Path,
    kind: str,
    run_id: str,
) -> str:
    now = utc_now()
    relative_path = _relative_raw(root, path)
    item = _find_item(connection, relative_path)
    extension = path.suffix.casefold() if kind != "directory" else None
    fingerprint: dict[str, Any] = {}
    sha256: str | None = None
    classification = "folder/container" if kind == "directory" else "unknown"
    classification_source = "deterministic"
    mime_type: str | None = None
    confidence: float | None = None
    archive_inventory: dict[str, Any] | None = None
    processing_state = "AWAITING_REVIEW"
    availability = "PRESENT"
    error: str | None = None
    try:
        if kind == "directory":
            fingerprint = _fingerprint(path)
        elif kind == "unknown":
            fingerprint = _fingerprint(path)
            availability = "UNSAFE_LINK"
            processing_state = "ERROR"
            error = "Symlink/junction was not followed."
        else:
            # The scanner is incremental: an unchanged regular file retains its
            # already verified digest rather than re-reading a huge payload.
            current_stat = _fingerprint(path)
            previous = _parse_json(item["fingerprint_json"], {}) if item is not None else {}
            if item is not None and previous == current_stat and item["sha256"] and item["hash_algorithm"] == HASH_ALGORITHM:
                fingerprint = current_stat
                sha256 = item["sha256"]
                classification = item["classification"]
                classification_source = item["classification_source"]
                mime_type = item["mime_type"]
                confidence = item["classification_confidence"]
                kind = item["entry_kind"] if item["entry_kind"] in ENTRY_KINDS else kind
            else:
                sha256, fingerprint = hash_file(path)
                classification, mime_type, confidence = _signature_classification(path, extension or "")
                if classification == "archive":
                    kind = "archive"
                    archive_inventory = _archive_inventory(path)
    except SourceChangedError as exc:
        fingerprint = {}
        processing_state = "STALE"
        availability = "CHANGED_DURING_SCAN"
        error = str(exc)
    except (OSError, PermissionError) as exc:
        processing_state = "ERROR"
        availability = "UNREADABLE"
        error = str(exc)

    changed = False
    if item is not None:
        previous = _parse_json(item["fingerprint_json"], {})
        changed = bool(previous and fingerprint and previous != fingerprint)
        if changed:
            connection.execute("UPDATE raw_proposals SET stale = 1, updated_at = ? WHERE raw_item_id = ? AND stale = 0", (now, item["id"]))
        connection.execute(
            """UPDATE raw_items SET current_relative_path=?, entry_kind=?, classification=?, classification_source=?,
              classification_confidence=?, extension=?, mime_type=?, size_bytes=?, sha256=?, hash_algorithm=?, fingerprint_json=?,
              availability_state=?, processing_state=?, analysis_status=?, source_batch_id=?, updated_at=?, last_observed_at=?, missing_since=NULL
              WHERE id=?""",
            (
                relative_path, kind, classification, classification_source, confidence, extension, mime_type,
                fingerprint.get("size_bytes"), sha256, HASH_ALGORITHM if sha256 else None,
                _json(fingerprint), availability, processing_state,
                "not_yet_supported", run_id, now, now, item["id"],
            ),
        )
        item_id = item["id"]
        if changed:
            _event(connection, item_id, "SOURCE_CHANGED", {"current_path": relative_path, "sha256": sha256, "error": "Prior proposals were marked stale."})
            _write_proposal(connection, item_id, classification, fingerprint, now=now)
    else:
        # Reconcile a manual rename/move within Raw only when exactly one missing
        # file has the same already-verified hash and size. Ambiguous copies stay
        # distinct Raw artifacts rather than being silently collapsed.
        candidates = []
        if sha256:
            candidates = connection.execute(
                """SELECT * FROM raw_items WHERE sha256 = ?
                   AND hash_algorithm = ? AND size_bytes = ? AND current_relative_path <> ? COLLATE NOCASE""",
                (sha256, HASH_ALGORITHM, fingerprint.get("size_bytes"), relative_path),
            ).fetchall()
            candidates = [
                candidate for candidate in candidates
                if candidate["availability_state"] == "MISSING"
                or not (root / Path(*PurePosixPath(candidate["current_relative_path"]).parts)).exists()
            ]
        if len(candidates) == 1:
            item_id = candidates[0]["id"]
            old_path = candidates[0]["current_relative_path"]
            connection.execute(
                """UPDATE raw_items SET current_relative_path=?, entry_kind=?, classification=?, classification_source=?,
                   classification_confidence=?, extension=?, mime_type=?, size_bytes=?, sha256=?, hash_algorithm=?, fingerprint_json=?,
                   availability_state='PRESENT', processing_state='AWAITING_REVIEW', source_batch_id=?, updated_at=?, last_observed_at=?, missing_since=NULL
                   WHERE id=?""",
                (relative_path, kind, classification, classification_source, confidence, extension, mime_type, fingerprint.get("size_bytes"), sha256, HASH_ALGORITHM, _json(fingerprint), run_id, now, now, item_id),
            )
            connection.execute("INSERT OR IGNORE INTO raw_item_paths (raw_item_id, relative_path, observed_at, path_event) VALUES (?, ?, ?, 'MOVED_WITHIN_RAW')", (item_id, relative_path, now))
            _event(connection, item_id, "SOURCE_RECONCILED", {"original_path": old_path, "current_path": relative_path, "sha256": sha256})
        else:
            item_id = _new_item_id()
            connection.execute(
                """INSERT INTO raw_items
                (id, original_relative_path, current_relative_path, entry_kind, classification, classification_source, classification_confidence,
                 extension, mime_type, size_bytes, sha256, hash_algorithm, fingerprint_json, availability_state, processing_state,
                 analysis_status, source_batch_id, created_at, updated_at, last_observed_at)
                 VALUES (?, ?, ?, ?, ?, 'deterministic', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_yet_supported', ?, ?, ?, ?)""",
                (item_id, relative_path, relative_path, kind, classification, confidence, extension, mime_type, fingerprint.get("size_bytes"), sha256, HASH_ALGORITHM if sha256 else None, _json(fingerprint), availability, processing_state, run_id, now, now, now),
            )
            connection.execute("INSERT INTO raw_item_paths (raw_item_id, relative_path, observed_at, path_event) VALUES (?, ?, ?, 'DISCOVERED')", (item_id, relative_path, now))
            _event(connection, item_id, "DISCOVERED", {"original_path": relative_path, "current_path": relative_path, "sha256": sha256, "classification": classification, "error": error})
            _write_proposal(connection, item_id, classification, fingerprint, now=now)
            if len(candidates) > 1:
                _event(connection, item_id, "RENAME_AMBIGUOUS", {"current_path": relative_path, "sha256": sha256, "error": "Multiple missing items matched; a new Raw item was retained."})

    if sha256:
        _refresh_duplicate_group(connection, item_id, sha256, now=now)
    _upsert_archive_inventory(connection, item_id, archive_inventory)
    if error:
        _event(connection, item_id, "SCAN_ERROR", {"current_path": relative_path, "error": error})
    _failpoint("scan_after_item_registration")
    return item_id


def scan_raw(root: Path | None = None) -> dict[str, Any]:
    """Read-only recursive scan; the only possible creation is an empty Raw/ directory."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    if DataRootManager.is_read_only(active_root):
        raise DataRootReadOnlyError("Data root is read-only; Raw scanning metadata cannot be recorded.")
    source_root = raw_directory(active_root, create=True)
    run_id = f"rawscan_{uuid.uuid4().hex}"
    seen: set[str] = set()
    summary = {"files": 0, "directories": 0, "errors": 0, "items": 0}
    with _locked(active_root):
        connection = _connection(active_root)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO raw_scan_runs (id, started_at, status, summary_json) VALUES (?, ?, 'RUNNING', '{}')",
                (run_id, utc_now()),
            )
            stack = [source_root]
            while stack:
                directory = stack.pop()
                try:
                    entries = sorted(list(os.scandir(directory)), key=lambda entry: unicodedata.normalize("NFC", entry.name).casefold())
                except OSError as exc:
                    summary["errors"] += 1
                    _event(connection, None, "SCAN_DIRECTORY_ERROR", {"current_path": _relative_raw(active_root, directory), "error": str(exc)})
                    continue
                for entry in entries:
                    path = Path(entry.path)
                    try:
                        relative = _relative_raw(active_root, path)
                    except RawIntakeError as exc:
                        summary["errors"] += 1
                        _event(connection, None, "SCAN_PATH_REJECTED", {"error": exc.message})
                        continue
                    folded = relative.casefold()
                    if folded in seen:
                        summary["errors"] += 1
                        _event(connection, None, "CASE_COLLISION", {"current_path": relative, "error": "Case-normalized Raw path collision."})
                        continue
                    seen.add(folded)
                    if entry.is_symlink():
                        kind = "unknown"
                    elif entry.is_dir(follow_symlinks=False):
                        kind = "directory"
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        kind = "file"
                    else:
                        kind = "unknown"
                    _record_observation(connection, root=active_root, path=path, kind=kind, run_id=run_id)
                    summary["items"] += 1
                    if kind == "directory":
                        summary["directories"] += 1
                    elif kind == "file":
                        summary["files"] += 1
                    else:
                        summary["errors"] += 1
            rows = connection.execute(
                "SELECT id, current_relative_path, sha256 FROM raw_items WHERE availability_state = 'PRESENT' AND current_relative_path IS NOT NULL"
            ).fetchall()
            now = utc_now()
            for row in rows:
                if row["current_relative_path"].casefold() not in seen:
                    connection.execute(
                        "UPDATE raw_items SET availability_state='MISSING', processing_state='MISSING', missing_since=?, updated_at=? WHERE id=?",
                        (now, now, row["id"]),
                    )
                    connection.execute("INSERT OR IGNORE INTO raw_item_paths (raw_item_id, relative_path, observed_at, path_event) VALUES (?, ?, ?, 'MISSING')", (row["id"], row["current_relative_path"], now))
                    _event(connection, row["id"], "SOURCE_MISSING", {"current_path": row["current_relative_path"], "sha256": row["sha256"]})
            final_status = "COMPLETED_WITH_ERRORS" if summary["errors"] else "COMPLETED"
            connection.execute(
                "UPDATE raw_scan_runs SET completed_at=?, status=?, summary_json=? WHERE id=?",
                (utc_now(), final_status, _json(summary), run_id),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            connection.execute(
                "UPDATE raw_scan_runs SET completed_at=?, status='FAILED', summary_json=?, error_message=? WHERE id=?",
                (utc_now(), _json(summary), str(exc), run_id),
            )
            connection.commit()
            raise
        finally:
            connection.close()
    try:
        flush_history(active_root)
    except Exception as exc:
        summary["history_pending"] = True
        summary["history_error"] = str(exc)
    return {"ok": True, "run_id": run_id, "status": final_status, "summary": summary}


def _item_row(connection, item_id: str):
    row = connection.execute("SELECT * FROM raw_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise RawIntakeError("Raw item was not found.", "RAW_ITEM_NOT_FOUND")
    return row


def _latest_proposal(connection, item_id: str):
    return connection.execute(
        "SELECT * FROM raw_proposals WHERE raw_item_id = ? ORDER BY rowid DESC LIMIT 1", (item_id,)
    ).fetchone()


def _item_payload(connection, row: Any) -> dict[str, Any]:
    proposal = _latest_proposal(connection, row["id"])
    group = connection.execute(
        """SELECT g.id, COUNT(peer.raw_item_id) AS member_count FROM raw_duplicate_members m
           JOIN raw_duplicate_groups g ON g.id=m.duplicate_group_id
           JOIN raw_duplicate_members peer ON peer.duplicate_group_id=g.id
           WHERE m.raw_item_id=? GROUP BY g.id""",
        (row["id"],),
    ).fetchone()
    return {
        **dict(row),
        "fingerprint": _parse_json(row["fingerprint_json"], {}),
        "proposal": dict(proposal) if proposal else None,
        "duplicate_group_id": group["id"] if group else None,
        "duplicate_count": int(group["member_count"]) if group else 0,
    }


def list_raw_items(root: Path | None = None, *, filter_name: str | None = None, query: str | None = None) -> dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    connection = _connection(active_root)
    try:
        rows = connection.execute("SELECT * FROM raw_items ORDER BY updated_at DESC, id DESC").fetchall()
        items = [_item_payload(connection, row) for row in rows]
        if query:
            needle = query.casefold()
            items = [item for item in items if needle in (item.get("current_relative_path") or "").casefold() or needle in item["classification"].casefold()]
        if filter_name and filter_name != "all":
            def selected(item: dict[str, Any]) -> bool:
                state = item["processing_state"]
                proposal = item.get("proposal") or {}
                mapping = {
                    "needs_review": state == "AWAITING_REVIEW",
                    "duplicates": item["duplicate_count"] > 1,
                    "unknown": item["classification"] == "unknown",
                    "blocked": proposal.get("proposal_state") == "BLOCKED_BY_FUTURE_PHASE",
                    "errors": state == "ERROR" or item["availability_state"] in {"UNREADABLE", "UNSAFE_LINK"},
                    "moved": state == "MOVED",
                    "missing": state == "MISSING",
                }
                return mapping.get(filter_name, item["classification"] == filter_name)
            items = [item for item in items if selected(item)]
        counts = {
            "all": len(rows),
            "needs_review": sum(row["processing_state"] == "AWAITING_REVIEW" for row in rows),
            "duplicates": sum(_item_payload(connection, row)["duplicate_count"] > 1 for row in rows),
            "unknown": sum(row["classification"] == "unknown" for row in rows),
            "blocked": sum((_latest_proposal(connection, row["id"]) or {"proposal_state": ""})["proposal_state"] == "BLOCKED_BY_FUTURE_PHASE" for row in rows),
            "errors": sum(row["processing_state"] == "ERROR" for row in rows),
            "moved": sum(row["processing_state"] == "MOVED" for row in rows),
            "missing": sum(row["processing_state"] == "MISSING" for row in rows),
        }
        latest = connection.execute("SELECT * FROM raw_scan_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return {"ok": True, "items": items, "counts": counts, "latest_run": dict(latest) if latest else None, "raw_exists": raw_directory(active_root).is_dir()}
    finally:
        connection.close()


def get_raw_item(item_id: str, root: Path | None = None) -> dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    connection = _connection(active_root)
    try:
        item = _item_payload(connection, _item_row(connection, item_id))
        item["paths"] = [dict(row) for row in connection.execute("SELECT * FROM raw_item_paths WHERE raw_item_id=? ORDER BY observed_at, id", (item_id,))]
        item["decisions"] = [dict(row) for row in connection.execute("SELECT * FROM raw_decisions WHERE raw_item_id=? ORDER BY created_at DESC, id DESC", (item_id,))]
        item["events"] = [dict(row) for row in connection.execute("SELECT * FROM raw_processing_events WHERE raw_item_id=? ORDER BY created_at DESC, id DESC", (item_id,))]
        item["duplicates"] = [dict(row) for row in connection.execute(
            """SELECT i.id, i.current_relative_path, i.availability_state, i.processing_state FROM raw_duplicate_members m
               JOIN raw_duplicate_members peer ON peer.duplicate_group_id=m.duplicate_group_id
               JOIN raw_items i ON i.id=peer.raw_item_id WHERE m.raw_item_id=? AND peer.raw_item_id<>?""",
            (item_id, item_id),
        )]
        archive = connection.execute("SELECT * FROM raw_archive_inventory WHERE raw_item_id=?", (item_id,)).fetchone()
        item["archive_inventory"] = dict(archive) if archive else None
        return {"ok": True, "item": item}
    finally:
        connection.close()


def correct_item(item_id: str, *, classification: str | None = None, destination_relative_path: str | None = None, note: str | None = None, root: Path | None = None) -> dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    if classification is not None and classification not in CLASSIFICATIONS:
        raise RawIntakeError("Unsupported Raw classification.", "RAW_CLASSIFICATION_INVALID")
    if destination_relative_path is not None:
        destination_relative_path = validate_relative_path(destination_relative_path, allowed_prefix="Database/Sources")
        if destination_relative_path == "Database/Sources":
            raise RawIntakeError("A destination file path is required.", "RAW_DESTINATION_INVALID")
    with _locked(active_root):
        connection = _connection(active_root)
        try:
            connection.execute("BEGIN IMMEDIATE")
            item = _item_row(connection, item_id)
            now = utc_now()
            new_classification = classification or item["classification"]
            if classification:
                connection.execute("UPDATE raw_items SET classification=?, classification_source='human', classification_confidence=1.0, processing_state='AWAITING_REVIEW', updated_at=? WHERE id=?", (classification, now, item_id))
            correction = {"classification": classification, "destination_relative_path": destination_relative_path, "note": note}
            connection.execute("INSERT INTO raw_decisions (id, raw_item_id, decision, note, correction_json, created_at) VALUES (?, ?, 'CORRECTED', ?, ?, ?)", (uuid.uuid4().hex, item_id, note, _json(correction), now))
            if destination_relative_path is not None:
                connection.execute("UPDATE raw_proposals SET stale=1, updated_at=? WHERE raw_item_id=? AND stale=0", (now, item_id))
                fingerprint = _parse_json(item["fingerprint_json"], {})
                proposal_state = "READY"
                proposal_reason = "Human-selected generic provenance destination under Database/Sources."
                try:
                    _destination_path(active_root, destination_relative_path)
                except RawIntakeError as exc:
                    if exc.code != "RAW_DESTINATION_COLLISION":
                        raise
                    proposal_state = "CONFLICT"
                    proposal_reason = "Destination conflicts with an existing canonical path; overwrite is forbidden."
                connection.execute(
                    """INSERT INTO raw_proposals (id, raw_item_id, destination_relative_path, proposal_state, reason, source, source_fingerprint_json, stale, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'human', ?, 0, ?, ?)""",
                    (uuid.uuid4().hex, item_id, destination_relative_path, proposal_state, proposal_reason, _json(fingerprint), now, now),
                )
            _event(connection, item_id, "CORRECTED", {"classification": new_classification, "proposal": destination_relative_path, "decision": "CORRECTED"})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    flush_history(active_root)
    return get_raw_item(item_id, active_root)


def _verify_current_source(root: Path, item: Any, *, require_hash: bool = True) -> tuple[Path, str, dict[str, Any]]:
    relative = item["current_relative_path"]
    if not relative:
        raise RawIntakeError("Raw item no longer has a source path.", "RAW_SOURCE_MISSING")
    safe = validate_relative_path(relative, allowed_prefix="Raw")
    source = _within(root, root / Path(*PurePosixPath(safe).parts))
    _ensure_no_link_ancestors(root, source)
    if not source.is_file():
        raise RawIntakeError("Raw source is no longer present as a regular file.", "RAW_SOURCE_MISSING")
    digest, fingerprint = hash_file(source)
    if require_hash and (item["sha256"] != digest or item["hash_algorithm"] != HASH_ALGORITHM):
        raise SourceChangedError("Raw source does not match its reviewed hash.")
    return source, digest, fingerprint


def decide_item(item_id: str, decision: str, *, note: str | None = None, root: Path | None = None) -> dict[str, Any]:
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED", "DEFERRED"}:
        raise RawIntakeError("Unsupported review decision.", "RAW_DECISION_INVALID")
    with _locked(active_root):
        connection = _connection(active_root)
        try:
            connection.execute("BEGIN IMMEDIATE")
            item = _item_row(connection, item_id)
            proposal = _latest_proposal(connection, item_id)
            if proposal is None:
                raise RawIntakeError("Raw item has no current proposal.", "RAW_PROPOSAL_MISSING")
            if decision == "APPROVED":
                if proposal["stale"] or proposal["proposal_state"] != "READY":
                    raise RawIntakeError("Only a current READY proposal can be approved.", "RAW_APPROVAL_BLOCKED")
                _verify_current_source(active_root, item)
            state = "APPROVED" if decision == "APPROVED" else "REJECTED" if decision == "REJECTED" else "DEFERRED"
            now = utc_now()
            connection.execute("INSERT INTO raw_decisions (id, raw_item_id, decision, note, created_at) VALUES (?, ?, ?, ?, ?)", (uuid.uuid4().hex, item_id, decision, note, now))
            connection.execute("UPDATE raw_items SET processing_state=?, updated_at=? WHERE id=?", (state, now, item_id))
            _event(connection, item_id, "DECISION", {"decision": decision, "proposal": proposal["proposal_state"], "current_path": item["current_relative_path"]})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    flush_history(active_root)
    return get_raw_item(item_id, active_root)


def _destination_path(root: Path, relative: str) -> Path:
    safe = validate_relative_path(relative, allowed_prefix="Database/Sources")
    destination = _within(root, root / Path(*PurePosixPath(safe).parts))
    _ensure_no_link_ancestors(root, destination)
    if destination.exists():
        raise RawIntakeError("Destination already exists; overwrite is forbidden.", "RAW_DESTINATION_COLLISION")
    parent = destination.parent
    if parent.exists():
        names = {child.name.casefold() for child in parent.iterdir()}
        if destination.name.casefold() in names:
            raise RawIntakeError("Destination case-collides with an existing entry.", "RAW_DESTINATION_COLLISION")
    return destination


def _copy_verified(source: Path, temporary: Path) -> str:
    temporary.parent.mkdir(parents=True, exist_ok=False)
    hasher = hashlib.sha256()
    with source.open("rb") as src, temporary.open("xb") as dst:
        for chunk in iter(lambda: src.read(HASH_CHUNK_SIZE), b""):
            dst.write(chunk)
            hasher.update(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    shutil.copystat(source, temporary, follow_symlinks=False)
    return hasher.hexdigest()


def move_approved_item(item_id: str, root: Path | None = None) -> dict[str, Any]:
    """Execute the reusable file move engine for a human-approved READY proposal.

    The final destination is verified before the Raw source is removed. A
    crash after publication leaves a ``DESTINATION_VERIFIED`` operation with
    both byte-identical copies rather than losing the source; recovery is an
    explicit, separately auditable action.
    """
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    if DataRootManager.is_read_only(active_root):
        raise DataRootReadOnlyError("Data root is read-only; Raw moves are blocked.")
    with _locked(active_root):
        connection = _connection(active_root)
        staging_dir: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            item = _item_row(connection, item_id)
            proposal = _latest_proposal(connection, item_id)
            if item["entry_kind"] != "file":
                raise RawIntakeError("Only regular files have a Phase 12 move engine.", "RAW_MOVE_UNSUPPORTED_KIND")
            if proposal is None or proposal["stale"] or proposal["proposal_state"] != "READY" or not proposal["destination_relative_path"]:
                raise RawIntakeError("Raw move requires a current human-approved READY proposal.", "RAW_MOVE_BLOCKED")
            approved = connection.execute(
                "SELECT created_at FROM raw_decisions WHERE raw_item_id=? AND decision='APPROVED' ORDER BY rowid DESC LIMIT 1", (item_id,)
            ).fetchone()
            if approved is None or approved["created_at"] < proposal["created_at"]:
                raise RawIntakeError("Raw move requires approval after the current proposal.", "RAW_APPROVAL_REQUIRED")
            source, digest, _ = _verify_current_source(active_root, item)
            destination = _destination_path(active_root, proposal["destination_relative_path"])
            operation_id = f"rawmove_{uuid.uuid4().hex}"
            now = utc_now()
            connection.execute("INSERT INTO raw_move_operations (id, raw_item_id, source_relative_path, destination_relative_path, expected_sha256, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'PREPARED', ?, ?)", (operation_id, item_id, item["current_relative_path"], proposal["destination_relative_path"], digest, now, now))
            connection.execute("UPDATE raw_items SET processing_state='MOVING', updated_at=? WHERE id=?", (now, item_id))
            _event(connection, item_id, "MOVE_PREPARED", {"current_path": item["current_relative_path"], "final_path": proposal["destination_relative_path"], "sha256": digest})
            connection.commit()
            staging_dir = active_root / "Database" / f"{RAW_STAGING_PREFIX}{operation_id}"
            temporary = staging_dir / "payload"
            copied_hash = _copy_verified(source, temporary)
            if copied_hash != digest:
                raise RawIntakeError("Staged copy hash mismatch; Raw source was retained.", "RAW_MOVE_HASH_MISMATCH")
            _failpoint("move_after_destination_copy_before_source_removal")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise RawIntakeError("Destination appeared during the move.", "RAW_DESTINATION_COLLISION")
            os.replace(temporary, destination)
            staging_dir.rmdir()
            staging_dir = None
            verified, _ = hash_file(destination)
            if verified != digest:
                raise RawIntakeError("Published destination hash mismatch; Raw source was retained.", "RAW_MOVE_HASH_MISMATCH")
            connection.execute("BEGIN IMMEDIATE")
            now = utc_now()
            connection.execute("UPDATE raw_move_operations SET status='DESTINATION_VERIFIED', updated_at=? WHERE id=?", (now, operation_id))
            _event(connection, item_id, "MOVE_DESTINATION_VERIFIED", {"final_path": proposal["destination_relative_path"], "sha256": digest})
            connection.commit()
            _failpoint("move_after_destination_verified")
            source.unlink()
            connection.execute("BEGIN IMMEDIATE")
            now = utc_now()
            connection.execute("UPDATE raw_move_operations SET status='COMPLETED', updated_at=? WHERE id=?", (now, operation_id))
            connection.execute("UPDATE raw_items SET availability_state='MOVED', processing_state='MOVED', final_relative_path=?, current_relative_path=NULL, updated_at=? WHERE id=?", (proposal["destination_relative_path"], now, item_id))
            _event(connection, item_id, "MOVE_COMPLETED", {"final_path": proposal["destination_relative_path"], "sha256": digest})
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if staging_dir and staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            try:
                connection.execute("BEGIN IMMEDIATE")
                if 'operation_id' in locals():
                    connection.execute("UPDATE raw_move_operations SET status='ERROR', error_message=?, updated_at=? WHERE id=? AND status='PREPARED'", (str(exc), utc_now(), operation_id))
                connection.commit()
            except Exception:
                connection.rollback()
            raise
        finally:
            connection.close()
    flush_history(active_root)
    return get_raw_item(item_id, active_root)


def recover_pending_moves(root: Path | None = None) -> dict[str, Any]:
    """Explicitly finish only verified, previously-approved destination copies."""
    active_root = root.resolve() if root else DataRootManager.resolve_active_root()
    recovered: list[str] = []
    with _locked(active_root):
        connection = _connection(active_root)
        try:
            operations = connection.execute("SELECT * FROM raw_move_operations WHERE status='DESTINATION_VERIFIED' ORDER BY created_at").fetchall()
            for operation in operations:
                item = _item_row(connection, operation["raw_item_id"])
                destination = _destination_path_for_existing(active_root, operation["destination_relative_path"])
                if not destination.is_file() or hash_file(destination)[0] != operation["expected_sha256"]:
                    connection.execute("UPDATE raw_move_operations SET status='ERROR', error_message=?, updated_at=? WHERE id=?", ("Published destination no longer matches the verified hash.", utc_now(), operation["id"]))
                    _event(connection, item["id"], "MOVE_RECOVERY_ERROR", {"error": "Published destination no longer matches verified hash."})
                    continue
                source = active_root / Path(*PurePosixPath(validate_relative_path(operation["source_relative_path"], allowed_prefix="Raw")).parts)
                if source.exists():
                    _ensure_no_link_ancestors(active_root, source)
                    if not source.is_file() or hash_file(source)[0] != operation["expected_sha256"]:
                        connection.execute("UPDATE raw_move_operations SET status='ERROR', error_message=?, updated_at=? WHERE id=?", ("Raw source changed; recovery retained both copies.", utc_now(), operation["id"]))
                        _event(connection, item["id"], "MOVE_RECOVERY_ERROR", {"error": "Raw source changed; recovery retained both copies."})
                        continue
                    source.unlink()
                now = utc_now()
                connection.execute("UPDATE raw_move_operations SET status='COMPLETED', updated_at=? WHERE id=?", (now, operation["id"]))
                connection.execute("UPDATE raw_items SET availability_state='MOVED', processing_state='MOVED', final_relative_path=?, current_relative_path=NULL, updated_at=? WHERE id=?", (operation["destination_relative_path"], now, item["id"]))
                _event(connection, item["id"], "MOVE_RECOVERED", {"final_path": operation["destination_relative_path"], "sha256": operation["expected_sha256"]})
                recovered.append(item["id"])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    flush_history(active_root)
    return {"ok": True, "recovered_item_ids": recovered}


def _destination_path_for_existing(root: Path, relative: str) -> Path:
    safe = validate_relative_path(relative, allowed_prefix="Database/Sources")
    destination = _within(root, root / Path(*PurePosixPath(safe).parts))
    _ensure_no_link_ancestors(root, destination)
    return destination


def rehash_item(item_id: str, root: Path | None = None) -> dict[str, Any]:
    """A rehash is an explicit rescan; it never changes the source."""
    scan_raw(root)
    return get_raw_item(item_id, root)
