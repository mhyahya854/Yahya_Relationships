"""SQLite migration/data integrity tests."""

import sqlite3

from app.backend import db
from app.backend.services import people
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.canonical.ids import generate_canonical_person_id


def test_migration_schema_and_seeding(isolated):
    connection = sqlite3.connect(DataRootManager.get_database_path(isolated))
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for table in (
        "people",
        "parent_child",
        "marriages",
        "sibling_groups",
        "general_relationships",
        "groups",
        "person_groups",
        "fact_sources",
    ):
        assert table in tables
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    assert connection.execute("SELECT COUNT(*) FROM groups").fetchone()[0] == 7
    assert connection.execute("SELECT COUNT(*) FROM person_groups").fetchone()[0] == 15
    assert (
        connection.execute(
            """
            SELECT COUNT(*) FROM people p
            WHERE NOT EXISTS (
              SELECT 1 FROM person_groups pg WHERE pg.person_id = p.id
            )
            """
        ).fetchone()[0]
        == 0
    )
    connection.close()


def test_foreign_keys_enabled(isolated):
    connection = db.get_connection()
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()


def test_stable_ids_exist_and_folders_are_per_person(isolated):
    people_rows = people.list_people()
    ids = [row["id"] for row in people_rows]
    assert len(ids) == len(set(ids))
    assert generate_canonical_person_id("Mira Rahim") in ids
    folders = [row["folder"] for row in people_rows]
    assert len(folders) == len(set(folders))
    for row in people_rows:
        assert row["id"] in row["folder"].replace("\\", "/")


def test_add_update_people(isolated):
    created = people.create_person(
        name="Test Person",
        aliases=["TP"],
        birth_year=1990,
        gender="male",
        group_id="friends",
    )
    assert created["id"] == generate_canonical_person_id("Test Person")
    assert created["groups"][0]["id"] == "friends"
    assert created["groups"][0]["is_primary"] is True
    fetched = people.get_person(created["id"])
    assert fetched["name"] == "Test Person"
    updated = people.update_person(created["id"], name="Test Person Two")
    assert updated["name"] == "Test Person Two"
    journal = people.get_person(created["id"])
    assert journal["folder"]
