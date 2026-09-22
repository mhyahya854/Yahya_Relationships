"""Independent Phase-11 safety and semantic regression tests.

All mutation, failure injection, migration, and restore cases use temporary
Data Roots. The repository's historical and canonical databases are read-only
inputs to these tests.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.backend import db
from app.backend.data_root.errors import DataRootNotFoundError
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.backups.create import create_backup
from app.backend.domain.backups.restore import restore_backup
from app.backend.domain.backups.verify import verify_backup
from app.backend.domain.canonical.ids import (
    generate_canonical_person_id,
    normalize_name,
)
from app.backend.domain.canonical.template import FOLDER_TEMPLATE_DIRECTORIES
from app.backend.domain.family import engine as family_engine
from app.backend.domain.migration import engine as migration
from app.backend.services import family as family_service
from app.backend.services import general as general_service
from app.backend.services import journals as journal_service
from app.backend.services import people as people_service


REPO = Path(__file__).resolve().parents[3]
LEGACY_DB = REPO / "Database" / "Main" / "family.db"
LEGACY_PEOPLE = REPO / "Database" / "People"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"), key=lambda value: value.as_posix())
        if path.is_file()
    }


def _legacy_root(tmp_path: Path) -> Path:
    root = tmp_path / "legacy-root"
    database = root / "Database" / "Main"
    database.mkdir(parents=True)
    shutil.copy2(LEGACY_DB, database / "family.db")
    if LEGACY_PEOPLE.is_dir():
        shutil.copytree(LEGACY_PEOPLE, root / "Database" / "People")
    else:
        (root / "Database" / "People").mkdir(parents=True)
    (root / "Database" / "Config").mkdir(parents=True)
    return root


def _migrated_root(tmp_path: Path) -> Path:
    root = _legacy_root(tmp_path)
    result = migration.execute_migration(root)
    assert result["ok"] is True
    return root


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _rows(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    return [tuple(row) for row in connection.execute(sql, params).fetchall()]


def test_id_algorithm_handles_unicode_and_rejects_invalid_names():
    assert normalize_name("  Élodie   O'Connor-Smith ") == "elodie_o_connor_smith"
    assert generate_canonical_person_id("Élodie O'Connor-Smith") == "elodie_o_connor_smith--EOCS01"
    arabic = generate_canonical_person_id("محمد يحيى")
    assert arabic.startswith("u0645u062du0645u062f_u064au062du064au0649--UU")
    assert generate_canonical_person_id("Sara Khan", {"sameer_khan--SK01"}) == "sara_khan--SK01"
    with pytest.raises(ValueError):
        generate_canonical_person_id("   ")
    with pytest.raises(ValueError):
        generate_canonical_person_id("---")


def test_missing_canonical_database_never_falls_back_or_creates(tmp_path):
    root = tmp_path / "canonical-missing-db"
    (root / "Database" / "Main").mkdir(parents=True)
    shutil.copy2(LEGACY_DB, root / "Database" / "Main" / "family.db")
    (root / "Database" / "Config").mkdir(parents=True)
    (root / "Database" / "Config" / "data-root.json").write_text(
        json.dumps({"storage_layout": DataRootManager.CANONICAL_LAYOUT}),
        encoding="utf-8",
    )
    expected = root / "Database" / "relationships.db"
    assert DataRootManager.get_database_path(root) == expected
    with pytest.raises(DataRootNotFoundError):
        db.get_connection(expected)
    assert not expected.exists()
    assert _sha256(root / "Database" / "Main" / "family.db") == _sha256(LEGACY_DB)


def test_semantic_row_by_row_migration_parity(tmp_path):
    root = _migrated_root(tmp_path)
    source = _connect(root / "Database" / "Main" / "family.db")
    target = _connect(root / "Database" / "relationships.db")
    try:
        id_map = dict(
            target.execute(
                "SELECT old_identifier, canonical_id FROM identifier_aliases WHERE entity_type='person'"
            )
        )
        assert set(id_map) == {row[0] for row in source.execute("SELECT id FROM people")}

        source_people = {
            id_map[row["id"]]: tuple(row[key] for key in (
                "name", "birth_year", "gender", "marital_status", "branch",
                "legacy_relation_en", "legacy_relation_ur", "note_en", "note_ur",
                "photo_path", "display_order",
            ))
            for row in source.execute("SELECT * FROM people")
        }
        target_people = {
            row["id"]: tuple(row[key] for key in (
                "name", "birth_year", "gender", "marital_status", "branch",
                "legacy_relation_en", "legacy_relation_ur", "note_en", "note_ur",
                "photo_path", "display_order",
            ))
            for row in target.execute("SELECT * FROM people")
        }
        assert target_people == source_people

        assert sorted(
            (id_map[r["parent_id"]], id_map[r["child_id"]], r["role"], r["kind"])
            for r in source.execute("SELECT * FROM parent_child")
        ) == sorted(
            (r["parent_id"], r["child_id"], r["role"], r["kind"])
            for r in target.execute("SELECT * FROM parent_child")
        )

        assert sorted(
            (
                min(id_map[r["spouse_a"]], id_map[r["spouse_b"]]),
                max(id_map[r["spouse_a"]], id_map[r["spouse_b"]]),
                r["status"], r["year"], r["children_status"], r["display_order"],
            )
            for r in source.execute("SELECT * FROM marriages")
        ) == sorted(
            (r["spouse_a"], r["spouse_b"], r["status"], r["year"], r["children_status"], r["display_order"])
            for r in target.execute("SELECT * FROM marriages")
        )

        for table, columns in {
            "sibling_groups": "id,is_ordered,type,label_en,label_ur,display_order",
            "sources": "id,batch_number,file_path,title,kind,recorded_on",
            "review_notes": "id,status,text,display_order",
            "groups": "id,name,slug,kind,display_order",
        }.items():
            assert _rows(source, f"SELECT {columns} FROM {table} ORDER BY {columns}") == _rows(
                target, f"SELECT {columns} FROM {table} ORDER BY {columns}"
            )

        assert sorted(
            (r["group_id"], id_map[r["person_id"]], r["member_order"])
            for r in source.execute("SELECT * FROM sibling_group_members")
        ) == sorted(
            (r["group_id"], r["person_id"], r["member_order"])
            for r in target.execute("SELECT * FROM sibling_group_members")
        )
        assert sorted(
            (id_map[r["person_id"]], r["group_id"], r["is_primary"])
            for r in source.execute("SELECT * FROM person_groups")
        ) == sorted(
            (r["person_id"], r["group_id"], r["is_primary"])
            for r in target.execute("SELECT * FROM person_groups")
        )
        assert sorted(
            (id_map[r["person_id"]], r["alias"], r["display_order"])
            for r in source.execute("SELECT * FROM aliases")
        ) == sorted(
            (r["person_id"], r["alias"], r["display_order"])
            for r in target.execute("SELECT * FROM aliases")
        )

        source_general = []
        for row in source.execute("SELECT * FROM general_relationships"):
            mapped_a = id_map[row["person_a"]]
            mapped_b = id_map[row["person_b"]]
            first, second = sorted((mapped_a, mapped_b))
            label_forward = row["label_a_to_b"]
            label_reverse = row["label_b_to_a"]
            if (first, second) != (mapped_a, mapped_b):
                label_forward, label_reverse = label_reverse, label_forward
            source_general.append(
                (
                    first, second, row["type"], row["directionality"],
                    id_map.get(row["direction_from"], row["direction_from"]),
                    label_forward, label_reverse, row["notes"],
                    row["created_at"], row["updated_at"],
                )
            )
        target_general = [
            tuple(row[key] for key in (
                "person_a", "person_b", "type", "directionality", "direction_from",
                "label_a_to_b", "label_b_to_a", "notes", "created_at", "updated_at",
            ))
            for row in target.execute("SELECT * FROM general_relationships")
        ]
        assert sorted(source_general) == sorted(target_general)

        def translate_fact_key(entity_type: str, entity_key: str) -> str:
            if entity_type == "people":
                return id_map.get(entity_key, entity_key)
            parts = entity_key.split("|", 1)
            if entity_type == "aliases":
                return "|".join((id_map.get(parts[0], parts[0]), *parts[1:]))
            if entity_type == "parent_child":
                return "|".join(id_map.get(part, part) for part in parts)
            if entity_type == "marriages" and len(parts) == 2:
                return "|".join(sorted(id_map.get(part, part) for part in parts))
            if entity_type == "sibling_group_members" and len(parts) == 2:
                return f"{parts[0]}|{id_map.get(parts[1], parts[1])}"
            return entity_key

        assert sorted(
            (
                row["source_id"], row["entity_type"],
                translate_fact_key(row["entity_type"], row["entity_key"]), row["note"],
            )
            for row in source.execute("SELECT * FROM fact_sources")
        ) == sorted(
            (row["source_id"], row["entity_type"], row["entity_key"], row["note"])
            for row in target.execute("SELECT * FROM fact_sources")
        )

        source_metadata = dict(source.execute("SELECT key,value FROM metadata"))
        target_metadata = dict(target.execute("SELECT key,value FROM metadata"))
        for key, value in source_metadata.items():
            if key == "focus_person":
                assert target_metadata[key] == id_map[value]
            elif key == "app_schema_version":
                assert target_metadata[key] == "3"
            elif key == "_source_of_truth":
                assert target_metadata[key] == "relationships.db"
            elif key == "app_name":
                assert target_metadata[key] == "Mosaic"
            elif key == "app_version":
                assert target_metadata[key] == "0.5.0"
            else:
                assert target_metadata[key] == value
    finally:
        source.close()
        target.close()


def test_all_ordered_pair_family_semantics_match_legacy(tmp_path):
    root = _migrated_root(tmp_path)
    legacy = family_engine.read_sqlite_model(root / "Database" / "Main" / "family.db")
    canonical = family_engine.read_sqlite_model(root / "Database" / "relationships.db")
    id_map = canonical["identifier_aliases"]
    legacy_index = {person["id"]: person for person in legacy["people"]}
    canonical_index = {person["id"]: person for person in canonical["people"]}

    def signature(pair: dict) -> tuple:
        fields = ("en", "ur", "group", "degree", "removal", "side", "kind", "role")
        return tuple(
            sorted(
                tuple(item.get(field) for field in fields)
                for item in pair["main"] + pair["additional"]
            )
        )

    legacy_ids = sorted(legacy_index)
    assert len(legacy_ids) == 35
    for first in legacy_ids:
        for second in legacy_ids:
            legacy_pair = family_engine._viewer_pair(legacy, first, second, legacy_index)
            canonical_pair = family_engine._viewer_pair(
                canonical,
                id_map[first],
                id_map[second],
                canonical_index,
            )
            assert signature(canonical_pair) == signature(legacy_pair), f"{first} -> {second}"


def test_canonical_ids_are_safe_in_every_mermaid_identifier(tmp_path):
    root = _migrated_root(tmp_path)
    canonical = family_engine.read_sqlite_model(root / "Database" / "relationships.db")
    diagram = family_engine.build_mermaid(canonical)

    identifier_tokens = re.findall(r"(?:subgraph|class|style)\s+([^\s;]+)", diagram)
    assert identifier_tokens
    assert all("--" not in token for token in identifier_tokens)


def test_exact_template_journal_bytes_facts_and_idempotency(tmp_path):
    root = _legacy_root(tmp_path)
    legacy_hash = _sha256(root / "Database" / "Main" / "family.db")
    legacy_journals = _tree_hashes(root / "Database" / "People")
    first = migration.execute_migration(root)
    mapping = {row["old_id"]: row for row in first["mappings"]}

    for old_id, entry in mapping.items():
        folder = root / "People" / entry["category"] / entry["canonical_id"]
        assert {path.name for path in folder.iterdir()} == {
            f"{entry['canonical_id']}(facts and about).md",
            "journal(personal thoughts).md",
            *FOLDER_TEMPLATE_DIRECTORIES,
        }
        source_journal = root / "Database" / "People" / "Family" / old_id / "journal.md"
        if source_journal.is_file():
            assert (folder / "journal(personal thoughts).md").read_bytes() == source_journal.read_bytes()
        facts = (folder / f"{entry['canonical_id']}(facts and about).md").read_text(encoding="utf-8")
        assert "- **Created**: Unknown" in facts
        assert "- **Updated**: Unknown" in facts
        assert "- **Contact Status**: Unknown" in facts

    canonical_db_hash = _sha256(root / "Database" / "relationships.db")
    canonical_people_hashes = _tree_hashes(root / "People")
    second = migration.execute_migration(root)
    third = migration.execute_migration(root)
    assert second["already_migrated"] is True
    assert third["already_migrated"] is True
    assert _sha256(root / "Database" / "relationships.db") == canonical_db_hash
    assert _tree_hashes(root / "People") == canonical_people_hashes
    assert _sha256(root / "Database" / "Main" / "family.db") == legacy_hash
    assert _tree_hashes(root / "Database" / "People") == legacy_journals


@pytest.mark.parametrize(
    "failpoint",
    [
        "before_db_staging",
        "during_db_migration",
        "after_db_transformation",
        "during_folder_staging",
        "during_journal_copy",
        "after_validation_before_publish",
        "after_people_publish_before_db_publish",
        "during_publication",
        "during_final_verification",
    ],
)
def test_failure_injection_rolls_back_and_reruns(tmp_path, monkeypatch, failpoint):
    root = _legacy_root(tmp_path)
    legacy_hash = _sha256(root / "Database" / "Main" / "family.db")
    journal_hashes = _tree_hashes(root / "Database" / "People")
    monkeypatch.setattr(migration, "_MIGRATION_FAILPOINT", failpoint)
    with pytest.raises(RuntimeError, match="Injected canonical migration failure"):
        migration.execute_migration(root)
    assert not (root / "Database" / "relationships.db").exists()
    assert not (root / "People").exists()
    assert not (root / ".migration_incomplete.json").exists()
    assert _sha256(root / "Database" / "Main" / "family.db") == legacy_hash
    assert _tree_hashes(root / "Database" / "People") == journal_hashes

    monkeypatch.setattr(migration, "_MIGRATION_FAILPOINT", None)
    assert migration.execute_migration(root)["ok"] is True


def test_canonical_backup_restore_round_trip_and_runtime_authority(tmp_path):
    root = _migrated_root(tmp_path / "source")
    backup = create_backup("audit canonical round trip", root=root)
    verification = verify_backup(Path(backup["path"]))
    assert verification["ok"] is True
    assert "source_root" not in verification["manifest"]
    assert verification["manifest"]["sqlite_schema_version"] == 3

    destination = tmp_path / "restored-canonical"
    destination.mkdir()
    restored = restore_backup(
        Path(backup["path"]),
        root=destination,
        _require_safety_backup=False,
    )
    assert restored["ok"] is True
    assert DataRootManager.get_database_path(destination) == destination / "Database" / "relationships.db"
    assert _tree_hashes(destination / "People") == _tree_hashes(root / "People")

    legacy_database = destination / "Database" / "Main" / "family.db"
    assert not legacy_database.exists()
    DataRootManager.set_override_root(destination)
    try:
        created = people_service.create_person(name="Concurrent Name", category="Friends")
        assert created["id"] == "concurrent_name--CN01"
        assert (destination / "People" / "Friends" / created["id"]).is_dir()
    finally:
        DataRootManager.set_override_root(None)
    assert not legacy_database.exists()


def test_legacy_backup_restores_as_legacy_not_canonical(tmp_path):
    backup = REPO / "Backups" / "Safety" / "Pre-Upgrade" / "backup-20260919T184332151Z-0d52d225-pre-phase11"
    assert verify_backup(backup)["ok"] is True
    destination = tmp_path / "restored-legacy"
    destination.mkdir()
    restored = restore_backup(
        backup,
        root=destination,
        _require_safety_backup=False,
    )
    assert restored["ok"] is True
    assert not (destination / "Database" / "relationships.db").exists()
    assert DataRootManager.get_database_path(destination) == destination / "Database" / "Main" / "family.db"
    assert DataRootManager.get_people_dir(destination) == destination / "Database" / "People"


def test_legacy_backup_replaces_an_existing_canonical_root(tmp_path):
    backup = REPO / "Backups" / "Safety" / "Pre-Upgrade" / "backup-20260919T184332151Z-0d52d225-pre-phase11"
    destination = _migrated_root(tmp_path / "canonical-destination")
    assert (destination / "Database" / "HISTORICAL_FAMILY_DB.md").is_file()

    restored = restore_backup(
        backup,
        root=destination,
        _require_safety_backup=False,
    )

    assert restored["ok"] is True
    assert not (destination / "Database" / "relationships.db").exists()
    assert not (destination / "Database" / "HISTORICAL_FAMILY_DB.md").exists()
    assert not (destination / "People").exists()
    assert DataRootManager.get_database_path(destination) == destination / "Database" / "Main" / "family.db"
    assert DataRootManager.get_people_dir(destination) == destination / "Database" / "People"


def test_duplicate_name_concurrency_never_duplicates_identity(tmp_path):
    root = _migrated_root(tmp_path)
    DataRootManager.set_override_root(root)
    try:
        def create() -> str:
            return people_service.create_person(name="Sara Khan", category="Friends")["id"]

        outcomes: list[str] = []
        errors: list[Exception] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            for future in futures:
                try:
                    outcomes.append(future.result())
                except Exception as exc:  # A lock/unique failure is safe; duplication is not.
                    errors.append(exc)
        connection = _connect(root / "Database" / "relationships.db")
        try:
            ids = [row[0] for row in connection.execute("SELECT id FROM people WHERE name='Sara Khan'")]
        finally:
            connection.close()
        assert len(ids) == len(set(ids))
        assert set(outcomes).issubset(set(ids))
        assert ids
        assert all(value in {"sara_khan--SK01", "sara_khan--SK02"} for value in ids)
        assert len(outcomes) + len(errors) == 2
    finally:
        DataRootManager.set_override_root(None)


def test_identifier_alias_constraints_reject_missing_target(tmp_path):
    root = _migrated_root(tmp_path)
    connection = _connect(root / "Database" / "relationships.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO identifier_aliases
                  (old_identifier, canonical_id, entity_type, notes, created_at)
                VALUES ('stale-id', 'missing_person--MP01', 'person', NULL, '2026-01-01T00:00:00Z')
                """
            )
    finally:
        connection.close()


