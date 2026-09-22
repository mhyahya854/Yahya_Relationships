"""Comprehensive test suite for Phase 11: Canonical Data Foundation & Migration.

Validates:
1. Canonical ID generation, initials computation, zero-padding, collision avoidance.
2. Unresolved person ID generation, allocation, resolution, and alias recording.
3. Canonical person folder template (5 subdirectories, facts file, journal file).
4. Facts and about generation and deterministic Markdown parsing.
5. Migration engine dry-run and atomic execution on isolated copies.
6. Schema v3 invariants, identifier alias resolution, and backward compatibility.
7. Kinship perspective audit compatibility with canonical store.
8. Backup verification and restore compatibility with relationships.db.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.backend import config, db
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.canonical.ids import (
    compute_initials,
    generate_canonical_person_id,
    generate_unresolved_person_id,
    is_valid_canonical_person_id,
    is_valid_unresolved_person_id,
    normalize_name,
)
from app.backend.domain.canonical.template import (
    FOLDER_TEMPLATE_DIRECTORIES,
    canonical_facts_filename,
    canonical_journal_filename,
    generate_facts_and_about,
    initialize_person_folder,
    parse_facts_and_about,
)
from app.backend.domain.migration.engine import CanonicalMigrationEngine
from app.backend.services import people as people_service


# ==============================================================================
# 1. Canonical ID & Unresolved ID Generation Tests
# ==============================================================================

def test_canonical_id_normalization_and_initials():
    assert normalize_name("Sara Khan") == "sara_khan"
    assert normalize_name("Mohammad Yahya Hussain") == "mohammad_yahya_hussain"
    assert normalize_name("O'Connor-Smith") == "o_connor_smith"
    assert normalize_name("  Syed   Ali  ") == "syed_ali"

    assert compute_initials("Sara Khan") == "SK"
    assert compute_initials("Mohammad Yahya Hussain") == "MYH"
    assert compute_initials("Plato") == "P"
    with pytest.raises(ValueError):
        compute_initials("")


def test_canonical_person_id_generation_basic():
    cid = generate_canonical_person_id("Sara Khan", set())
    assert cid == "sara_khan--SK01"
    assert is_valid_canonical_person_id(cid) is True

    cid_long = generate_canonical_person_id("Mohammad Yahya Hussain", set())
    assert cid_long == "mohammad_yahya_hussain--MYH01"
    assert is_valid_canonical_person_id(cid_long) is True


def test_canonical_person_id_collision_handling():
    existing = {"sara_khan--SK01", "sara_khan--SK02"}
    cid3 = generate_canonical_person_id("Sara Khan", existing)
    assert cid3 == "sara_khan--SK03"

    # Up to 2 digits zero padded
    existing_many = {f"sara_khan--SK{i:02d}" for i in range(1, 10)}
    cid10 = generate_canonical_person_id("Sara Khan", existing_many)
    assert cid10 == "sara_khan--SK10"


def test_canonical_person_id_validation_predicate():
    assert is_valid_canonical_person_id("sara_khan--SK01") is True
    assert is_valid_canonical_person_id("mohammad_yahya_hussain--MYH99") is True
    assert is_valid_canonical_person_id("unknown_person--UP0001") is False
    assert is_valid_canonical_person_id("sara-khan") is False
    assert is_valid_canonical_person_id("sara_khan") is False
    assert is_valid_canonical_person_id("sara_khan--sk01") is False  # initials must be upper


def test_unresolved_person_id_generation():
    up1 = generate_unresolved_person_id(set())
    assert up1 == "unknown_person--UP0001"
    assert is_valid_unresolved_person_id(up1) is True

    up2 = generate_unresolved_person_id({"unknown_person--UP0001"})
    assert up2 == "unknown_person--UP0002"
    assert is_valid_unresolved_person_id(up2) is True

    assert is_valid_unresolved_person_id("unknown_person--UP9999") is True
    assert is_valid_unresolved_person_id("unknown_person--UP01") is False  # must be 4 digits
    assert is_valid_unresolved_person_id("sara_khan--SK01") is False


# ==============================================================================
# 2. Canonical Folder Template & Facts-and-About Parsing Tests
# ==============================================================================

def test_canonical_filenames():
    assert canonical_facts_filename("sara_khan--SK01") == "sara_khan--SK01(facts and about).md"
    assert canonical_journal_filename() == "journal(personal thoughts).md"


def test_initialize_person_folder_structure(tmp_path):
    person_dir = tmp_path / "sara_khan--SK01"
    initialize_person_folder(
        person_dir,
        "sara_khan--SK01",
        "Sara Khan",
        primary_category="Family",
        aliases=["SK", "Saroo"],
        birth_year=1995,
        gender="female",
    )

    # 5 standard directories exist
    for sub in FOLDER_TEMPLATE_DIRECTORIES:
        assert (person_dir / sub).is_dir()

    # Facts and about file exists
    facts_file = person_dir / "sara_khan--SK01(facts and about).md"
    assert facts_file.is_file()

    # Journal file exists
    journal_file = person_dir / "journal(personal thoughts).md"
    assert journal_file.is_file()

    # Parse facts file
    content = facts_file.read_text(encoding="utf-8")
    data = parse_facts_and_about(content)
    assert data["Canonical ID"] == "sara_khan--SK01"
    assert data["Full Name"] == "Sara Khan"
    assert data["Primary Category"] == "Family"
    assert "SK" in data["Aliases / Nicknames"]
    assert data["Date of Birth"] == "1995"
    assert data["Gender"] == "female"
    assert data["Contact Status"] == "Unknown"


def test_facts_and_about_explicit_unknowns():
    content = generate_facts_and_about(
        "john_doe--JD01",
        "John Doe",
        primary_category="Friends",
    )
    data = parse_facts_and_about(content)
    assert data["Canonical ID"] == "john_doe--JD01"
    assert data["Date of Birth"] == "Unknown"
    assert data["Where We Met"] == "Unknown"
    assert data["When We Met"] == "Unknown"
    assert data["Current / Old Phone Numbers"] == "Unknown"
    assert data["Current / Old Email Addresses"] == "Unknown"


# ==============================================================================
# 3. Unresolved Person Lifecycle & Resolution Tests
# ==============================================================================

@pytest.fixture
def canonical_test_env(tmp_path, monkeypatch):
    """Sets up a clean canonical test environment with Schema 3 relationships.db."""
    root = tmp_path / "CanonicalDataRoot"
    root.mkdir()
    db_dir = root / "Database"
    db_dir.mkdir()
    people_dir = root / "People"
    people_dir.mkdir()
    (people_dir / "Me").mkdir()
    (people_dir / "Family").mkdir()
    (people_dir / "Friends").mkdir()

    rel_db = db_dir / "relationships.db"
    conn = sqlite3.connect(str(rel_db))
    conn.row_factory = sqlite3.Row
    db._bootstrap_new_database(conn, target_schema=3)
    db._migrate_v2_to_v3_atomic(conn)
    conn.close()

    monkeypatch.setattr(DataRootManager, "resolve_active_root", lambda: root)
    return root, rel_db


def test_unresolved_person_lifecycle(canonical_test_env):
    root, rel_db = canonical_test_env

    # 1. Allocate an unresolved person
    res1 = people_service.allocate_unresolved_person(
        provisional_label="Mysterious Wedding Guest",
        source_context="1998 wedding album photo #4",
        create_folder=True,
    )
    assert res1["id"] == "unknown_person--UP0001"
    assert res1["label"] == "Mysterious Wedding Guest"
    assert res1["resolved_to_person_id"] is None

    # Folder exists directly under People/
    up_folder = root / "People" / "unknown_person--UP0001"
    assert up_folder.is_dir()
    assert (up_folder / "unknown_person--UP0001(facts and about).md").is_file()
    assert (up_folder / "journal(personal thoughts).md").is_file()
    for sub in FOLDER_TEMPLATE_DIRECTORIES:
        assert (up_folder / sub).is_dir()

    # 2. List unresolved people
    unresolved_list = people_service.list_unresolved_people()
    assert len(unresolved_list) == 1
    assert unresolved_list[0]["id"] == "unknown_person--UP0001"

    # 3. Create a canonical target person
    target = people_service.create_person(
        name="Uncle Rashid",
        birth_year=1960,
        gender="male",
        category="Family",
    )
    assert target["id"] == "uncle_rashid--UR01"

    # 4. Resolve the unresolved person
    resolution = people_service.resolve_unresolved_person(
        "unknown_person--UP0001",
        target["id"],
        resolution_notes="Identified Rashid in 1998 wedding album",
    )
    assert resolution["unresolved_id"] == "unknown_person--UP0001"
    assert resolution["resolved_to_person_id"] == "uncle_rashid--UR01"

    # Verify unresolved is now excluded from active list
    assert len(people_service.list_unresolved_people(include_resolved=False)) == 0
    resolved_all = people_service.list_unresolved_people(include_resolved=True)
    assert len(resolved_all) == 1
    assert resolved_all[0]["resolved_to_person_id"] == "uncle_rashid--UR01"

    # Verify alias resolution
    conn = sqlite3.connect(str(rel_db))
    conn.row_factory = sqlite3.Row
    resolved_alias = db.resolve_canonical_id(conn, "unknown_person--UP0001")
    assert resolved_alias == "uncle_rashid--UR01"
    conn.close()


# ==============================================================================
# 4. Migration Engine Tests (Isolated Copy)
# ==============================================================================

def test_migration_engine_plan_and_dry_run(tmp_path):
    # Test on isolated unmigrated copy with dry_run=True (safe, read-only)
    proj_root = Path(__file__).resolve().parents[3]
    isolated_root = tmp_path / "UnmigratedDataRoot"
    (isolated_root / "Database" / "Main").mkdir(parents=True, exist_ok=True)
    shutil.copy2(proj_root / "Database" / "Main" / "family.db", isolated_root / "Database" / "Main" / "family.db")
    if (proj_root / "Database" / "People").exists():
        shutil.copytree(proj_root / "Database" / "People", isolated_root / "Database" / "People")
    else:
        (isolated_root / "Database" / "People").mkdir(parents=True, exist_ok=True)

    engine = CanonicalMigrationEngine(isolated_root, dry_run=True)
    plan = engine.plan()

    assert plan["can_migrate"] is True
    assert len(plan["mappings"]) == 35

    # Check key mappings from Master Plan
    id_map = {m["old_id"]: m["canonical_id"] for m in plan["mappings"]}
    assert id_map["mohammad_yahya_hussain"] == "mohammad_yahya_hussain--MYH01"
    assert id_map["maham_mansoor"] == "maham_mansoor--MM01"
    assert id_map["mansoor_hussain"] == "mansoor_hussain--MH01"

    # Dry run should not modify anything
    assert not (isolated_root / "Database" / "relationships.db").exists()


def test_migration_engine_execution_on_isolated_copy(tmp_path):
    # Create an isolated copy of the real unmigrated data root
    proj_root = Path(__file__).resolve().parents[3]
    isolated_root = tmp_path / "IsolatedDataRoot"
    (isolated_root / "Database" / "Main").mkdir(parents=True, exist_ok=True)
    shutil.copy2(proj_root / "Database" / "Main" / "family.db", isolated_root / "Database" / "Main" / "family.db")
    if (proj_root / "Database" / "People").exists():
        shutil.copytree(proj_root / "Database" / "People", isolated_root / "Database" / "People")
    else:
        (isolated_root / "Database" / "People").mkdir(parents=True, exist_ok=True)

    # Run migration on the isolated copy
    engine = CanonicalMigrationEngine(isolated_root, dry_run=False)
    results = engine.migrate()

    assert results["ok"] is True
    assert results["migrated_people_count"] == 35
    assert len(results["mappings"]) == 35

    # Authoritative canonical database exists
    canon_db_path = isolated_root / "Database" / "relationships.db"
    assert canon_db_path.is_file()

    # Original family.db preserved untouched
    assert (isolated_root / "Database" / "Main" / "family.db").is_file()

    # Verify schema version 3
    conn = sqlite3.connect(str(canon_db_path))
    conn.row_factory = sqlite3.Row
    user_ver = conn.execute("PRAGMA user_version").fetchone()[0]
    assert user_ver == 3
    s_row = conn.execute("SELECT value FROM metadata WHERE key = 'app_schema_version'").fetchone()
    assert s_row["value"] == "3"

    # Verify table counts match source
    src_conn = sqlite3.connect(str(isolated_root / "Database" / "Main" / "family.db"))
    for tbl in ("people", "parent_child", "marriages", "sibling_groups", "sibling_group_members", "general_relationships", "sources"):
        src_cnt = src_conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        dst_cnt = conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        assert src_cnt == dst_cnt, f"Mismatch in table {tbl}: {src_cnt} != {dst_cnt}"
    src_conn.close()

    # Verify all 35 aliases registered
    alias_count = conn.execute("SELECT count(*) FROM identifier_aliases").fetchone()[0]
    assert alias_count == 35

    # Verify alias lookup works
    assert db.resolve_canonical_id(conn, "maham_mansoor") == "maham_mansoor--MM01"
    assert db.resolve_canonical_id(conn, "mohammad_yahya_hussain") == "mohammad_yahya_hussain--MYH01"
    conn.close()

    # Verify People folder hierarchy
    people_root = isolated_root / "People"
    assert people_root.is_dir()
    assert (people_root / "Me").is_dir()
    assert (people_root / "Family").is_dir()
    assert (people_root / "Friends").is_dir()

    # Verify Mohammad Yahya Hussain is under Me/
    myh_folder = people_root / "Me" / "mohammad_yahya_hussain--MYH01"
    assert myh_folder.is_dir()
    assert (myh_folder / "mohammad_yahya_hussain--MYH01(facts and about).md").is_file()
    assert (myh_folder / "journal(personal thoughts).md").is_file()
    for sub in FOLDER_TEMPLATE_DIRECTORIES:
        assert (myh_folder / sub).is_dir()

    # Verify journal content was copied accurately
    myh_journal = (myh_folder / "journal(personal thoughts).md").read_text(encoding="utf-8")
    assert len(myh_journal) > 0

    # Verify Maham Mansoor is under Family/
    mm_folder = people_root / "Family" / "maham_mansoor--MM01"
    assert mm_folder.is_dir()
    assert (mm_folder / "maham_mansoor--MM01(facts and about).md").is_file()
    assert (mm_folder / "journal(personal thoughts).md").is_file()


# ==============================================================================
# 5. Kinship Regression Compatibility with Canonical Store
# ==============================================================================

def test_kinship_audit_on_migrated_store(tmp_path):
    proj_root = Path(__file__).resolve().parents[3]
    isolated_root = tmp_path / "KinshipDataRoot"
    (isolated_root / "Database" / "Main").mkdir(parents=True, exist_ok=True)
    shutil.copy2(proj_root / "Database" / "Main" / "family.db", isolated_root / "Database" / "Main" / "family.db")
    if (proj_root / "Database" / "People").exists():
        shutil.copytree(proj_root / "Database" / "People", isolated_root / "Database" / "People")
    else:
        (isolated_root / "Database" / "People").mkdir(parents=True, exist_ok=True)

    engine = CanonicalMigrationEngine(isolated_root, dry_run=False)
    engine.migrate()

    canon_db = isolated_root / "Database" / "relationships.db"
    from app.backend.domain.family.engine import read_sqlite_model, _kinship_regression_audit

    model = read_sqlite_model(canon_db)
    # The regression audit should pass cleanly without throwing any KinshipPerspectiveAuditError
    _kinship_regression_audit(model)


# ==============================================================================
# 6. Backup Verification Compatibility with Schema v3
# ==============================================================================

def test_backup_verification_with_schema_3(canonical_test_env):
    root, rel_db = canonical_test_env
    from app.backend.domain.backups.create import create_backup
    from app.backend.domain.backups.verify import verify_backup

    backup_info = create_backup("Canonical Schema 3 Snapshot", root=root)
    backup_path = Path(backup_info["path"])

    result = verify_backup(backup_path)
    assert result["ok"] is True
    assert result["manifest"]["sqlite_schema_version"] == 3
    assert result["db_integrity"] == "ok"
