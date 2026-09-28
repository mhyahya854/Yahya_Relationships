"""Independent Phase 12 adversarial audit regressions.

All filesystem mutation occurs beneath pytest temporary Data Roots. The live
repository Data Root is only inspected by the release audit, never by tests.
"""

from __future__ import annotations

import hashlib
import errno
import json
import os
import re
import sqlite3
import subprocess
import time
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from app.backend import db
from app.backend.data_root.manager import DataRootManager
from app.backend.domain import raw_intake
from app.backend.domain.backups import create_backup, restore_backup
from app.backend.services.data_root import move_data_root
from app.backend.data_root.errors import DataRootInvalidError
from privacy_gate import ABSOLUTE_PROFILE


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> dict[str, tuple[int, str, int]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, _sha(path), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def _items(root: Path) -> dict[str, dict]:
    return {
        item["current_relative_path"]: item
        for item in raw_intake.list_raw_items(root)["items"]
        if item["current_relative_path"]
    }


def _new_root(tmp_path: Path, name: str = "audit-root") -> Path:
    root = tmp_path / name
    DataRootManager.ensure_structure(root, create=True, canonical=True)
    db.initialize_database(root / "Database" / "relationships.db")
    return root


def _approved_item(root: Path, filename: str = "evidence.pdf", destination: str | None = None) -> tuple[str, Path, Path]:
    source = root / "Raw" / filename
    source.write_bytes(b"%PDF-1.4 independent audit evidence")
    raw_intake.scan_raw(root)
    item = _items(root)[f"Raw/{filename}"]
    relative_destination = destination or f"Database/Sources/audit/{filename}"
    raw_intake.correct_item(
        item["id"],
        classification="provenance_source",
        destination_relative_path=relative_destination,
        root=root,
    )
    raw_intake.decide_item(item["id"], "APPROVED", root=root)
    return item["id"], source, root / Path(*relative_destination.split("/"))


def test_scan_is_forensically_read_only_and_absent_raw_stays_absent(tmp_path: Path):
    root = _new_root(tmp_path)
    raw = root / "Raw"
    raw.rmdir()
    assert raw_intake.scan_raw(root)["summary"]["items"] == 0
    assert not raw.exists()

    raw.mkdir()
    names = ["single-quote '.txt", "ampersand &.txt", "rtl-\u202efile.txt", "x" * 100 + ".txt"]
    for index, name in enumerate(names):
        (raw / name).write_text(f"synthetic-{index}", encoding="utf-8")
    before = _inventory(raw)
    raw_intake.scan_raw(root)
    assert _inventory(raw) == before
    assert not [path for path in raw.rglob("*") if path.name.startswith((".", ".raw_"))]


def test_symlink_escape_is_recorded_but_never_followed(tmp_path: Path):
    root = _new_root(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "Raw" / "outside-link"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlink creation is unavailable: {exc}")
    before = outside.read_bytes()
    result = raw_intake.scan_raw(root)
    assert result["summary"]["errors"] == 1
    item = _items(root)["Raw/outside-link"]
    assert item["availability_state"] == "UNSAFE_LINK"
    assert item["sha256"] is None
    assert outside.read_bytes() == before


def test_destination_rejects_internal_link_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    linked = root / "Database" / "Sources" / "linked"
    linked.mkdir()
    original = raw_intake._is_link_like
    monkeypatch.setattr(raw_intake, "_is_link_like", lambda path: path == linked or original(path))
    with pytest.raises(raw_intake.RawIntakeError) as error:
        raw_intake._destination_path(root, "Database/Sources/linked/evidence.pdf")
    assert error.value.code == "RAW_LINK_UNSAFE"


def test_hash_detects_changed_during_read_and_streams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "large.bin"
    path.write_bytes(b"a" * (raw_intake.HASH_CHUNK_SIZE * 3 + 17))
    original = raw_intake._fingerprint
    calls = 0

    def mutate_before_final_stat(target: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            with target.open("r+b") as handle:
                handle.seek(0)
                handle.write(b"b")
                handle.flush()
                os.fsync(handle.fileno())
        return original(target)

    monkeypatch.setattr(raw_intake, "_fingerprint", mutate_before_final_stat)
    with pytest.raises(raw_intake.SourceChangedError):
        raw_intake.hash_file(path)


def test_claim_identity_allows_only_posix_rename_ctime_change():
    approved = {"size_bytes": 7, "mtime_ns": 11, "ctime_ns": 13, "device": 17, "inode": 19}
    renamed = {**approved, "ctime_ns": 23}
    assert raw_intake._matches_approved_claim(renamed, approved) is (os.name != "nt")
    assert not raw_intake._matches_approved_claim({**renamed, "inode": 29}, approved)


def test_duplicate_membership_tracks_current_hash_and_ambiguous_rename_does_not_merge(tmp_path: Path):
    root = _new_root(tmp_path)
    raw = root / "Raw"
    (raw / "a.bin").write_bytes(b"same")
    (raw / "b.bin").write_bytes(b"same")
    raw_intake.scan_raw(root)
    items = _items(root)
    assert items["Raw/a.bin"]["duplicate_count"] == 2
    first_ids = {items["Raw/a.bin"]["id"], items["Raw/b.bin"]["id"]}

    (raw / "a.bin").write_bytes(b"different")
    raw_intake.scan_raw(root)
    assert _items(root)["Raw/a.bin"]["duplicate_count"] == 1
    assert _items(root)["Raw/b.bin"]["duplicate_count"] == 1

    (raw / "a.bin").write_bytes(b"same")
    raw_intake.scan_raw(root)
    (raw / "a.bin").unlink()
    (raw / "b.bin").unlink()
    raw_intake.scan_raw(root)
    (raw / "renamed.bin").write_bytes(b"same")
    raw_intake.scan_raw(root)
    renamed = _items(root)["Raw/renamed.bin"]
    assert renamed["id"] not in first_ids
    events = raw_intake.get_raw_item(renamed["id"], root)["item"]["events"]
    assert any(event["event_type"] == "RENAME_AMBIGUOUS" for event in events)


def test_missing_reappearance_preserves_identity_and_requires_fresh_review(tmp_path: Path):
    root = _new_root(tmp_path)
    source = root / "Raw" / "source.txt"
    source.write_text("stable", encoding="utf-8")
    raw_intake.scan_raw(root)
    original = _items(root)["Raw/source.txt"]
    source.unlink()
    raw_intake.scan_raw(root)
    missing = raw_intake.get_raw_item(original["id"], root)["item"]
    assert missing["processing_state"] == "MISSING"
    assert missing["proposal"]["stale"] == 1
    source.write_text("stable", encoding="utf-8")
    raw_intake.scan_raw(root)
    restored = _items(root)["Raw/source.txt"]
    assert restored["id"] == original["id"]
    assert restored["processing_state"] == "AWAITING_REVIEW"
    assert any(path["path_event"] == "RESTORED" for path in raw_intake.get_raw_item(original["id"], root)["item"]["paths"])


def test_provenance_boundary_and_server_side_state_machine_fail_closed(tmp_path: Path):
    root = _new_root(tmp_path)
    source = root / "Raw" / "ordinary.pdf"
    source.write_bytes(b"%PDF-1.4 ordinary document")
    raw_intake.scan_raw(root)
    item = _items(root)["Raw/ordinary.pdf"]
    assert item["proposal"]["proposal_state"] == "BLOCKED_BY_FUTURE_PHASE"
    with pytest.raises(raw_intake.RawIntakeError) as blocked:
        raw_intake.correct_item(item["id"], destination_relative_path="Database/Sources/ordinary.pdf", root=root)
    assert blocked.value.code == "RAW_FUTURE_PHASE_BLOCKED"

    raw_intake.correct_item(
        item["id"], classification="provenance_source",
        destination_relative_path="Database/Sources/evidence/ordinary.pdf", root=root,
    )
    raw_intake.decide_item(item["id"], "APPROVED", root=root)
    raw_intake.scan_raw(root)
    assert raw_intake.get_raw_item(item["id"], root)["item"]["processing_state"] == "APPROVED"
    raw_intake.decide_item(item["id"], "REJECTED", root=root)
    with pytest.raises(raw_intake.RawIntakeError) as transition:
        raw_intake.move_approved_item(item["id"], root)
    assert transition.value.code == "RAW_TRANSITION_INVALID"


def test_approval_is_bound_to_exact_proposal_not_timestamp_order(tmp_path: Path):
    root = _new_root(tmp_path)
    item_id, source, _ = _approved_item(root)
    raw_intake.correct_item(
        item_id,
        classification="provenance_source",
        destination_relative_path="Database/Sources/audit/reproposal.pdf",
        root=root,
    )
    with pytest.raises(raw_intake.RawIntakeError) as stale:
        raw_intake.move_approved_item(item_id, root)
    assert stale.value.code == "RAW_TRANSITION_INVALID"
    assert source.exists()


@pytest.mark.parametrize(
    ("failpoint", "destination_expected", "recoverable"),
    [
        ("move_before_source_validation", False, False),
        ("move_after_source_validation", False, False),
        ("move_before_quarantine_claim", False, False),
        ("move_after_quarantine_claim", False, True),
        ("move_during_staging_copy", False, True),
        ("move_after_staging_copy", False, True),
        ("move_before_destination_publish", False, True),
        ("move_after_destination_publish", True, True),
        ("move_during_destination_verify", True, True),
        ("move_after_destination_verify", True, True),
        ("move_after_destination_verified", True, True),
        ("move_before_source_removal", True, True),
        pytest.param(
            "move_during_source_removal", True, True,
            marks=pytest.mark.skipif(os.name != "nt", reason="Only Windows performs identity-bound source removal"),
        ),
        ("move_after_source_removal", True, True),
        ("move_before_db_completion", True, True),
        ("move_after_db_completion_before_history", True, False),
    ],
)
def test_move_failure_checkpoints_preserve_or_recover_source(
    tmp_path: Path, failpoint: str, destination_expected: bool, recoverable: bool
):
    root = _new_root(tmp_path, failpoint)
    item_id, source, destination = _approved_item(root)
    raw_intake._RAW_FAILPOINT = failpoint
    try:
        with pytest.raises(RuntimeError, match="Injected Phase 12 failure"):
            raw_intake.move_approved_item(item_id, root)
    finally:
        raw_intake._RAW_FAILPOINT = None
    assert destination.exists() is destination_expected
    if recoverable:
        assert not source.exists()
        with closing(raw_intake._connection(root)) as connection:
            operation = connection.execute(
                "SELECT id FROM raw_move_operations WHERE raw_item_id=? ORDER BY created_at DESC LIMIT 1", (item_id,)
            ).fetchone()
        claimed = raw_intake._quarantine_payload(root, operation["id"])
        assert claimed.is_file() or destination.is_file()
        assert item_id in raw_intake.recover_pending_moves(root)["recovered_item_ids"]
        assert not source.exists()
    elif failpoint == "move_after_db_completion_before_history":
        assert not source.exists()
        assert raw_intake.get_raw_item(item_id, root)["item"]["processing_state"] == "MOVED"
        raw_intake.flush_history(root)
    else:
        assert source.exists()
        assert raw_intake.get_raw_item(item_id, root)["item"]["processing_state"] == "APPROVED"


def test_destination_race_never_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original_publish = raw_intake._publish_without_overwrite

    def race(temporary: Path, target: Path):
        target.write_bytes(b"concurrent-writer")
        return original_publish(temporary, target)

    monkeypatch.setattr(raw_intake, "_publish_without_overwrite", race)
    with pytest.raises(raw_intake.RawIntakeError) as collision:
        raw_intake.move_approved_item(item_id, root)
    assert collision.value.code == "RAW_DESTINATION_COLLISION"
    assert not source.exists()
    assert any((root / ".mosaic-quarantine").rglob("payload"))
    assert destination.read_bytes() == b"concurrent-writer"


def test_replacement_immediately_before_claim_is_retained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original = raw_intake._failpoint
    held = root / "held-approved.pdf"

    def swap(name: str):
        if name == "move_before_quarantine_claim":
            source.rename(held)
            source.write_bytes(b"unreviewed replacement")
        return original(name)

    monkeypatch.setattr(raw_intake, "_failpoint", swap)
    with pytest.raises(raw_intake.SourceChangedError):
        raw_intake.move_approved_item(item_id, root)
    assert held.read_bytes() == b"%PDF-1.4 independent audit evidence"
    assert not destination.exists()
    assert any(path.read_bytes() == b"unreviewed replacement" for path in (root / ".mosaic-quarantine").rglob("payload"))


def test_quarantine_tampering_preserves_both_objects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original = raw_intake._failpoint

    def tamper(name: str):
        if name == "move_after_quarantine_claim":
            claimed = next((root / ".mosaic-quarantine" / "raw-moves").glob("*/payload"))
            claimed.write_bytes(b"quarantine tampering")
        return original(name)

    monkeypatch.setattr(raw_intake, "_failpoint", tamper)
    with pytest.raises(raw_intake.SourceChangedError):
        raw_intake.move_approved_item(item_id, root)
    assert not source.exists() and not destination.exists()
    assert next((root / ".mosaic-quarantine" / "raw-moves").glob("*/payload")).read_bytes() == b"quarantine tampering"


@pytest.mark.skipif(os.name != "nt", reason="Windows identity-bound cleanup")
def test_failed_cleanup_marks_pending_and_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original = raw_intake._remove_verified_source

    def busy(*_args):
        raise raw_intake.RawIntakeError("Synthetic busy handle", "RAW_REMOVE_BUSY")

    monkeypatch.setattr(raw_intake, "_remove_verified_source", busy)
    with pytest.raises(raw_intake.RawIntakeError):
        raw_intake.move_approved_item(item_id, root)
    assert not source.exists() and destination.is_file()
    with closing(raw_intake._connection(root)) as connection:
        operation = connection.execute("SELECT id,status,error_message FROM raw_move_operations WHERE raw_item_id=?", (item_id,)).fetchone()
    assert operation["status"] == "DESTINATION_VERIFIED"
    assert operation["error_message"].startswith("CLEANUP_PENDING")
    assert raw_intake._quarantine_payload(root, operation["id"]).is_file()
    monkeypatch.setattr(raw_intake, "_remove_verified_source", original)
    assert item_id in raw_intake.recover_pending_moves(root)["recovered_item_ids"]


def test_retained_posix_quarantine_relocates_without_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolated_user_bootstrap: Path
):
    root = _isolated_user_bootstrap
    item_id, source, destination = _approved_item(root, "retained-source.pdf")
    monkeypatch.setattr(raw_intake, "_supports_identity_bound_cleanup", lambda: False)
    assert raw_intake.move_approved_item(item_id, root)["item"]["processing_state"] == "MOVED"
    assert not source.exists() and destination.is_file()
    with closing(raw_intake._connection(root)) as connection:
        operation = connection.execute(
            "SELECT id,status,error_message FROM raw_move_operations WHERE raw_item_id=? ORDER BY created_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
    assert operation["status"] == "COMPLETED" and operation["error_message"] == "CLEANUP_PENDING"
    claimed = raw_intake._quarantine_payload(root, operation["id"])
    assert claimed.read_bytes() == destination.read_bytes()

    relocated = tmp_path / "relocated-private-root"
    assert move_data_root(str(relocated))["ok"] is True
    moved_claim = raw_intake._quarantine_payload(relocated, operation["id"])
    moved_destination = relocated / destination.relative_to(root)
    assert moved_claim.read_bytes() == claimed.read_bytes() == moved_destination.read_bytes()
    assert DataRootManager.resolve_active_root() == relocated
    assert claimed.is_file()  # The previous Data Root remains a safety copy.

    moved_claim.write_bytes(b"unreviewed quarantine replacement")
    with pytest.raises(DataRootInvalidError) as error:
        move_data_root(str(tmp_path / "blocked-relocation"))
    assert error.value.detail["code"] == "RAW_QUARANTINE_PENDING"


@pytest.mark.skipif(os.name != "nt", reason="Non-Windows verified removal fails closed")
def test_cross_volume_publish_fallback_is_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    def cross_volume(*_args, **_kwargs):
        raise OSError(errno.EXDEV, "synthetic cross-volume publication")
    monkeypatch.setattr(raw_intake.os, "link", cross_volume)
    raw_intake.move_approved_item(item_id, root)
    assert not source.exists()
    assert destination.read_bytes() == b"%PDF-1.4 independent audit evidence"


def test_source_replacement_before_removal_is_retained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original_failpoint = raw_intake._failpoint

    def replace_source(name: str):
        if name == "move_before_source_removal":
            source.write_bytes(b"replacement that was never approved")
        return original_failpoint(name)

    monkeypatch.setattr(raw_intake, "_failpoint", replace_source)
    raw_intake.move_approved_item(item_id, root)
    assert source.read_bytes() == b"replacement that was never approved"
    assert destination.read_bytes() == b"%PDF-1.4 independent audit evidence"


def test_identity_bound_removal_preserves_replacement_after_last_path_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A new occupant after the last path hash must remain in Raw."""
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original_failpoint = raw_intake._failpoint
    replacement = b"unreviewed external replacement"
    swapped = False

    def replace_immediately_before_lock(name: str):
        nonlocal swapped
        if name == "move_before_verified_remove_open" and not swapped:
            swapped = True
            source.write_bytes(replacement)
        return original_failpoint(name)

    monkeypatch.setattr(raw_intake, "_failpoint", replace_immediately_before_lock)
    raw_intake.move_approved_item(item_id, root)
    assert swapped
    assert destination.read_bytes() == b"%PDF-1.4 independent audit evidence"
    assert source.read_bytes() == replacement


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-sharing behavior")
def test_identity_bound_removal_denies_write_during_verified_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original_failpoint = raw_intake._failpoint
    replacement = root / "Raw" / "external-replacement.bin"
    replacement.write_bytes(b"unreviewed replacement")
    attempted = False

    def try_write_while_locked(name: str):
        nonlocal attempted
        if name == "move_during_source_removal":
            attempted = True
            claimed = next((root / ".mosaic-quarantine" / "raw-moves").glob("*/payload"))
            with pytest.raises(PermissionError):
                claimed.write_bytes(b"unreviewed replacement")
            with pytest.raises(PermissionError):
                os.replace(replacement, claimed)
        return original_failpoint(name)

    monkeypatch.setattr(raw_intake, "_failpoint", try_write_while_locked)
    raw_intake.move_approved_item(item_id, root)
    assert attempted
    assert not source.exists()
    assert replacement.read_bytes() == b"unreviewed replacement"
    assert destination.read_bytes() == b"%PDF-1.4 independent audit evidence"


@pytest.mark.skipif(os.name != "nt", reason="Windows identity-bound removal")
def test_new_source_after_verified_delete_gets_new_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    original_failpoint = raw_intake._failpoint
    replacement = b"new source arriving after completed removal"

    def recreate_after_delete(name: str):
        if name == "move_after_source_removal":
            source.write_bytes(replacement)
        return original_failpoint(name)

    monkeypatch.setattr(raw_intake, "_failpoint", recreate_after_delete)
    raw_intake.move_approved_item(item_id, root)
    assert source.read_bytes() == replacement
    assert raw_intake.get_raw_item(item_id, root)["item"]["processing_state"] == "MOVED"
    raw_intake.scan_raw(root)
    new_item = _items(root)["Raw/evidence.pdf"]
    assert new_item["id"] != item_id
    assert new_item["sha256"] == _sha(source)
    assert destination.read_bytes() == b"%PDF-1.4 independent audit evidence"


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-sharing behavior")
def test_busy_source_is_retained_without_claim(tmp_path: Path):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    with source.open("r+b"):
        with pytest.raises(raw_intake.RawIntakeError) as error:
            raw_intake.move_approved_item(item_id, root)
        assert error.value.code == "RAW_CLAIM_BUSY"
        assert source.is_file() and not destination.exists()
    assert raw_intake.recover_pending_moves(root)["recovered_item_ids"] == []
    assert source.exists()


@pytest.mark.skipif(os.name != "nt", reason="Non-Windows verified removal fails closed")
def test_identity_bound_move_supports_unicode_source(tmp_path: Path):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root, "دليل 🧪.pdf")
    raw_intake.move_approved_item(item_id, root)
    assert not source.exists()
    assert destination.read_bytes() == b"%PDF-1.4 independent audit evidence"


def test_corrupt_moving_state_without_supporting_proposal_fails_closed(tmp_path: Path):
    root = _new_root(tmp_path)
    item_id, source, destination = _approved_item(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    connection = sqlite3.connect(root / "Database" / "relationships.db")
    try:
        connection.execute("UPDATE raw_items SET processing_state='MOVING' WHERE id=?", (item_id,))
        connection.execute("DELETE FROM raw_proposals WHERE raw_item_id=?", (item_id,))
        connection.execute(
            """INSERT INTO raw_move_operations
               (id, raw_item_id, source_relative_path, destination_relative_path, expected_sha256, status, created_at, updated_at)
               VALUES ('corrupt-op', ?, 'Raw/evidence.pdf', 'Database/Sources/audit/evidence.pdf', ?, 'DESTINATION_VERIFIED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
            (item_id, _sha(source)),
        )
        connection.commit()
    finally:
        connection.close()
    assert raw_intake.recover_pending_moves(root)["recovered_item_ids"] == []
    assert source.exists()
    connection = sqlite3.connect(root / "Database" / "relationships.db")
    try:
        assert connection.execute("SELECT status FROM raw_move_operations WHERE id='corrupt-op'").fetchone()[0] == "ERROR"
    finally:
        connection.close()


def test_archive_metadata_limits_and_unsafe_names_without_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _new_root(tmp_path)
    archive_path = root / "Raw" / "hostile.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "no")
        archive.writestr("C:/absolute.txt", "no")
        archive.writestr("duplicate.txt", "one")
        archive.writestr("DUPLICATE.txt", "two")
    raw_intake.scan_raw(root)
    item = _items(root)["Raw/hostile.zip"]
    inventory = raw_intake.get_raw_item(item["id"], root)["item"]["archive_inventory"]
    assert inventory["safety_status"] == "UNSAFE_PATH"
    assert not (root / "escape.txt").exists()

    monkeypatch.setattr(raw_intake, "MAX_ARCHIVE_MEMBERS", 1)
    limited = raw_intake._archive_inventory(archive_path)
    assert limited and limited["safety_status"] == "RESOURCE_LIMIT"
    assert limited["members"] == []


def test_history_projection_rebuilds_after_delete_or_corruption(tmp_path: Path):
    root = _new_root(tmp_path)
    (root / "Raw" / "history.txt").write_text("history", encoding="utf-8")
    raw_intake.scan_raw(root)
    history = root / "Database" / raw_intake.HISTORY_FILENAME
    expected_ids = {
        row[0]
        for row in sqlite3.connect(root / "Database" / "relationships.db").execute(
            "SELECT id FROM raw_processing_events"
        ).fetchall()
    }
    history.unlink()
    raw_intake.flush_history(root)
    rebuilt = history.read_text(encoding="utf-8")
    assert all(f"raw-event:{event_id}" in rebuilt for event_id in expected_ids)
    history.write_text("corrupted", encoding="utf-8")
    raw_intake.flush_history(root)
    assert history.read_text(encoding="utf-8").startswith(raw_intake.HISTORY_HEADER)


def test_schema4_restore_marks_missing_sources_and_schema3_restore_removes_newer_history(tmp_path: Path):
    root = _new_root(tmp_path, "schema4-root")
    source = root / "Raw" / "restore.txt"
    source.write_text("restore", encoding="utf-8")
    raw_intake.scan_raw(root)
    item_id = _items(root)["Raw/restore.txt"]["id"]
    schema4_backup = Path(create_backup("schema4", root=root)["path"])
    source.unlink()
    restore_backup(schema4_backup, root=root, _allow_path=True)
    assert raw_intake.get_raw_item(item_id, root)["item"]["processing_state"] == "MISSING"

    v3 = tmp_path / "schema3-source"
    DataRootManager.ensure_structure(v3, create=True, canonical=True)
    v3_db = v3 / "Database" / "relationships.db"
    connection = sqlite3.connect(v3_db)
    connection.row_factory = sqlite3.Row
    db._bootstrap_new_database(connection, target_schema=2)
    db._migrate_v2_to_v3_atomic(connection)
    connection.close()
    schema3_backup = Path(create_backup("schema3", root=v3)["path"])
    raw_payload = root / "Raw" / "survives.bin"
    raw_payload.write_bytes(b"survives generation rollback")
    restore_backup(schema3_backup, root=root, _allow_path=True)
    assert raw_payload.read_bytes() == b"survives generation rollback"
    assert not (root / "Database" / raw_intake.HISTORY_FILENAME).exists()
    restored = sqlite3.connect(root / "Database" / "relationships.db")
    try:
        assert restored.execute("PRAGMA user_version").fetchone()[0] == 3
        assert not restored.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_items'").fetchone()
    finally:
        restored.close()


def test_v3_to_v4_migration_preserves_every_preexisting_table_semantically(tmp_path: Path):
    path = tmp_path / "Database" / "relationships.db"
    path.parent.mkdir()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    db._bootstrap_new_database(connection, target_schema=2)
    db._migrate_v2_to_v3_atomic(connection)
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    before = {
        table: connection.execute(
            f'SELECT * FROM "{table}"' + (" WHERE key <> 'app_schema_version'" if table == "metadata" else "") + " ORDER BY rowid"
        ).fetchall()
        for table in tables
    }
    connection.close()
    db.migrate(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        for table, rows in before.items():
            query = f'SELECT * FROM "{table}"' + (" WHERE key <> 'app_schema_version'" if table == "metadata" else "") + " ORDER BY rowid"
            assert sorted((tuple(row) for row in connection.execute(query)), key=repr) == sorted((tuple(row) for row in rows), key=repr)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_v3_to_v4_failure_rolls_back_and_preupgrade_backup_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    isolated_db = tmp_path / "Database" / "relationships.db"
    isolated_db.parent.mkdir()
    connection = sqlite3.connect(isolated_db)
    connection.row_factory = sqlite3.Row
    db._bootstrap_new_database(connection, target_schema=2)
    db._migrate_v2_to_v3_atomic(connection)
    connection.close()
    db._MIGRATION_FAILPOINT = "after_phase12_tables"
    try:
        with pytest.raises(RuntimeError, match="Injected migration failure"):
            db.migrate(isolated_db)
    finally:
        db._MIGRATION_FAILPOINT = None
    connection = sqlite3.connect(isolated_db)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_items'").fetchone()
    finally:
        connection.close()

    real_root = tmp_path / "canonical-root"
    DataRootManager.ensure_structure(real_root, create=True, canonical=True)
    real_db = real_root / "Database" / "relationships.db"
    connection = sqlite3.connect(real_db)
    connection.row_factory = sqlite3.Row
    db._bootstrap_new_database(connection, target_schema=2)
    db._migrate_v2_to_v3_atomic(connection)
    connection.close()

    def refuse_backup(*args, **kwargs):
        raise OSError("synthetic read-only backup destination")

    from app.backend.domain.backups import create as backup_create
    monkeypatch.setattr(backup_create, "create_backup", refuse_backup)
    with pytest.raises(RuntimeError, match="required pre-upgrade safety snapshot"):
        db.migrate(real_db)
    connection = sqlite3.connect(real_db)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_items'").fetchone()
    finally:
        connection.close()


def test_raw_api_rejects_invalid_and_unauthorized_actions(tmp_path: Path):
    from fastapi.testclient import TestClient
    from app.backend.api.main import app

    root = _new_root(tmp_path)
    (root / "Raw" / "api.pdf").write_bytes(b"%PDF-1.4 api")
    DataRootManager.set_override_root(root)
    try:
        with TestClient(app) as client:
            assert client.post("/api/raw/scan").status_code == 200
            item = client.get("/api/raw").json()["items"][0]
            assert client.post(f"/api/raw/{item['id']}/decision", json={"decision": "APPROVED"}).status_code == 400
            assert client.post(f"/api/raw/{item['id']}/move").status_code == 400
            traversal = client.post(
                f"/api/raw/{item['id']}/correct",
                json={"classification": "provenance_source", "destination_relative_path": "../escape"},
            )
            assert traversal.status_code == 400
            assert traversal.json()["detail"]["code"] == "RAW_PATH_UNSAFE"
            assert client.post(f"/api/raw/{item['id']}/decision", json={"decision": "INVALID"}).status_code == 400
            assert client.get("/api/raw/not-a-real-item").status_code == 404
    finally:
        DataRootManager.set_override_root(None)


def test_source_control_has_no_raw_payload_or_machine_specific_phase12_path():
    repo = Path(__file__).resolve().parents[2]
    tracked_raw = subprocess.run(
        ["git", "ls-files", "Raw"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked_raw == []
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=repo, check=True, capture_output=True,
    ).stdout.split(b"\0")
    for encoded in filter(None, tracked):
        path = encoded.decode("utf-8", "surrogateescape")
        assert not path.startswith("Codebase/"), path
        content = subprocess.run(
            ["git", "show", ":" + path], cwd=repo, check=True, capture_output=True,
        ).stdout
        if b"\0" in content[:4096]:
            continue
        source = content.decode("utf-8", "replace")
        assert not ABSOLUTE_PROFILE.search(source), path
        assert not re.search("One" + "Drive" + r"[\\/]", source), path


def test_thousand_file_scan_is_bounded_paginated_and_idempotent(tmp_path: Path):
    root = _new_root(tmp_path)
    for index in range(1_000):
        (root / "Raw" / f"item-{index:04d}.bin").write_bytes(index.to_bytes(4, "little"))
    started = time.perf_counter()
    result = raw_intake.scan_raw(root)
    elapsed = time.perf_counter() - started
    assert result["summary"]["files"] == 1_000
    assert elapsed < 30
    first_page = raw_intake.list_raw_items(root, limit=200, offset=0)
    last_page = raw_intake.list_raw_items(root, limit=200, offset=800)
    assert first_page["counts"]["all"] == 1_000
    assert first_page["total_filtered"] == 1_000
    assert len(first_page["items"]) == len(last_page["items"]) == 200
    connection = sqlite3.connect(root / "Database" / "relationships.db")
    before_events = connection.execute("SELECT COUNT(*) FROM raw_processing_events").fetchone()[0]
    connection.close()
    raw_intake.scan_raw(root)
    connection = sqlite3.connect(root / "Database" / "relationships.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM raw_processing_events").fetchone()[0] == before_events
    finally:
        connection.close()
