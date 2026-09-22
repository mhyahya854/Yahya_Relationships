"""Phase 12 Raw Intake verification on synthetic, disposable Data Roots only."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app.backend import db
from app.backend.data_root.manager import DataRootManager
from app.backend.domain import raw_intake
from app.backend.domain.backups import create_backup, restore_backup, verify_backup


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def raw_root(tmp_path: Path) -> Path:
    root = tmp_path / "phase12-root"
    DataRootManager.ensure_structure(root, create=True, canonical=True)
    db.initialize_database(root / "Database" / "relationships.db")
    raw = root / "Raw"
    (raw / "nested").mkdir()
    (raw / "nested" / "café.txt").write_text("unicode synthetic", encoding="utf-8")
    (raw / "image.jpg").write_bytes(b"\xff\xd8\xffsynthetic-jpeg")
    (raw / "image-copy.jpg").write_bytes(b"\xff\xd8\xffsynthetic-jpeg")
    (raw / "video.mp4").write_bytes(b"synthetic-video")
    (raw / "audio.mp3").write_bytes(b"synthetic-audio")
    (raw / "report.pdf").write_bytes(b"%PDF-1.4 synthetic")
    (raw / "unknown.bin").write_bytes(b"\x00\x01\x02\x03")
    (raw / "Google Timeline takeout.json").write_text("{}", encoding="utf-8")
    (raw / "WhatsApp export.txt").write_text("synthetic", encoding="utf-8")
    (raw / "empty.bin").write_bytes(b"")
    with zipfile.ZipFile(raw / "safe.zip", "w") as archive:
        archive.writestr("nested/safe.txt", "synthetic")
    (raw / "malformed.zip").write_bytes(b"PK\x03\x04not-a-real-zip")
    return root


def _items(root: Path) -> dict[str, dict]:
    return {
        item["current_relative_path"]: item
        for item in raw_intake.list_raw_items(root)["items"]
        if item["current_relative_path"]
    }


def test_v3_to_v4_migration_is_atomic_and_coherent(tmp_path: Path):
    path = tmp_path / "relationships.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    db._bootstrap_new_database(connection, target_schema=2)
    db._migrate_v2_to_v3_atomic(connection)
    assert db.get_current_schema_version(connection) == 3
    connection.close()

    db.migrate(path)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert connection.execute("SELECT value FROM metadata WHERE key='app_schema_version'").fetchone()[0] == "4"
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_items'").fetchone()
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_raw_items_hash'").fetchone()
    finally:
        connection.close()

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    db._MIGRATION_FAILPOINT = "before_phase12_tables"
    try:
        # A second migration is safely idempotent; the failpoint cannot rewrite
        # a coherent schema four database.
        db.migrate(path)
        assert db.get_current_schema_version(connection) == 4
    finally:
        db._MIGRATION_FAILPOINT = None
        connection.close()


def test_real_v3_root_gets_verified_pre_upgrade_safety_snapshot(tmp_path: Path):
    root = tmp_path / "v3-root"
    DataRootManager.ensure_structure(root, create=True, canonical=True)
    path = root / "Database" / "relationships.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    db._bootstrap_new_database(connection, target_schema=2)
    db._migrate_v2_to_v3_atomic(connection)
    connection.close()

    db.migrate(path)
    snapshots = sorted((root / "Backups" / "Safety" / "Pre-Upgrade").iterdir())
    assert len(snapshots) == 1
    assert verify_backup(snapshots[0])["ok"] is True
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        connection.close()


def test_scanner_is_read_only_classifies_and_groups_exact_duplicates(raw_root: Path):
    before = {path.relative_to(raw_root / "Raw").as_posix(): _sha(path) for path in (raw_root / "Raw").rglob("*") if path.is_file()}
    result = raw_intake.scan_raw(raw_root)
    after = {path.relative_to(raw_root / "Raw").as_posix(): _sha(path) for path in (raw_root / "Raw").rglob("*") if path.is_file()}
    assert result["status"] == "COMPLETED"
    assert before == after

    items = _items(raw_root)
    assert items["Raw/image.jpg"]["classification"] == "image"
    assert items["Raw/video.mp4"]["classification"] == "video"
    assert items["Raw/audio.mp3"]["classification"] == "audio"
    assert items["Raw/report.pdf"]["classification"] == "document"
    assert items["Raw/safe.zip"]["classification"] == "archive"
    assert items["Raw/unknown.bin"]["classification"] == "unknown"
    assert items["Raw/Google Timeline takeout.json"]["classification"] == "location_export_candidate"
    assert items["Raw/WhatsApp export.txt"]["classification"] == "social_export_candidate"
    assert items["Raw/image.jpg"]["duplicate_count"] == 2
    assert items["Raw/image-copy.jpg"]["duplicate_count"] == 2
    assert items["Raw/image.jpg"]["id"] != items["Raw/image-copy.jpg"]["id"]
    malformed = raw_intake.get_raw_item(items["Raw/malformed.zip"]["id"], raw_root)["item"]["archive_inventory"]
    assert malformed["safety_status"] == "MALFORMED"
    assert not list((raw_root / "Raw").glob("**/safe.txt"))


def test_rescan_is_idempotent_then_changed_source_stales_review(raw_root: Path):
    raw_intake.scan_raw(raw_root)
    first = _items(raw_root)["Raw/report.pdf"]
    history_after_first = (raw_root / "Database" / "raw_processing_history.md").read_text(encoding="utf-8")
    raw_intake.scan_raw(raw_root)
    second = _items(raw_root)["Raw/report.pdf"]
    history_after_second = (raw_root / "Database" / "raw_processing_history.md").read_text(encoding="utf-8")
    assert first["id"] == second["id"]
    assert first["sha256"] == second["sha256"]
    assert history_after_first == history_after_second

    path = raw_root / "Raw" / "report.pdf"
    path.write_bytes(b"%PDF-1.4 changed synthetic")
    raw_intake.scan_raw(raw_root)
    changed = _items(raw_root)["Raw/report.pdf"]
    assert changed["id"] == first["id"]
    assert changed["sha256"] != first["sha256"]
    assert changed["proposal"]["stale"] == 0
    assert changed["proposal"]["proposal_state"] == "NEEDS_USER_INPUT"


def test_correction_approval_verified_move_and_truthful_history(raw_root: Path):
    raw_intake.scan_raw(raw_root)
    item = _items(raw_root)["Raw/report.pdf"]
    destination = "Database/Sources/synthetic-batch/report.pdf"
    corrected = raw_intake.correct_item(item["id"], classification="document", destination_relative_path=destination, note="Synthetic fixture", root=raw_root)["item"]
    assert corrected["classification_source"] == "human"
    assert corrected["proposal"]["proposal_state"] == "READY"
    raw_intake.decide_item(item["id"], "APPROVED", note="Explicit synthetic review", root=raw_root)
    moved = raw_intake.move_approved_item(item["id"], raw_root)["item"]
    assert moved["processing_state"] == "MOVED"
    assert not (raw_root / "Raw" / "report.pdf").exists()
    assert (raw_root / "Database" / "Sources" / "synthetic-batch" / "report.pdf").read_bytes() == b"%PDF-1.4 synthetic"
    history = (raw_root / "Database" / "raw_processing_history.md").read_text(encoding="utf-8")
    assert item["id"] in history
    assert "Raw/report.pdf" in history
    assert destination in history
    assert "MOVE_COMPLETED" in history


def test_stale_approval_traversal_and_overwrite_are_refused(raw_root: Path):
    raw_intake.scan_raw(raw_root)
    item = _items(raw_root)["Raw/report.pdf"]
    with pytest.raises(raw_intake.RawIntakeError, match="traversal"):
        raw_intake.correct_item(item["id"], destination_relative_path="../outside.pdf", root=raw_root)
    raw_intake.correct_item(item["id"], destination_relative_path="Database/Sources/batch/report.pdf", root=raw_root)
    # The file changes after the destination proposal, so approval must rehash
    # and refuse the stale source rather than moving a different payload.
    (raw_root / "Raw" / "report.pdf").write_bytes(b"%PDF-1.4 changed after proposal")
    with pytest.raises(raw_intake.SourceChangedError):
        raw_intake.decide_item(item["id"], "APPROVED", root=raw_root)
    assert (raw_root / "Raw" / "report.pdf").exists()

    (raw_root / "Database" / "Sources" / "batch").mkdir(parents=True, exist_ok=True)
    (raw_root / "Database" / "Sources" / "batch" / "occupied.pdf").write_bytes(b"retain")
    conflict = raw_intake.correct_item(item["id"], destination_relative_path="Database/Sources/batch/occupied.pdf", root=raw_root)["item"]
    assert conflict["proposal"]["proposal_state"] == "CONFLICT"


def test_missing_and_rename_reconciliation_preserve_history(raw_root: Path):
    raw_intake.scan_raw(raw_root)
    original = _items(raw_root)["Raw/nested/café.txt"]
    (raw_root / "Raw" / "nested" / "café.txt").rename(raw_root / "Raw" / "renamed-café.txt")
    raw_intake.scan_raw(raw_root)
    renamed = _items(raw_root)["Raw/renamed-café.txt"]
    assert renamed["id"] == original["id"]
    (raw_root / "Raw" / "renamed-café.txt").unlink()
    raw_intake.scan_raw(raw_root)
    missing = raw_intake.get_raw_item(original["id"], raw_root)["item"]
    assert missing["processing_state"] == "MISSING"
    assert missing["current_relative_path"] == "Raw/renamed-café.txt"


def test_history_outbox_and_move_recovery_never_lose_raw_source(raw_root: Path, monkeypatch: pytest.MonkeyPatch):
    raw_intake._RAW_FAILPOINT = "history_before_replace"
    try:
        result = raw_intake.scan_raw(raw_root)
        assert result["summary"]["history_pending"] is True
    finally:
        raw_intake._RAW_FAILPOINT = None
    assert raw_intake.flush_history(raw_root) > 0

    item = _items(raw_root)["Raw/report.pdf"]
    destination = "Database/Sources/recovery/report.pdf"
    raw_intake.correct_item(item["id"], destination_relative_path=destination, root=raw_root)
    raw_intake.decide_item(item["id"], "APPROVED", root=raw_root)
    raw_intake._RAW_FAILPOINT = "move_after_destination_verified"
    try:
        with pytest.raises(RuntimeError, match="Injected Phase 12 failure"):
            raw_intake.move_approved_item(item["id"], raw_root)
    finally:
        raw_intake._RAW_FAILPOINT = None
    assert (raw_root / "Raw" / "report.pdf").exists()
    assert (raw_root / "Database" / "Sources" / "recovery" / "report.pdf").exists()
    recovered = raw_intake.recover_pending_moves(raw_root)
    assert item["id"] in recovered["recovered_item_ids"]
    assert not (raw_root / "Raw" / "report.pdf").exists()


def test_backup_keeps_raw_metadata_history_but_excludes_raw_binary_payload(raw_root: Path):
    raw_intake.scan_raw(raw_root)
    backup = create_backup("Phase 12 synthetic snapshot", root=raw_root)
    backup_path = Path(backup["path"])
    assert (backup_path / "data" / "relationships.db").is_file()
    assert (backup_path / "data" / "raw_processing_history.md").is_file()
    assert not (backup_path / "Raw").exists()
    assert verify_backup(backup_path)["ok"] is True
    manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
    assert "data/raw_processing_history.md" in {entry["path"] for entry in manifest["files"]}


def test_restore_recovers_phase12_metadata_and_history_but_not_raw_payload(raw_root: Path):
    raw_intake.scan_raw(raw_root)
    backup_path = Path(create_backup("Phase 12 restore fixture", root=raw_root)["path"])
    original_history = (raw_root / "Database" / "raw_processing_history.md").read_text(encoding="utf-8")
    (raw_root / "Raw" / "after-backup.txt").write_text("not in backup", encoding="utf-8")
    raw_intake.scan_raw(raw_root)
    assert "Raw/after-backup.txt" in (raw_root / "Database" / "raw_processing_history.md").read_text(encoding="utf-8")

    restored = restore_backup(backup_path, root=raw_root, _allow_path=True)
    assert restored["ok"] is True
    assert (raw_root / "Database" / "raw_processing_history.md").read_text(encoding="utf-8") == original_history
    assert (raw_root / "Raw" / "after-backup.txt").read_text(encoding="utf-8") == "not in backup"
    items = raw_intake.list_raw_items(raw_root)["items"]
    assert all(item["current_relative_path"] != "Raw/after-backup.txt" for item in items)
