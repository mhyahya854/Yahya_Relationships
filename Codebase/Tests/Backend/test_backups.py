"""Backup tests: manifest, database and journals included, restorable copy."""

from pathlib import Path

from app.backend import db
from app.backend.services import backups, journals


def test_backup_contains_database_journals_and_manifest(isolated):
    journals.append_journal("mohammad_yahya_hussain", "- Backup test entry.")
    created = backups.create_backup(label="test-backup")
    folder = Path(created["path"])
    assert (folder / "manifest.json").exists()
    assert (folder / "data" / "family.db").exists()
    manifest = folder / "manifest.json"
    import json

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["kind"] == "people-relationships-backup"
    assert payload["label"] == "test-backup"
    assert payload["schema_version"] == 1
    paths = {entry["path"] for entry in payload["files"]}
    assert "data/family.db" in paths
    assert any(path.endswith("mohammad_yahya_hussain/journal.md") for path in paths)


def test_backup_verification_passes(isolated):
    created = backups.create_backup()
    assert backups.verify_backup(created["name"])["ok"] is True


def test_backup_database_is_restorable_copy(isolated):
    created = backups.create_backup()
    import sqlite3

    connection = sqlite3.connect(
        Path(created["path"]) / "data" / "family.db"
    )
    count = connection.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    connection.close()
    assert count == 35
