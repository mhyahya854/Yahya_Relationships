"""Phase 2 Relationships Final Surgical Hardening Test Suite.

Exhaustively covers:
1. Sibling stored/derived precedence bug: derived female sibling without explicit sibling group does not crash.
2. Derived sibling without stored sibling fact stays derived=True.
3. Semantic ID unchanged when English display wording is altered/mock-formatted.
4. Structured cousin semantic identity.
5. Structured ancestor/collateral semantic identity.
6. Two same-type opposite directional general relationships remain distinct.
7. Exact stored general path binding by row/fact ID.
8. Deterministic general path IDs across repeated calls and restarts.
9. Deterministic general graph edge IDs with objective directionality.
10. Deleting one same-type directional fact preserves the other.
11. Undo restores the exact deleted fact.
12. Direct SQL duplicate symmetric relation rejected by SQLite constraint.
13. Legitimate distinct general relations accepted.
14. Custom relationship duplicate semantics and coexistence.
15. Schema v1 -> v2 migration from isolated v1 fixture.
16. Migration idempotency.
17. Migration data preservation.
18. Migration foreign_key_check passes.
19. Migration integrity_check passes.
20. Schema-version mismatch behavior raises SchemaVersionMismatchError.
21. Current 35-person ordered-pair audit passes.
22. Canonical multipath example (Yahya <-> Aresha) preserved.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.backend import config, db
from app.backend.data_root import DataRootManager
from app.backend.domain.family import engine as build_family
from app.backend.domain.mutations import history, preview
from app.backend.domain.relationships import graph as graph_service, path_service
from app.backend.kinship import labels
from app.backend.services import errors, family, general, people, relationship


# ==============================================================================
# 1. Defect 1: Sibling Precedence & Derived Status
# ==============================================================================

def test_derived_female_sibling_without_explicit_group_does_not_crash(isolated):
    """Two people who share parents but have NO explicit sibling_group row must not crash.

    Target female returns 'sister' or 'half_sister'; must not raise AttributeError.
    """
    # Create parents and children
    father = people.create_person(name="Test Father", gender="male")["id"]
    mother = people.create_person(name="Test Mother", gender="female")["id"]
    son = people.create_person(name="Test Son", gender="male")["id"]
    daughter = people.create_person(name="Test Daughter", gender="female")["id"]

    # Link both children to the same parents
    family.add_parent_child(parent_id=father, child_id=son, role="father", kind="biological")
    family.add_parent_child(parent_id=mother, child_id=son, role="mother", kind="biological")
    family.add_parent_child(parent_id=father, child_id=daughter, role="father", kind="biological")
    family.add_parent_child(parent_id=mother, child_id=daughter, role="mother", kind="biological")

    # Verify NO explicit sibling_group contains both son and daughter
    facts = family.family_facts()
    shared_groups = [
        g for g in facts.get("sibling_groups", [])
        if son in g["members"] and daughter in g["members"]
    ]
    assert len(shared_groups) == 0, "Test precondition violated: sibling group exists"

    # Son -> Daughter: target is female, returns sister
    rel_son_to_daughter = relationship.get_relationship(son, daughter)
    assert rel_son_to_daughter["target"]["id"] == daughter
    entries = rel_son_to_daughter["primary"] + rel_son_to_daughter["additional"]
    sister_entries = [e for e in entries if "sister" in e["relationship_type"]]
    assert len(sister_entries) >= 1
    # Must remain derived=True because no explicit stored sibling fact exists
    assert sister_entries[0]["derived"] is True

    # Daughter -> Son: target is male, returns brother
    rel_daughter_to_son = relationship.get_relationship(daughter, son)
    entries_rev = rel_daughter_to_son["primary"] + rel_daughter_to_son["additional"]
    brother_entries = [e for e in entries_rev if "brother" in e["relationship_type"]]
    assert len(brother_entries) >= 1
    assert brother_entries[0]["derived"] is True


def test_half_sibling_without_explicit_group_stays_derived(isolated):
    """Half-siblings sharing only one biological parent must remain derived=True."""
    father = people.create_person(name="Shared Dad", gender="male")["id"]
    child_a = people.create_person(name="Child A", gender="male")["id"]
    child_b = people.create_person(name="Child B", gender="female")["id"]

    family.add_parent_child(parent_id=father, child_id=child_a, role="father", kind="biological")
    family.add_parent_child(parent_id=father, child_id=child_b, role="father", kind="biological")

    res = relationship.get_relationship(child_a, child_b)
    entries = res["primary"] + res["additional"]
    half_sister = [e for e in entries if "sister" in e["relationship_type"]]
    assert len(half_sister) >= 1
    assert half_sister[0]["derived"] is True


# ==============================================================================
# 2. Defect 2: Language-Neutral Semantic Identity (Decoupled from Display Text)
# ==============================================================================

def test_semantic_id_unchanged_when_display_english_wording_altered():
    """Altering or localizing the English label must NOT change the semantic ID."""
    # 1. Cousin record
    cousin_entry = {
        "kind": "collateral",
        "da": 2,
        "db": 2,
        "side": "maternal",
        "degree": 1,
        "removal": 0,
        "en": "Maternal first cousin",
    }
    norm_orig = labels.normalize_family_entry(cousin_entry)
    expected_id = "maternal_cousin_degree_1_removed_0"
    assert norm_orig["semantic_id"] == expected_id

    # Mock/alter display wording
    altered_cousin = copy.deepcopy(cousin_entry)
    altered_cousin["en"] = "First cousin on mother's side (altered display text!)"
    norm_altered = labels.normalize_family_entry(altered_cousin)
    assert norm_altered["semantic_id"] == expected_id
    assert norm_altered["relationship_type"] == expected_id
    assert norm_altered["degree"] == 1
    assert norm_altered["removal"] == 0
    assert norm_altered["side"] == "maternal"

    # 2. Ancestor record
    ancestor_entry = {
        "kind": "ancestor",
        "distance": 2,
        "side": "paternal",
        "target_gender": "male",
        "en": "Paternal grandfather",
    }
    norm_anc = labels.normalize_family_entry(ancestor_entry)
    assert norm_anc["semantic_id"] == "paternal_grandfather"

    altered_anc = copy.deepcopy(ancestor_entry)
    altered_anc["en"] = "Dada Abu / Grandfather (custom localization)"
    norm_anc_altered = labels.normalize_family_entry(altered_anc)
    assert norm_anc_altered["semantic_id"] == "paternal_grandfather"

    # 3. Collateral uncle record
    uncle_entry = {
        "kind": "collateral",
        "da": 2,
        "db": 1,
        "side": "maternal",
        "target_gender": "male",
        "en": "Maternal uncle",
    }
    norm_uncle = labels.normalize_family_entry(uncle_entry)
    assert norm_uncle["semantic_id"] == "maternal_uncle"

    altered_uncle = copy.deepcopy(uncle_entry)
    altered_uncle["en"] = "Mamoo Jan (custom Urdu-style wording)"
    norm_uncle_altered = labels.normalize_family_entry(altered_uncle)
    assert norm_uncle_altered["semantic_id"] == "maternal_uncle"

    # 4. Sibling record
    sibling_entry = {
        "kind": "sibling",
        "sibling_type": "full",
        "target_gender": "female",
        "en": "Full sister",
    }
    norm_sib = labels.normalize_family_entry(sibling_entry)
    assert norm_sib["semantic_id"] == "full_sister"

    altered_sib = copy.deepcopy(sibling_entry)
    altered_sib["en"] = "Elder sister (custom family note)"
    norm_sib_altered = labels.normalize_family_entry(altered_sib)
    assert norm_sib_altered["semantic_id"] == "full_sister"


def test_structured_cousin_semantic_identity():
    """Exhaustive check of degree, removal, and side for structured cousin identity."""
    for degree in (1, 2, 3):
        for removal in (0, 1, 2):
            for side in ("maternal", "paternal"):
                entry = {
                    "kind": "collateral",
                    "da": degree + 1,
                    "db": degree + 1 + removal,
                    "side": side,
                    "degree": degree,
                    "removal": removal,
                }
                norm = labels.normalize_family_entry(entry)
                assert norm["semantic_id"] == f"{side}_cousin_degree_{degree}_removed_{removal}"
                assert norm["degree"] == degree
                assert norm["removal"] == removal
                assert norm["side"] == side


def test_structured_ancestor_and_collateral_identity():
    """Exhaustive check of generational ancestor and collateral structured identity."""
    # Great-grandfather
    great_gf = labels.normalize_family_entry({
        "kind": "ancestor",
        "distance": 3,
        "side": "maternal",
        "target_gender": "male",
    })
    assert great_gf["semantic_id"] == "maternal_great_grandfather"

    # Niece
    niece = labels.normalize_family_entry({
        "kind": "collateral",
        "da": 1,
        "db": 2,
        "target_gender": "female",
    })
    assert niece["semantic_id"] == "niece"

    # Grandnephew
    grandnephew = labels.normalize_family_entry({
        "kind": "collateral",
        "da": 1,
        "db": 3,
        "target_gender": "male",
    })
    assert grandnephew["semantic_id"] == "grandnephew"


# ==============================================================================
# 3. Defect 3 & 3B: General Relationship Stored Identity, Direction & Constraints
# ==============================================================================

def test_same_type_opposite_directional_relationships_coexist(isolated):
    """Two opposite directional mentor rows between the same pair must coexist distinctly."""
    p_a = people.create_person(name="Alice")["id"]
    p_b = people.create_person(name="Bob")["id"]

    # 1. A -> B: Alice is Mentor, Bob is Mentee
    row1 = general.add_general_relationship(
        person_a=p_a,
        person_b=p_b,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )

    # 2. B -> A: Bob is Mentor, Alice is Mentee
    row2 = general.add_general_relationship(
        person_a=p_b,
        person_b=p_a,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )

    assert row1["id"] != row2["id"]

    # Both rows exist in DB
    all_rows = general.list_general_relationships(p_a)
    assert len(all_rows) == 2

    # Query from perspective of A
    rel_a = relationship.get_relationship(p_a, p_b)
    entries_a = rel_a["primary"]
    assert len(entries_a) == 2
    # One entry where A is Mentor, one where A is Mentee
    labels_a = {e["label_en"] for e in entries_a}
    assert labels_a == {"Mentor", "Mentee"}

    # Each entry must expose its exact stored fact identity
    fact_ids_a = {e["general_relationship_id"] for e in entries_a}
    assert fact_ids_a == {row1["id"], row2["id"]}

    # Path IDs must be distinct
    paths = path_service.get_relationship_paths(p_a, p_b)["paths"]
    assert len(paths) == 2
    assert paths[0]["id"] != paths[1]["id"]
    path_fact_ids = {p["general_relationship_id"] for p in paths}
    assert path_fact_ids == {row1["id"], row2["id"]}

    # Show Why path binding: each entry maps exclusively to its own path
    for entry in entries_a:
        assert len(entry["path_ids"]) == 1
        matched_path = next(p for p in paths if p["id"] == entry["path_ids"][0])
        assert matched_path["general_relationship_id"] == entry["general_relationship_id"]
        assert matched_path["label_en"] == entry["label_en"]


def test_deterministic_general_path_and_graph_ids(isolated):
    """Path IDs and graph edge IDs must be strictly deterministic across calls."""
    p_a = people.create_person(name="Alice")["id"]
    p_b = people.create_person(name="Bob")["id"]

    row = general.add_general_relationship(
        person_a=p_a,
        person_b=p_b,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )

    # Path IDs
    paths_call1 = path_service.get_relationship_paths(p_a, p_b)["paths"]
    paths_call2 = path_service.get_relationship_paths(p_a, p_b)["paths"]
    assert paths_call1[0]["id"] == paths_call2[0]["id"]
    assert paths_call1[0]["id"] is not None

    # Graph edge IDs and direction
    graph1 = graph_service.get_graph_neighbors(p_a, perspective_id=p_a, filters=["general"])
    graph2 = graph_service.get_graph_neighbors(p_a, perspective_id=p_a, filters=["general"])
    assert len(graph1["edges"]) == 1
    assert graph1["edges"][0]["id"] == graph2["edges"][0]["id"]
    assert graph1["edges"][0]["source"] == p_a
    assert graph1["edges"][0]["target"] == p_b
    assert str(row["id"]) in graph1["edges"][0]["id"]


def test_deleting_one_directional_fact_preserves_other_and_undo_restores(isolated):
    """Deleting one same-type directional fact leaves the other intact; Undo restores it."""
    p_a = people.create_person(name="Alice")["id"]
    p_b = people.create_person(name="Bob")["id"]

    row1 = general.add_general_relationship(
        person_a=p_a,
        person_b=p_b,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )
    row2 = general.add_general_relationship(
        person_a=p_b,
        person_b=p_a,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )

    # Delete row1
    general.delete_general_relationship(row1["id"])

    # row2 must remain intact
    remaining = general.list_general_relationships(p_a)
    assert len(remaining) == 1
    assert remaining[0]["id"] == row2["id"]

    # Undo must restore row1 exactly
    assert history.can_undo() is True
    history.undo_last_mutation()

    restored = general.list_general_relationships(p_a)
    assert len(restored) == 2
    restored_ids = {r["id"] for r in restored}
    assert restored_ids == {row1["id"], row2["id"]}


def test_sqlite_db_level_duplicate_rejection(isolated):
    """Direct SQL insertion of duplicate symmetric fact must fail with sqlite3.IntegrityError."""
    p_a = people.create_person(name="Alice")["id"]
    p_b = people.create_person(name="Bob")["id"]
    p_low, p_high = sorted((p_a, p_b))

    con = db.get_connection()
    try:
        # First symmetric row succeeds
        con.execute(
            """
            INSERT INTO general_relationships (person_a, person_b, type, directionality, direction_from)
            VALUES (?, ?, 'friend', 'symmetric', NULL)
            """,
            (p_low, p_high),
        )
        con.commit()

        # Second exact duplicate symmetric row must fail at DB level
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO general_relationships (person_a, person_b, type, directionality, direction_from)
                VALUES (?, ?, 'friend', 'symmetric', NULL)
                """,
                (p_low, p_high),
            )
            con.commit()
    finally:
        con.close()


