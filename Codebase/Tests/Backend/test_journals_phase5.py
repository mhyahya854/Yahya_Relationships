"""Phase 5 contract tests for canonical Markdown journals."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from app.backend import db
from app.backend.data_root.errors import (
    DataRootReadOnlyError,
    MaintenanceOperationInProgressError,
)
from app.backend.data_root.manager import DataRootManager
from app.backend.domain import maintenance
from app.backend.services import errors, journals


PID = "mohammad_yahya_hussain"
OTHER_PID = "maham_mansoor"


def _path(person_id: str = PID) -> Path:
    return Path(journals.read_journal(person_id)["path"])


def _save(person_id: str, content: str, revision: dict, *, force: bool = False) -> dict:
    return journals.save_journal(
        person_id,
        content,
        expected_exists=revision["exists"],
        expected_sha256=revision["sha256"],
        expected_modified_ns=revision["modified_ns"],
        force=force,
    )


def test_read_existing_journal_exact_utf8(isolated):
    path = _path()
    expected = "# English\n\nاردو Roman Urdu 😀\n"
    path.write_bytes(expected.encode("utf-8"))
    result = journals.read_journal(PID)
    assert result["content"] == expected
    assert result["sha256"]
    assert result["modified_ns"]
    assert result["exists"] is True


def test_read_missing_journal_creates_nothing(isolated):
    path = _path()
    path.unlink()
    before = set(path.parent.iterdir())
    result = journals.read_journal(PID)
    assert result["exists"] is False
    assert result["content"] == ""
    assert result["sha256"] is None
    assert set(path.parent.iterdir()) == before


def test_journal_summaries_read_creates_nothing(isolated):
    path = _path()
    path.unlink()
    before = {p.relative_to(isolated) for p in isolated.rglob("*")}
    journals.journal_summaries()
    after = {p.relative_to(isolated) for p in isolated.rglob("*")}
    assert after == before


def test_save_existing_journal(isolated):
    first = journals.read_journal(PID)
    saved = _save(PID, "# Updated\n", first)
    assert saved["content"] == "# Updated\n"
    assert _path().read_text(encoding="utf-8") == "# Updated\n"


def test_explicit_first_save_creates_missing_journal(isolated):
    path = _path()
    path.unlink()
    missing = journals.read_journal(PID)
    saved = _save(PID, "First journal\n", missing)
    assert saved["exists"] is True
    assert path.read_bytes() == b"First journal\n"


def test_empty_existing_remains_distinguishable_from_missing(isolated):
    path = _path()
    path.write_bytes(b"")
    empty = journals.read_journal(PID)
    assert empty["exists"] is True and empty["content"] == ""
    path.unlink()
    missing = journals.read_journal(PID)
    assert missing["exists"] is False and missing["content"] == ""


def test_english_round_trip(isolated):
    first = journals.read_journal(PID)
    text = "# Family memories\n\nA quiet afternoon.\n"
    assert _save(PID, text, first)["content"] == text


def test_urdu_round_trip(isolated):
    first = journals.read_journal(PID)
    text = "# یادداشتیں\n\nیہ ایک خاندانی یاد ہے۔\n"
    assert _save(PID, text, first)["content"] == text


def test_roman_urdu_round_trip(isolated):
    first = journals.read_journal(PID)
    text = "# Yaadein\n\nAaj sab ghar walay saath thay.\n"
    assert _save(PID, text, first)["content"] == text


def test_mixed_unicode_and_emoji_round_trip(isolated):
    first = journals.read_journal(PID)
    text = "English — اردو — Roman Urdu — 👨‍👩‍👧‍👦✨\n"
    saved = _save(PID, text, first)
    assert saved["content"] == text
    assert _path().read_bytes().decode("utf-8") == text


def test_save_normalizes_all_newlines_to_lf(isolated):
    first = journals.read_journal(PID)
    saved = _save(PID, "one\r\ntwo\rthree\n", first)
    assert saved["content"] == "one\ntwo\nthree\n"
    assert b"\r" not in _path().read_bytes()


def test_append_uses_local_date_heading(isolated):
    result = journals.append_journal(PID, "A dated note")
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    assert f"## {today}\n\nA dated note\n" in result["content"]


def test_repeated_same_date_append_avoids_duplicate_heading(isolated):
    journals.append_journal(PID, "First", heading="2026-09-07")
    result = journals.append_journal(PID, "Second", heading="2026-09-07")
    assert result["content"].count("## 2026-09-07") == 1
    assert result["content"].endswith("First\n\nSecond\n")


def test_custom_append_heading(isolated):
    result = journals.append_journal(PID, "Milestone text", heading="Milestone")
    assert "## Milestone\n\nMilestone text\n" in result["content"]


def test_empty_append_rejected(isolated):
    with pytest.raises(errors.ValidationError):
        journals.append_journal(PID, " \r\n ")


def test_external_modification_conflicts(isolated):
    first = journals.read_journal(PID)
    path = _path()
    path.write_text("external\n", encoding="utf-8", newline="\n")
    with pytest.raises(errors.JournalConflictError):
        _save(PID, "local\n", first)
    assert path.read_text(encoding="utf-8") == "external\n"


def test_missing_journal_externally_created_before_save_conflicts(isolated):
    path = _path()
    path.unlink()
    missing = journals.read_journal(PID)
    path.write_text("external creation\n", encoding="utf-8", newline="\n")
    with pytest.raises(errors.JournalConflictError) as exc:
        _save(PID, "local draft\n", missing)
    assert exc.value.details["current_exists"] is True
    assert path.read_text(encoding="utf-8") == "external creation\n"


def test_existing_journal_externally_deleted_before_save_conflicts(isolated):
    first = journals.read_journal(PID)
    path = _path()
    path.unlink()
    with pytest.raises(errors.JournalConflictError) as exc:
        _save(PID, "local draft\n", first)
    assert exc.value.details["current_exists"] is False
    assert not path.exists()


def test_same_mtime_different_sha_still_conflicts(isolated):
    first = journals.read_journal(PID)
    path = _path()
    stat = path.stat()
    path.write_text("different bytes\n", encoding="utf-8", newline="\n")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(errors.JournalConflictError):
        _save(PID, "local\n", first)


def test_changed_mtime_identical_sha_does_not_false_conflict(isolated):
    first = journals.read_journal(PID)
    path = _path()
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    saved = _save(PID, "accepted\n", first)
    assert saved["content"] == "accepted\n"


def test_two_clients_same_revision_second_save_conflicts(isolated):
    client_a = journals.read_journal(PID)
    client_b = journals.read_journal(PID)
    _save(PID, "client A\n", client_a)
    with pytest.raises(errors.JournalConflictError):
        _save(PID, "client B\n", client_b)
    assert _path().read_text(encoding="utf-8") == "client A\n"


def test_explicit_overwrite_only_succeeds_when_requested(isolated):
    first = journals.read_journal(PID)
    _path().write_text("disk\n", encoding="utf-8", newline="\n")
    with pytest.raises(errors.JournalConflictError):
        _save(PID, "draft\n", first)
    forced = _save(PID, "draft\n", first, force=True)
    assert forced["content"] == "draft\n"


def test_conflict_detection_creates_no_files_or_folders(isolated):
    first = journals.read_journal(PID)
    folder = _path().parent
    for child in folder.iterdir():
        if child.is_file():
            child.unlink()
    folder.rmdir()
    with pytest.raises(errors.JournalConflictError):
        _save(PID, "draft\n", first)
    assert not folder.exists()


def test_temp_write_failure_preserves_existing_bytes(isolated, monkeypatch):
    path = _path()
    original = path.read_bytes()
    first = journals.read_journal(PID)
    real_fdopen = journals.os.fdopen

    class FailingHandle:
        def __init__(self, fd):
            self.fd = fd

        def __enter__(self):
            return self

        def __exit__(self, *_):
            os.close(self.fd)

        def write(self, _content):
            raise OSError("injected write failure")

    monkeypatch.setattr(journals.os, "fdopen", lambda fd, *_a, **_k: FailingHandle(fd))
    with pytest.raises(OSError, match="injected write failure"):
        _save(PID, "replacement\n", first)
    monkeypatch.setattr(journals.os, "fdopen", real_fdopen)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(".journal-*.tmp"))


def test_fsync_failure_preserves_existing_bytes_and_cleans_temp(isolated, monkeypatch):
    path = _path()
    original = path.read_bytes()
    first = journals.read_journal(PID)
    monkeypatch.setattr(journals.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("fsync failed")))
    with pytest.raises(OSError, match="fsync failed"):
        _save(PID, "replacement\n", first)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(".journal-*.tmp"))


def test_replace_failure_on_first_save_leaves_no_journal_or_temp(isolated, monkeypatch):
    path = _path()
    path.unlink()
    missing = journals.read_journal(PID)
    monkeypatch.setattr(journals.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        _save(PID, "first save\n", missing)
    assert not path.exists()
    assert not list(path.parent.glob(".journal-*.tmp"))


def test_append_does_not_clobber_concurrent_external_content(isolated, monkeypatch):
    path = _path()
    original_save = journals.save_journal

    def race(person_id, content, **kwargs):
        path.write_text("external wins\n", encoding="utf-8", newline="\n")
        return original_save(person_id, content, **kwargs)

    monkeypatch.setattr(journals, "save_journal", race)
    with pytest.raises(errors.JournalConflictError):
        journals.append_journal(PID, "local append")
    assert path.read_text(encoding="utf-8") == "external wins\n"


def test_read_only_save_blocked(isolated, monkeypatch):
    first = journals.read_journal(PID)
    original = _path().read_bytes()
    monkeypatch.setattr(DataRootManager, "is_read_only", lambda *_: True)
    with pytest.raises(DataRootReadOnlyError):
        _save(PID, "blocked\n", first)
    assert _path().read_bytes() == original


def test_read_only_append_blocked(isolated, monkeypatch):
    original = _path().read_bytes()
    monkeypatch.setattr(DataRootManager, "is_read_only", lambda *_: True)
    with pytest.raises(DataRootReadOnlyError):
        journals.append_journal(PID, "blocked")
    assert _path().read_bytes() == original


def test_maintenance_lock_save_blocked(isolated):
    first = journals.read_journal(PID)
    assert maintenance.acquire_maintenance_lock("TEST_JOURNAL_LOCK")
    try:
        with pytest.raises(MaintenanceOperationInProgressError):
            _save(PID, "blocked\n", first)
    finally:
        maintenance.release_maintenance_lock()


def test_unknown_person_rejected_cleanly(isolated):
    with pytest.raises(errors.NotFoundError):
        journals.read_journal("definitely_unknown_person")


def test_unsafe_person_id_rejected(isolated):
    for unsafe in ("../secret", "..\\secret", "a/b", "a b", ""):
        with pytest.raises(errors.ValidationError):
            journals.read_journal(unsafe)


def test_summaries_ignore_orphan_folder(isolated):
    orphan = isolated / "Database" / "People" / "Family" / "orphan_phase5" / "journal.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("orphan prose", encoding="utf-8")
    assert all(item["person_id"] != "orphan_phase5" for item in journals.journal_summaries())


def test_malformed_journal_does_not_crash_summary_scan(isolated):
    bad = _path()
    bad.write_bytes(b"\xff\xfe\x00")
    summaries = journals.journal_summaries()
    assert all(item["person_id"] != PID for item in summaries)
    assert any(item["person_id"] == OTHER_PID for item in summaries)


def test_no_journal_prose_columns_in_sqlite(isolated):
    connection = db.get_connection()
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        columns = {
            f"{table}.{row[1]}".lower()
            for table in tables
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
    finally:
        connection.close()
    assert not any("journal" in column for column in columns)


def test_reasonably_large_journal_round_trip(isolated):
    first = journals.read_journal(PID)
    text = "# Large\n\n" + ("English اردو Roman Urdu 😀\n" * 18_000)
    saved = _save(PID, text, first)
    assert len(saved["content"].encode("utf-8")) > 500_000
    assert journals.read_journal(PID)["content"] == text


def test_force_overwrite_returns_new_revision(isolated):
    first = journals.read_journal(PID)
    _path().write_text("external\n", encoding="utf-8", newline="\n")
    forced = _save(PID, "forced\n", first, force=True)
    assert forced["saved"] is True
    assert forced["sha256"] != first["sha256"]
    assert forced["exists"] is True


def test_revision_values_update_after_successful_write(isolated):
    first = journals.read_journal(PID)
    saved = _save(PID, first["content"] + "revision change\n", first)
    assert saved["sha256"] != first["sha256"]
    assert int(saved["modified_ns"]) >= int(first["modified_ns"])
    assert saved["content"].endswith("revision change\n")