def test_all_runtime_mutations_stay_on_canonical_authority(tmp_path):
    root = _migrated_root(tmp_path)
    legacy_db = root / "Database" / "Main" / "family.db"
    legacy_people = root / "Database" / "People"
    legacy_db_hash = _sha256(legacy_db)
    legacy_people_hashes = _tree_hashes(legacy_people)

    DataRootManager.set_override_root(root)
    try:
        first = people_service.create_person(
            name="Runtime Parent",
            aliases=["Stable Runtime Alias"],
            category="Family",
            group_ids=["family", "friends"],
        )
        second = people_service.create_person(
            name="Runtime Child",
            category="Family",
            group_ids=["family"],
        )
        original_id = first["id"]
        updated = people_service.update_person(
            original_id,
            name="Renamed Runtime Parent",
            group_ids=["family", "friends"],
            primary_group_id="friends",
        )
        assert updated["id"] == original_id
        assert (root / "People" / "Family" / original_id).is_dir()
        assert not (root / "People" / "Friends" / original_id).exists()

        journal_service.append_journal(original_id, "Canonical-only journal mutation.", heading="Audit")
        family_service.add_parent_child(parent_id=original_id, child_id=second["id"])
        general_service.add_general_relationship(
            person_a=original_id,
            person_b=second["id"],
            type="friend",
        )
        legacy_general = general_service.add_general_relationship(
            person_a="mohammad_yahya_hussain",
            person_b="aresha_zubair",
            type="friend",
        )
        assert legacy_general["person_a"] == "aresha_zubair--AZ01"
        assert legacy_general["person_b"] == "mohammad_yahya_hussain--MYH01"
        assert general_service.list_general_relationships("mohammad_yahya_hussain")
        updated_parent = family_service.update_parent_child(
            "irsa_naz",
            "mohammad_yahya_hussain",
            role="mother",
            kind="biological",
        )
        assert updated_parent["parent_id"] == "irsa_naz--IN01"
        assert updated_parent["child_id"] == "mohammad_yahya_hussain--MYH01"
        updated_marriage = family_service.update_marriage(
            "irsa_naz",
            "mansoor_hussain",
            status="married",
        )
        assert {updated_marriage["person_a"], updated_marriage["person_b"]} == {
            "irsa_naz--IN01",
            "mansoor_hussain--MH01",
        }

        connection = _connect(root / "Database" / "relationships.db")
        try:
            assert db.resolve_canonical_id(connection, "mohammad_yahya_hussain") == (
                "mohammad_yahya_hussain--MYH01"
            )
            assert connection.execute(
                "SELECT 1 FROM parent_child WHERE parent_id=? AND child_id=?",
                (original_id, second["id"]),
            ).fetchone()
            pair = tuple(sorted((original_id, second["id"])))
            assert connection.execute(
                "SELECT 1 FROM general_relationships WHERE person_a=? AND person_b=?",
                pair,
            ).fetchone()
            memberships = {
                row[0]
                for row in connection.execute(
                    "SELECT group_id FROM person_groups WHERE person_id=?", (original_id,)
                )
            }
            assert memberships == {"family", "friends"}
        finally:
            connection.close()

        journal_path = root / "People" / "Family" / original_id / "journal(personal thoughts).md"
        assert "Canonical-only journal mutation." in journal_path.read_text(encoding="utf-8")
    finally:
        DataRootManager.set_override_root(None)

    assert _sha256(legacy_db) == legacy_db_hash
    assert _tree_hashes(legacy_people) == legacy_people_hashes
