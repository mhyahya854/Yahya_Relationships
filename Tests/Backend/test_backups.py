"""Backup tests: manifest, database and journals included, restorable copy."""

from pathlib import Path

from app.backend import db
from app.backend.services import backups, journals
from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")


def test_backup_contains_database_journals_and_manifest(isolated):
    journals.append_journal(MIRA, "- Synthetic backup test entry.")
    created = backups.create_backup(label="test-backup")
    folder = Path(created["path"])
    assert (folder / "manifest.json").exists()
    assert (folder / "data" / "relationships.db").exists()
    manifest = folder / "manifest.json"
    import json

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["kind"] == "people-relationships-backup"
    assert payload["label"] == "test-backup"
    assert payload["schema_version"] == 4
    paths = {entry["path"] for entry in payload["files"]}
    assert "data/relationships.db" in paths
    assert any(path.endswith(f"{MIRA}/journal(personal thoughts).md") for path in paths)


def test_backup_verification_passes(isolated):
    created = backups.create_backup()
    assert backups.verify_backup(created["name"])["ok"] is True


def test_backup_database_is_restorable_copy(isolated):
    created = backups.create_backup()
    import sqlite3

    connection = sqlite3.connect(
        Path(created["path"]) / "data" / "relationships.db"
    )
    count = connection.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    connection.close()
    assert count == 15
