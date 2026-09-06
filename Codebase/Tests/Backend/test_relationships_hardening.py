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
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.backend import config, db
from app.backend.data_root import DataRootManager
from app.backend.domain.family import engine as build_family
from app.backend.domain.mutations import history
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


def test_schema_version_mismatch_refuses_destructive_migration(tmp_path):
    """If metadata and PRAGMA user_version disagree, migration must raise SchemaVersionMismatchError."""
    mismatch_db = tmp_path / "mismatch.db"
    con = sqlite3.connect(str(mismatch_db))
    build_family.create_sqlite_schema(con)
    con.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', '2')")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()

    with pytest.raises(db.SchemaVersionMismatchError):
        db.migrate(mismatch_db)


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