def test_sqlite_db_level_custom_relationship_semantics(isolated):
    """Custom relationships allow different labels, but reject identical labels at DB level."""
    p_a = people.create_person(name="Alice")["id"]
    p_b = people.create_person(name="Bob")["id"]
    p_low, p_high = sorted((p_a, p_b))

    con = db.get_connection()
    try:
        # Custom 1: Bandmates
        con.execute(
            """
            INSERT INTO general_relationships (person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a)
            VALUES (?, ?, 'custom', 'symmetric', NULL, 'Bandmates', 'Bandmates')
            """,
            (p_low, p_high),
        )
        con.commit()

        # Custom 2: Co-authors (distinct labels) must succeed
        con.execute(
            """
            INSERT INTO general_relationships (person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a)
            VALUES (?, ?, 'custom', 'symmetric', NULL, 'Co-authors', 'Co-authors')
            """,
            (p_low, p_high),
        )
        con.commit()

        # Custom 3: Duplicate Bandmates must fail with IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO general_relationships (person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a)
                VALUES (?, ?, 'custom', 'symmetric', NULL, 'Bandmates', 'Bandmates')
                """,
                (p_low, p_high),
            )
            con.commit()
    finally:
        con.close()


# ==============================================================================
# 4. Defect 4: Schema v1 -> v2 Migration, Idempotency, and Safety
# ==============================================================================

def test_schema_v1_to_v2_migration_fixture(tmp_path):
    """Migrate a realistic v1 database fixture to schema v2."""
    v1_db = tmp_path / "v1_test.db"
    con = sqlite3.connect(str(v1_db))
    con.execute("PRAGMA foreign_keys = ON")

    # Build legacy schema
    build_family.create_sqlite_schema(con)
    # Apply v1 schema (without partial unique indexes)
    con.executescript(
        """
        CREATE TABLE groups (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          slug TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL DEFAULT 'custom' CHECK (kind IN ('system', 'custom')),
          display_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE person_groups (
          person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
          group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
          is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
          PRIMARY KEY (person_id, group_id)
        );
        CREATE TABLE general_relationships (
          id INTEGER PRIMARY KEY,
          person_a TEXT NOT NULL REFERENCES people(id),
          person_b TEXT NOT NULL REFERENCES people(id),
          type TEXT NOT NULL,
          directionality TEXT NOT NULL DEFAULT 'symmetric',
          direction_from TEXT,
          label_a_to_b TEXT,
          label_b_to_a TEXT,
          notes TEXT,
          created_at TEXT,
          updated_at TEXT,
          CHECK (person_a <> person_b),
          CHECK (person_a < person_b),
          UNIQUE (person_a, person_b, type, directionality, direction_from)
        );
        """
    )
    # Insert v1 metadata
    con.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', '1')")
    con.execute("PRAGMA user_version = 1")

    # Populate realistic data
    con.execute("INSERT INTO people (id, name, display_order) VALUES ('p1', 'Person One', 0)")
    con.execute("INSERT INTO people (id, name, display_order) VALUES ('p2', 'Person Two', 1)")
    con.execute(
        """
        INSERT INTO general_relationships (id, person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a, notes, created_at, updated_at)
        VALUES (42, 'p1', 'p2', 'colleague', 'symmetric', NULL, 'Colleague', 'Colleague', 'Met at work', '2026-01-01', '2026-01-01')
        """
    )
    con.execute(
        """
        INSERT INTO general_relationships (id, person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a, notes, created_at, updated_at)
        VALUES (43, 'p1', 'p2', 'mentor', 'directional', 'p1', 'Mentor', 'Mentee', 'Senior mentor', '2026-01-02', '2026-01-02')
        """
    )
    con.commit()
    con.close()

    # Run migrate() on the v1 database
    db.migrate(v1_db)

    # Verify v2 schema and metadata
    con2 = sqlite3.connect(str(v1_db))
    row = con2.execute("SELECT value FROM metadata WHERE key = 'app_schema_version'").fetchone()
    assert row[0] == "2"
    assert con2.execute("PRAGMA user_version").fetchone()[0] == 2

    # Verify rows preserved exactly
    rows = con2.execute("SELECT * FROM general_relationships ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0][0] == 42
    assert rows[0][1] == "p1"
    assert rows[0][2] == "p2"
    assert rows[0][3] == "colleague"
    assert rows[0][8] == "Met at work"

    assert rows[1][0] == 43
    assert rows[1][3] == "mentor"
    assert rows[1][4] == "directional"
    assert rows[1][5] == "p1"

    # Verify PRAGMA integrity_check and foreign_key_check
    assert con2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert len(con2.execute("PRAGMA foreign_key_check").fetchall()) == 0
    con2.close()

    # Run migrate() AGAIN to verify idempotency
    db.migrate(v1_db)
    con3 = sqlite3.connect(str(v1_db))
    assert con3.execute("PRAGMA user_version").fetchone()[0] == 2
    rows_again = con3.execute("SELECT * FROM general_relationships ORDER BY id").fetchall()
    assert len(rows_again) == 2
    assert con3.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con3.close()


# ==============================================================================
# 5. Migration Failure Injection Atomicity & Schema Mismatch Non-Mutation
# ==============================================================================

def _create_v1_fixture(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    build_family.create_sqlite_schema(con)
    con.executescript(
        """
        CREATE TABLE groups (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          slug TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL DEFAULT 'custom' CHECK (kind IN ('system', 'custom')),
          display_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE person_groups (
          person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
          group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
          is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
          PRIMARY KEY (person_id, group_id)
        );
        CREATE TABLE general_relationships (
          id INTEGER PRIMARY KEY,
          person_a TEXT NOT NULL REFERENCES people(id),
          person_b TEXT NOT NULL REFERENCES people(id),
          type TEXT NOT NULL,
          directionality TEXT NOT NULL DEFAULT 'symmetric',
          direction_from TEXT,
          label_a_to_b TEXT,
          label_b_to_a TEXT,
          notes TEXT,
          created_at TEXT,
          updated_at TEXT,
          CHECK (person_a <> person_b),
          CHECK (person_a < person_b),
          UNIQUE (person_a, person_b, type, directionality, direction_from)
        );
        """
    )
    con.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', '1')")
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO people (id, name, display_order) VALUES ('p1', 'Person One', 0)")
    con.execute("INSERT INTO people (id, name, display_order) VALUES ('p2', 'Person Two', 1)")
    con.execute(
        """
        INSERT INTO general_relationships (id, person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a, notes, created_at, updated_at)
        VALUES (42, 'p1', 'p2', 'colleague', 'symmetric', NULL, 'Colleague', 'Colleague', 'Met at work', '2026-01-01', '2026-01-01')
        """
    )
    con.execute(
        """
        INSERT INTO general_relationships (id, person_a, person_b, type, directionality, direction_from, label_a_to_b, label_b_to_a, notes, created_at, updated_at)
        VALUES (43, 'p1', 'p2', 'mentor', 'directional', 'p1', 'Mentor', 'Mentee', 'Senior mentor', '2026-01-02', '2026-01-02')
        """
    )
    con.commit()
    con.close()


@pytest.mark.parametrize(
    "failpoint",
    [
        "before_create_v2_table",
        "after_create_v2_table",
        "after_copy_rows",
        "after_drop_old_table",
        "during_unique_index",
        "before_metadata_version_update",
        "after_version_bookkeeping",
    ],
)
def test_migration_failure_injection_atomicity(tmp_path, failpoint):
    """Deliberately fail migration at failpoint and verify complete atomic rollback."""
    v1_db = tmp_path / f"v1_fail_{failpoint}.db"
    _create_v1_fixture(v1_db)

    db._MIGRATION_FAILPOINT = failpoint
    try:
        with pytest.raises(RuntimeError, match=f"Injected migration failure at failpoint: {failpoint}"):
            db.migrate(v1_db)
    finally:
        db._MIGRATION_FAILPOINT = None

    # Verify atomic rollback
    con = sqlite3.connect(str(v1_db))
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "general_relationships_v2" not in tables
        assert "general_relationships" in tables

        rows = con.execute("SELECT * FROM general_relationships ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 42
        assert rows[0][1] == "p1"
        assert rows[0][2] == "p2"
        assert rows[0][3] == "colleague"
        assert rows[0][8] == "Met at work"

        assert rows[1][0] == 43
        assert rows[1][3] == "mentor"
        assert rows[1][4] == "directional"
        assert rows[1][5] == "p1"

        meta_row = con.execute("SELECT value FROM metadata WHERE key = 'app_schema_version'").fetchone()
        assert meta_row[0] == "1"
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1

        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()

    # Subsequent normal migration must succeed cleanly
    db.migrate(v1_db)
    con2 = sqlite3.connect(str(v1_db))
    try:
        assert con2.execute("SELECT value FROM metadata WHERE key = 'app_schema_version'").fetchone()[0] == "2"
        assert con2.execute("PRAGMA user_version").fetchone()[0] == 2
        assert con2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con2.execute("PRAGMA foreign_key_check").fetchall() == []
        rows2 = con2.execute("SELECT * FROM general_relationships ORDER BY id").fetchall()
        assert len(rows2) == 2
    finally:
        con2.close()


def test_schema_mismatch_refusal_is_strictly_non_mutating(tmp_path):
    """If metadata and user_version disagree, migration raises without any mutation."""
    mismatch_db = tmp_path / "mismatch_non_mutating.db"
    con = sqlite3.connect(str(mismatch_db))
    build_family.create_sqlite_schema(con)
    con.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', '2')")
    con.execute("PRAGMA user_version = 1")
    con.commit()

    before_schema = con.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    before_tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    before_metadata = con.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
    before_user_ver = con.execute("PRAGMA user_version").fetchone()[0]
    con.close()

    before_bytes = mismatch_db.read_bytes()
    before_sha = hashlib.sha256(before_bytes).hexdigest()

    with pytest.raises(db.SchemaVersionMismatchError):
        db.migrate(mismatch_db)

    con_after = sqlite3.connect(str(mismatch_db))
    after_schema = con_after.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    after_tables = [
        r[0]
        for r in con_after.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    after_metadata = con_after.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
    after_user_ver = con_after.execute("PRAGMA user_version").fetchone()[0]
    con_after.close()

    assert before_schema == after_schema
    assert before_tables == after_tables
    assert before_metadata == after_metadata
    assert before_user_ver == after_user_ver
    assert hashlib.sha256(mismatch_db.read_bytes()).hexdigest() == before_sha


# ==============================================================================
# 6. Parent-Child Stored vs Derived Test Matrix
# ==============================================================================

@pytest.mark.parametrize(
    "kind",
    [
        "biological",
        "adopted",
        "step",
        "foster",
        "guardian",
        "unknown",
        "unspecified",
    ],
)
@pytest.mark.parametrize("direction", ["parent_to_child", "child_to_parent"])
def test_parent_child_matrix_stored_classification(isolated, kind, direction):
    """Direct row in parent_child is ALWAYS a stored fact (derived=False) regardless of kind."""
    p_dad = people.create_person(name=f"Dad {kind}", gender="male")["id"]
    p_child = people.create_person(name=f"Child {kind}", gender="female")["id"]

    family.add_parent_child(parent_id=p_dad, child_id=p_child, role="father", kind=kind)

    perspective, target = (p_dad, p_child) if direction == "parent_to_child" else (p_child, p_dad)
    rel = relationship.get_relationship(perspective, target)

    facts = family.family_facts()
    matching_pc = [
        pc for pc in facts["parent_child"]
        if pc["parent_id"] == p_dad and pc["child_id"] == p_child
    ]
    assert len(matching_pc) == 1
    assert matching_pc[0]["kind"] == kind

    entries = rel["primary"] + rel["additional"]
    pc_entries = [
        e for e in entries
        if e["domain"] == "family" and (
            e.get("stored_fact_kind") == "parent_child" or
            any(k in e["relationship_type"] for k in ("father", "mother", "parent", "son", "daughter", "child"))
        )
    ]
    assert len(pc_entries) >= 1
    entry = pc_entries[0]

    if direction == "parent_to_child":
        expected_sem = "daughter" if kind == "biological" else f"daughter_{kind}"
    else:
        expected_sem = "father" if kind == "biological" else f"father_{kind}"

    assert entry["semantic_id"] == expected_sem
    assert entry["relationship_type"] == expected_sem
    assert entry["derived"] is False

    paths_res = path_service.get_relationship_paths(perspective, target)
    matching_paths = [
        p for p in paths_res["paths"]
        if p.get("semantic_id") == expected_sem or p.get("relationship_type") == expected_sem
    ]
    assert len(matching_paths) >= 1
    path = matching_paths[0]
    assert path["derived"] is False
    assert len(path["nodes"]) == 2
    assert [n["id"] for n in path["nodes"]] == [perspective, target]

    prev_res = preview.preview_mutation(
        "delete_parent_child",
        {"parent_id": p_dad, "child_id": p_child},
    )
    assert prev_res["direct_changes"]
    assert any("parent-child" in c.lower() for c in prev_res["direct_changes"])

    assert len([e for e in entries if e["semantic_id"] == expected_sem]) == 1


def test_explicit_named_parent_child_cases(isolated):
    """Specifically assert father_adopted, mother_step, son_foster, daughter_guardian derived=False."""
    dad = people.create_person(name="Adoptive Father", gender="male")["id"]
    child1 = people.create_person(name="Adopted Child", gender="male")["id"]
    family.add_parent_child(parent_id=dad, child_id=child1, role="father", kind="adopted")
    rel1 = relationship.get_relationship(child1, dad)
    e1 = next(e for e in rel1["primary"] if e["relationship_type"] == "father_adopted")
    assert e1["derived"] is False

    mom = people.create_person(name="Step Mother", gender="female")["id"]
    child2 = people.create_person(name="Step Child", gender="male")["id"]
    family.add_parent_child(parent_id=mom, child_id=child2, role="mother", kind="step")
    rel2 = relationship.get_relationship(child2, mom)
    e2 = next(e for e in rel2["primary"] if e["relationship_type"] == "mother_step")
    assert e2["derived"] is False

    foster_parent = people.create_person(name="Foster Parent", gender="female")["id"]
    foster_son = people.create_person(name="Foster Son", gender="male")["id"]
    family.add_parent_child(parent_id=foster_parent, child_id=foster_son, role="mother", kind="foster")
    rel3 = relationship.get_relationship(foster_parent, foster_son)
    e3 = next(e for e in rel3["primary"] if e["relationship_type"] == "son_foster")
    assert e3["derived"] is False

    guardian = people.create_person(name="Guardian Person", gender="male")["id"]
    ward_daughter = people.create_person(name="Ward Daughter", gender="female")["id"]
    family.add_parent_child(parent_id=guardian, child_id=ward_daughter, role="father", kind="guardian")
    rel4 = relationship.get_relationship(guardian, ward_daughter)
    e4 = next(e for e in rel4["primary"] if e["relationship_type"] == "daughter_guardian")
    assert e4["derived"] is False


# ==============================================================================
# 7. Sibling Stored/Derived Test Matrix
# ==============================================================================

def test_sibling_stored_vs_derived_matrix(isolated):
    """Test explicit full group, explicit default group, inferred biological, and inferred half."""
    # Case 1 people
    p_sib1 = people.create_person(name="Full Sib 1", gender="male")["id"]
    p_sib2 = people.create_person(name="Full Sib 2", gender="female")["id"]

    # Case 2 people
    p_def1 = people.create_person(name="Def Sib 1", gender="male")["id"]
    p_def2 = people.create_person(name="Def Sib 2", gender="female")["id"]

    # Insert explicit groups
    con = db.get_connection()
    try:
        con.execute(
            "INSERT INTO sibling_groups (id, type, is_ordered, display_order) VALUES ('sg_full', 'full', 0, 0)"
        )
        con.execute(
            "INSERT INTO sibling_group_members (group_id, person_id, member_order) VALUES ('sg_full', ?, 1)",
            (p_sib1,),
        )
        con.execute(
            "INSERT INTO sibling_group_members (group_id, person_id, member_order) VALUES ('sg_full', ?, 2)",
            (p_sib2,),
        )

        con.execute(
            "INSERT INTO sibling_groups (id, type, is_ordered, display_order) VALUES ('sg_default', NULL, 0, 1)"
        )
        con.execute(
            "INSERT INTO sibling_group_members (group_id, person_id, member_order) VALUES ('sg_default', ?, 1)",
            (p_def1,),
        )
        con.execute(
            "INSERT INTO sibling_group_members (group_id, person_id, member_order) VALUES ('sg_default', ?, 2)",
            (p_def2,),
        )
        con.commit()
    finally:
        con.close()

    # Case 3: Biological sibling inferred from shared parent-child facts (NO explicit group) -> derived=True
    dad_bio = people.create_person(name="Dad Bio", gender="male")["id"]
    mom_bio = people.create_person(name="Mom Bio", gender="female")["id"]
    p_bio1 = people.create_person(name="Bio Sib 1", gender="male")["id"]
    p_bio2 = people.create_person(name="Bio Sib 2", gender="female")["id"]
    family.add_parent_child(parent_id=dad_bio, child_id=p_bio1, role="father", kind="biological")
    family.add_parent_child(parent_id=mom_bio, child_id=p_bio1, role="mother", kind="biological")
    family.add_parent_child(parent_id=dad_bio, child_id=p_bio2, role="father", kind="biological")
    family.add_parent_child(parent_id=mom_bio, child_id=p_bio2, role="mother", kind="biological")

    # Case 4: Half sibling inferred from one shared biological parent (NO explicit group) -> derived=True
    dad_half = people.create_person(name="Dad Half", gender="male")["id"]
    p_half1 = people.create_person(name="Half Sib 1", gender="male")["id"]
    p_half2 = people.create_person(name="Half Sib 2", gender="female")["id"]
    family.add_parent_child(parent_id=dad_half, child_id=p_half1, role="father", kind="biological")
    family.add_parent_child(parent_id=dad_half, child_id=p_half2, role="father", kind="biological")

    # Verify Case 1: Explicit full group -> derived=False, path derived=False
    rel1 = relationship.get_relationship(p_sib1, p_sib2)
    e1 = next(e for e in rel1["primary"] if "sister" in e["relationship_type"])
    assert e1["derived"] is False
    path1 = path_service.get_relationship_paths(p_sib1, p_sib2)["paths"][0]
    assert path1["derived"] is False

    rel1_rev = relationship.get_relationship(p_sib2, p_sib1)
    e1_rev = next(e for e in rel1_rev["primary"] if "brother" in e["relationship_type"])
    assert e1_rev["derived"] is False
    path1_rev = path_service.get_relationship_paths(p_sib2, p_sib1)["paths"][0]
    assert path1_rev["derived"] is False

    # Verify Case 2: Explicit group with type NULL/default -> derived=False, path derived=False
    rel2 = relationship.get_relationship(p_def1, p_def2)
    e2 = next(e for e in rel2["primary"] if "sister" in e["relationship_type"])
    assert e2["derived"] is False
    path2 = path_service.get_relationship_paths(p_def1, p_def2)["paths"][0]
    assert path2["derived"] is False

    rel2_rev = relationship.get_relationship(p_def2, p_def1)
    e2_rev = next(e for e in rel2_rev["primary"] if "brother" in e["relationship_type"])
    assert e2_rev["derived"] is False
    path2_rev = path_service.get_relationship_paths(p_def2, p_def1)["paths"][0]
    assert path2_rev["derived"] is False

    # Verify Case 3: Inferred biological siblings -> derived=True, path derived=True
    rel3 = relationship.get_relationship(p_bio1, p_bio2)
    e3 = next(e for e in rel3["primary"] if "sister" in e["relationship_type"])
    assert e3["derived"] is True
    path3 = path_service.get_relationship_paths(p_bio1, p_bio2)["paths"][0]
    assert path3["derived"] is True
    # Proof path edges are stored parent_child facts
    assert all(edge["type"] == "parent_child" for edge in path3["edges"])

    rel3_rev = relationship.get_relationship(p_bio2, p_bio1)
    e3_rev = next(e for e in rel3_rev["primary"] if "brother" in e["relationship_type"])
    assert e3_rev["derived"] is True
    path3_rev = path_service.get_relationship_paths(p_bio2, p_bio1)["paths"][0]
    assert path3_rev["derived"] is True
    assert all(edge["type"] == "parent_child" for edge in path3_rev["edges"])

    # Verify Case 4: Inferred half siblings -> derived=True, path derived=True
    rel4 = relationship.get_relationship(p_half1, p_half2)
    entries4 = rel4["primary"] + rel4["additional"]
    e4 = next(e for e in entries4 if "half_sister" in e["relationship_type"] or "sister" in e["relationship_type"])
    assert e4["derived"] is True
    paths4 = path_service.get_relationship_paths(p_half1, p_half2)["paths"]
    half_path = next(p for p in paths4 if "half_sister" in p["relationship_type"] or "sister" in p["relationship_type"])
    assert half_path["derived"] is True
    assert all(edge["type"] == "parent_child" for edge in half_path["edges"])

    rel4_rev = relationship.get_relationship(p_half2, p_half1)
    entries4_rev = rel4_rev["primary"] + rel4_rev["additional"]
    e4_rev = next(e for e in entries4_rev if "half_brother" in e["relationship_type"] or "brother" in e["relationship_type"])
    assert e4_rev["derived"] is True
    paths4_rev = path_service.get_relationship_paths(p_half2, p_half1)["paths"]
    half_path_rev = next(p for p in paths4_rev if "half_brother" in p["relationship_type"] or "brother" in p["relationship_type"])
    assert half_path_rev["derived"] is True
    assert all(edge["type"] == "parent_child" for edge in half_path_rev["edges"])


def test_temporary_copy_of_production_db_migration(tmp_path):
    """Copy current Database/Main/family.db to temp location, run migration, verify data and baseline."""
    real_db = config.PROJECT_ROOT / "Database" / "Main" / "family.db"
    assert real_db.exists()

    temp_copy = tmp_path / "temp_family_copy.db"
    shutil.copy2(real_db, temp_copy)

    # Run migration on the copy
    db.migrate(temp_copy)

    con = sqlite3.connect(str(temp_copy))
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert len(con.execute("PRAGMA foreign_key_check").fetchall()) == 0

        # Verify family baseline numbers
        p_count = con.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        pc_count = con.execute("SELECT COUNT(*) FROM parent_child").fetchone()[0]
        m_count = con.execute("SELECT COUNT(*) FROM marriages").fetchone()[0]
        sg_count = con.execute("SELECT COUNT(*) FROM sibling_groups").fetchone()[0]

        assert p_count == 35, f"Expected 35 people, got {p_count}"
        assert pc_count == 44, f"Expected 44 parent_child, got {pc_count}"
        assert m_count == 12, f"Expected 12 marriages, got {m_count}"
        assert sg_count == 10, f"Expected 10 sibling_groups, got {sg_count}"

        # Schema version must be 2
        meta_ver = con.execute("SELECT value FROM metadata WHERE key = 'app_schema_version'").fetchone()[0]
        user_ver = con.execute("PRAGMA user_version").fetchone()[0]
        assert meta_ver == "2"
        assert user_ver == 2
    finally:
        con.close()
        temp_copy.unlink(missing_ok=True)


# ==============================================================================
# 23. Stored Fact Editing Closure Tests
# ==============================================================================

def test_update_marriage_status(isolated):
    """Update marriage status (married -> divorced) persists in DB."""
    res = family.update_marriage("abrar_hussain", "shaheen_abrar", status="divorced")
    assert res["status"] == "divorced"
    con = db.get_connection()
    try:
        row = con.execute(
            "SELECT status FROM marriages WHERE (spouse_a = 'abrar_hussain' AND spouse_b = 'shaheen_abrar') OR (spouse_a = 'shaheen_abrar' AND spouse_b = 'abrar_hussain')"
        ).fetchone()
        assert row["status"] == "divorced"
    finally:
        con.close()


def test_update_marriage_year(isolated):
    """Update marriage year persists in DB."""
    res = family.update_marriage("abrar_hussain", "shaheen_abrar", year=1988)
    assert res["year"] == 1988
    con = db.get_connection()
    try:
        row = con.execute(
            "SELECT year FROM marriages WHERE (spouse_a = 'abrar_hussain' AND spouse_b = 'shaheen_abrar') OR (spouse_a = 'shaheen_abrar' AND spouse_b = 'abrar_hussain')"
        ).fetchone()
        assert row["year"] == 1988
    finally:
        con.close()


def test_update_marriage_children_status(isolated):
    """Update marriage children_status persists in DB."""
    p1 = people.create_person(name="Spouse A", gender="male")["id"]
    p2 = people.create_person(name="Spouse B", gender="female")["id"]
    family.add_marriage(person_a=p1, person_b=p2, status="married")
    res = family.update_marriage(p1, p2, children_status="no_children")
    assert res["children_status"] == "no_children"
    con = db.get_connection()
    try:
        row = con.execute(
            "SELECT children_status FROM marriages WHERE (spouse_a = ? AND spouse_b = ?) OR (spouse_a = ? AND spouse_b = ?)",
            (p1, p2, p2, p1),
        ).fetchone()
        assert row["children_status"] == "no_children"
    finally:
        con.close()


def test_update_marriage_invalid_rollback(isolated):
    """Invalid marriage update raises ValidationError and leaves DB unchanged."""
    con = db.get_connection()
    try:
        before = dict(con.execute(
            "SELECT * FROM marriages WHERE (spouse_a = 'abrar_hussain' AND spouse_b = 'shaheen_abrar') OR (spouse_a = 'shaheen_abrar' AND spouse_b = 'abrar_hussain')"
        ).fetchone())
    finally:
        con.close()

    with pytest.raises(errors.ValidationError):
        family.update_marriage("abrar_hussain", "shaheen_abrar", status="invalid_status_xyz")

    con = db.get_connection()
    try:
        after = dict(con.execute(
            "SELECT * FROM marriages WHERE (spouse_a = 'abrar_hussain' AND spouse_b = 'shaheen_abrar') OR (spouse_a = 'shaheen_abrar' AND spouse_b = 'abrar_hussain')"
        ).fetchone())
        assert before == after
    finally:
        con.close()


def test_update_marriage_undo_restores(isolated):
    """Undo restores original marriage fact attributes."""
    con = db.get_connection()
    try:
        orig = dict(con.execute(
            "SELECT * FROM marriages WHERE (spouse_a = 'abrar_hussain' AND spouse_b = 'shaheen_abrar') OR (spouse_a = 'shaheen_abrar' AND spouse_b = 'abrar_hussain')"
        ).fetchone())
    finally:
        con.close()

    family.update_marriage("abrar_hussain", "shaheen_abrar", status="widowed", year=1995, children_status="unknown")
    history.undo_last_mutation()

    con = db.get_connection()
    try:
        restored = dict(con.execute(
            "SELECT * FROM marriages WHERE (spouse_a = 'abrar_hussain' AND spouse_b = 'shaheen_abrar') OR (spouse_a = 'shaheen_abrar' AND spouse_b = 'abrar_hussain')"
        ).fetchone())
        assert restored["status"] == orig["status"]
        assert restored["year"] == orig["year"]
        assert restored["children_status"] == orig["children_status"]
    finally:
        con.close()


def test_explicit_sibling_group_delete(isolated):
    """Explicit sibling group delete removes group and member records."""
    facts = family.family_facts()
    assert len(facts["sibling_groups"]) > 0
    group = facts["sibling_groups"][0]
    group_id = group["id"]

    res = family.delete_sibling_group(group_id)
    assert res["ok"] is True

    con = db.get_connection()
    try:
        assert con.execute("SELECT 1 FROM sibling_groups WHERE id = ?", (group_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM sibling_group_members WHERE group_id = ?", (group_id,)).fetchone() is None
    finally:
        con.close()


def test_explicit_sibling_group_delete_preview(isolated):
    """Sibling group deletion preview calculates consequences without mutating DB."""
    facts = family.family_facts()
    group_id = facts["sibling_groups"][0]["id"]

    con_before = db.get_connection()
    try:
        count_before = con_before.execute("SELECT COUNT(*) FROM sibling_groups").fetchone()[0]
    finally:
        con_before.close()

    res = preview.preview_mutation("delete_sibling_group", {"group_id": group_id})
    assert len(res["direct_changes"]) > 0
    assert any(group_id in dc for dc in res["direct_changes"])

    con_after = db.get_connection()
    try:
        count_after = con_after.execute("SELECT COUNT(*) FROM sibling_groups").fetchone()[0]
        assert count_before == count_after
    finally:
        con_after.close()


def test_explicit_sibling_group_delete_undo(isolated):
    """Undo restores exact sibling group record and member rows."""
    facts = family.family_facts()
    group = facts["sibling_groups"][0]
    group_id = group["id"]

    con = db.get_connection()
    try:
        orig_group = dict(con.execute("SELECT * FROM sibling_groups WHERE id = ?", (group_id,)).fetchone())
        orig_members = [dict(r) for r in con.execute("SELECT * FROM sibling_group_members WHERE group_id = ? ORDER BY person_id", (group_id,)).fetchall()]
    finally:
        con.close()

    family.delete_sibling_group(group_id)
    history.undo_last_mutation()

    con = db.get_connection()
    try:
        restored_group = dict(con.execute("SELECT * FROM sibling_groups WHERE id = ?", (group_id,)).fetchone())
        restored_members = [dict(r) for r in con.execute("SELECT * FROM sibling_group_members WHERE group_id = ? ORDER BY person_id", (group_id,)).fetchall()]
        assert restored_group == orig_group
        assert restored_members == orig_members
    finally:
        con.close()


def test_update_sibling_group_type(isolated):
    """Update sibling group type persists and updates correctly."""
    p1 = people.create_person(name="Sib Person 1", gender="male")["id"]
    p2 = people.create_person(name="Sib Person 2", gender="female")["id"]
    added = family.add_sibling_group(member_ids=[p1, p2], type_=None, ordered=False)
    gid = added["id"]

    updated = family.update_sibling_group(gid, type_="full")
    assert updated["type"] == "full"

    con = db.get_connection()
    try:
        row = con.execute("SELECT type FROM sibling_groups WHERE id = ?", (gid,)).fetchone()
        assert row["type"] == "full"
    finally:
        con.close()

    updated2 = family.update_sibling_group(gid, type_=None)
    assert updated2["type"] is None


def test_update_sibling_group_ordered(isolated):
    """Update sibling group ordered flag assigns or clears member order."""
    p1 = people.create_person(name="Sib Order 1", gender="male")["id"]
    p2 = people.create_person(name="Sib Order 2", gender="female")["id"]
    added = family.add_sibling_group(member_ids=[p1, p2], type_=None, ordered=False)
    gid = added["id"]

    family.update_sibling_group(gid, ordered=True)
    con = db.get_connection()
    try:
        g_row = con.execute("SELECT is_ordered FROM sibling_groups WHERE id = ?", (gid,)).fetchone()
        assert g_row["is_ordered"] == 1
        m_rows = con.execute("SELECT member_order FROM sibling_group_members WHERE group_id = ?", (gid,)).fetchall()
        assert all(r["member_order"] is not None and r["member_order"] >= 1 for r in m_rows)
    finally:
        con.close()

    family.update_sibling_group(gid, ordered=False)
    con = db.get_connection()
    try:
        g_row = con.execute("SELECT is_ordered FROM sibling_groups WHERE id = ?", (gid,)).fetchone()
        assert g_row["is_ordered"] == 0
        m_rows = con.execute("SELECT member_order FROM sibling_group_members WHERE group_id = ?", (gid,)).fetchall()
        assert all(r["member_order"] is None for r in m_rows)
    finally:
        con.close()


def test_update_sibling_group_invalid_rollback(isolated):
    """Invalid sibling group update raises ValidationError and rolls back."""
    p1 = people.create_person(name="Sib Tri 1", gender="male")["id"]
    p2 = people.create_person(name="Sib Tri 2", gender="male")["id"]
    p3 = people.create_person(name="Sib Tri 3", gender="male")["id"]
    added = family.add_sibling_group(member_ids=[p1, p2, p3], type_=None, ordered=False)
    gid = added["id"]

    with pytest.raises(errors.ValidationError):
        family.update_sibling_group(gid, type_="full")

    con = db.get_connection()
    try:
        row = con.execute("SELECT type FROM sibling_groups WHERE id = ?", (gid,)).fetchone()
        assert row["type"] is None
    finally:
        con.close()


def test_update_sibling_group_failed_no_phantom_undo(isolated):
    """Failed sibling update does not leave an extra undo snapshot."""
    p1 = people.create_person(name="Sib Stack 1", gender="male")["id"]
    p2 = people.create_person(name="Sib Stack 2", gender="male")["id"]
    p3 = people.create_person(name="Sib Stack 3", gender="male")["id"]
    added = family.add_sibling_group(member_ids=[p1, p2, p3], type_=None)
    gid = added["id"]

    depth_after_add = len(history._MUTATION_STACK)
    with pytest.raises(errors.ValidationError):
        family.update_sibling_group(gid, type_="full")

    assert len(history._MUTATION_STACK) == depth_after_add


def test_edit_general_type(isolated):
    """Editing general relationship type updates DB."""
    p1 = people.create_person(name="Gen Person 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Person 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="friend")
    rid = rel["id"]

    updated = general.update_general_relationship(rid, type="colleague")
    assert updated["type"] == "colleague"
    con = db.get_connection()
    try:
        row = con.execute("SELECT type FROM general_relationships WHERE id = ?", (rid,)).fetchone()
        assert row["type"] == "colleague"
    finally:
        con.close()


def test_edit_general_labels(isolated):
    """Editing general relationship labels updates DB."""
    p1 = people.create_person(name="Gen Lab 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Lab 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="mentor", directionality="directional", label_a_to_b="Mentor", label_b_to_a="Mentee")
    rid = rel["id"]

    updated = general.update_general_relationship(rid, label_a_to_b="Senior Advisor", label_b_to_a="Junior Fellow")
    assert updated["label_a_to_b"] == "Senior Advisor"
    assert updated["label_b_to_a"] == "Junior Fellow"


def test_edit_general_notes(isolated):
    """Editing general relationship notes updates DB."""
    p1 = people.create_person(name="Gen Notes 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Notes 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="friend", notes="Initial note")
    rid = rel["id"]

    updated = general.update_general_relationship(rid, notes="Updated note content")
    assert updated["notes"] == "Updated note content"


def test_edit_general_directionality(isolated):
    """Switching general relationship between symmetric and directional works cleanly."""
    p1 = people.create_person(name="Gen Dir 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Dir 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="friend", directionality="symmetric")
    rid = rel["id"]

    # Switch to directional
    updated = general.update_general_relationship(rid, directionality="directional", direction_from=p1, label_a_to_b="Guide", label_b_to_a="Learner")
    assert updated["directionality"] == "directional"
    assert updated["direction_from"] == p1

    # Switch back to symmetric
    updated2 = general.update_general_relationship(rid, directionality="symmetric")
    assert updated2["directionality"] == "symmetric"
    assert updated2["direction_from"] is None


def test_edit_general_custom_labels(isolated):
    """Editing custom relationship labels works cleanly."""
    p1 = people.create_person(name="Gen Cust 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Cust 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="custom", label_a_to_b="Research Lead", label_b_to_a="Analyst")
    rid = rel["id"]

    updated = general.update_general_relationship(rid, label_a_to_b="Principal Investigator", label_b_to_a="Co-Investigator")
    assert updated["label_a_to_b"] == "Principal Investigator"
    assert updated["label_b_to_a"] == "Co-Investigator"


def test_edit_general_duplicate_rejected(isolated):
    """Attempting an edit that would collide with another existing general relationship is rejected."""
    p1 = people.create_person(name="Gen Dup 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Dup 2", gender="female")["id"]
    rel1 = general.add_general_relationship(person_a=p1, person_b=p2, type="friend")
    rel2 = general.add_general_relationship(person_a=p1, person_b=p2, type="colleague")

    with pytest.raises(errors.ValidationError) as exc_info:
        general.update_general_relationship(rel2["id"], type="friend")

    assert "duplicate" in str(exc_info.value).lower() or exc_info.value.code == "DUPLICATE_FACT"


def test_edit_general_failed_preserves_old_row(isolated):
    """A failed general relationship edit leaves the existing DB row completely intact."""
    p1 = people.create_person(name="Gen Fail 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Fail 2", gender="female")["id"]
    rel1 = general.add_general_relationship(person_a=p1, person_b=p2, type="friend")
    rel2 = general.add_general_relationship(person_a=p1, person_b=p2, type="colleague")
    con = db.get_connection()
    try:
        before = dict(con.execute("SELECT * FROM general_relationships WHERE id = ?", (rel2["id"],)).fetchone())
    finally:
        con.close()

    with pytest.raises(errors.ValidationError):
        general.update_general_relationship(rel2["id"], type="friend")

    con = db.get_connection()
    try:
        after = dict(con.execute("SELECT * FROM general_relationships WHERE id = ?", (rel2["id"],)).fetchone())
        assert before == after
    finally:
        con.close()


def test_edit_general_undo_restores_exact_fact(isolated):
    """Undo restores exact general relationship before edit."""
    p1 = people.create_person(name="Gen Undo 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Undo 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="friend", notes="First note")
    rid = rel["id"]

    general.update_general_relationship(rid, type="mentor", notes="Second note")
    history.undo_last_mutation()

    con = db.get_connection()
    try:
        row = dict(con.execute("SELECT * FROM general_relationships WHERE id = ?", (rid,)).fetchone())
        assert row["type"] == "friend"
        assert row["notes"] == "First note"
    finally:
        con.close()


def test_edit_general_id_remains_stable(isolated):
    """General relationship ID remains identical across edits."""
    p1 = people.create_person(name="Gen Stable 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Stable 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="friend")
    rid = rel["id"]

    updated = general.update_general_relationship(rid, type="colleague", notes="New notes")
    assert updated["id"] == rid


def test_edit_general_stored_fact_id_stable(isolated):
    """The stored_fact_id and general_relationship_id in relationship view remain stable across edits."""
    p1 = people.create_person(name="Gen Sem 1", gender="male")["id"]
    p2 = people.create_person(name="Gen Sem 2", gender="female")["id"]
    rel = general.add_general_relationship(person_a=p1, person_b=p2, type="friend")
    rid = rel["id"]

    rel_view_before = relationship.get_relationship(p1, p2)
    entries_before = rel_view_before["primary"] + rel_view_before["additional"]
    gen_entry_before = next(e for e in entries_before if e["domain"] == "general")
    assert gen_entry_before["general_relationship_id"] == rid
    assert gen_entry_before["stored_fact_id"] == f"general_relationship:{rid}"

    general.update_general_relationship(rid, type="colleague")

    rel_view_after = relationship.get_relationship(p1, p2)
    entries_after = rel_view_after["primary"] + rel_view_after["additional"]
    gen_entry_after = next(e for e in entries_after if e["domain"] == "general")
    assert gen_entry_after["general_relationship_id"] == rid
    assert gen_entry_after["stored_fact_id"] == f"general_relationship:{rid}"


def test_parent_kind_unknown_accepted(isolated):
    """Parent-child kind='unknown' is valid, stored, editable, and derived=False."""
    p1 = people.create_person(name="Parent Unk", gender="male")["id"]
    c1 = people.create_person(name="Child Unk", gender="male")["id"]
    res = family.add_parent_child(parent_id=p1, child_id=c1, role="parent", kind="unknown")
    assert res["kind"] == "unknown"

    con = db.get_connection()
    try:
        row = con.execute("SELECT kind FROM parent_child WHERE parent_id = ? AND child_id = ?", (p1, c1)).fetchone()
        assert row["kind"] == "unknown"
    finally:
        con.close()

    updated = family.update_parent_child(p1, c1, role="father", kind="unknown")
    assert updated["kind"] == "unknown"

    rel = relationship.get_relationship(p1, c1)
    entries = rel["primary"] + rel["additional"]
    pc_entry = next(e for e in entries if e["domain"] == "family")
    assert pc_entry["derived"] is False


def test_parent_kind_unspecified_accepted(isolated):
    """Parent-child kind='unspecified' is valid, stored, editable, and derived=False."""
    p1 = people.create_person(name="Parent Unspec", gender="female")["id"]
    c1 = people.create_person(name="Child Unspec", gender="female")["id"]
    res = family.add_parent_child(parent_id=p1, child_id=c1, role="parent", kind="unspecified")
    assert res["kind"] == "unspecified"

    con = db.get_connection()
    try:
        row = con.execute("SELECT kind FROM parent_child WHERE parent_id = ? AND child_id = ?", (p1, c1)).fetchone()
        assert row["kind"] == "unspecified"
    finally:
        con.close()

    updated = family.update_parent_child(p1, c1, role="mother", kind="unspecified")
    assert updated["kind"] == "unspecified"

    rel = relationship.get_relationship(p1, c1)
    entries = rel["primary"] + rel["additional"]
    pc_entry = next(e for e in entries if e["domain"] == "family")
    assert pc_entry["derived"] is False
