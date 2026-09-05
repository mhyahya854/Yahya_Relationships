"""Surgical tests for canonical journal safety and failure-atomicity.

Covers:
1. Existing person + existing journal: list/get/profile returns person, filesystem unchanged.
2. Existing person + missing journal: read paths do NOT recreate journal, surfaces missing state cleanly.
3. Existing person + missing folder: read paths do NOT recreate folder, surfaces missing state cleanly.
4. Explicit ensure_journal(): creates folder and journal when called from explicit write/repair path.
5. create_person normal success: person exists, exactly one folder, exactly one journal.md.
6. create_person filesystem failure: rolls back SQLite, removes any created folder/journal, pops snapshot, raises StorageError.
7. person edit: existing journal remains exactly attached, no duplicates.
8. cross-platform: spaces in root, Unicode root, case-sensitive group directories, read-only root protection.
"""

from pathlib import Path
import shutil
from unittest.mock import patch
import pytest

from app.backend import config, db
from app.backend.data_root.errors import DataRootReadOnlyError
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.mutations import history as mutation_history
from app.backend.services import errors, journals, people


def test_existing_person_and_journal_reads_do_not_mutate(isolated):
    """Reading an existing person leaves the filesystem untouched."""
    p_id = "mohammad_yahya_hussain"
    conn = db.get_connection()
    try:
        folder = db.find_person_folder(conn, p_id)
    finally:
        conn.close()
    assert folder is not None and folder.exists()
    journal = folder / "journal.md"
    assert journal.exists()

    mtime_before = journal.stat().st_mtime_ns
    hash_before = journal.read_bytes()

    # 1. list_people
    plist = people.list_people()
    assert any(p["id"] == p_id for p in plist)

    # 2. get_person
    p = people.get_person(p_id)
    assert p["folder_exists"] is True
    assert p["journal_exists"] is True

    # 3. get_person_profile
    profile = people.get_person_profile(p_id)
    assert profile["journal"]["exists"] is True

    # 4. read_journal
    j_res = journals.read_journal(p_id)
    assert j_res["exists"] is True

    # Filesystem must be strictly identical
    assert journal.stat().st_mtime_ns == mtime_before
    assert journal.read_bytes() == hash_before


def test_missing_journal_not_recreated_by_reads(isolated):
    """If journal.md is missing, read paths must NEVER recreate it."""
    p_id = "mohammad_yahya_hussain"
    conn = db.get_connection()
    try:
        folder = db.find_person_folder(conn, p_id)
    finally:
        conn.close()
    assert folder is not None
    journal = folder / "journal.md"
    assert journal.exists()

    # Simulate missing journal
    journal.unlink()
    assert not journal.exists()

    # 1. list_people must not recreate journal
    plist = people.list_people()
    target = next(p for p in plist if p["id"] == p_id)
    assert not journal.exists(), "list_people recreated missing journal!"
    assert target["folder_exists"] is True
    assert target["journal_exists"] is False

    # 2. get_person must not recreate journal
    p = people.get_person(p_id)
    assert not journal.exists(), "get_person recreated missing journal!"
    assert p["folder_exists"] is True
    assert p["journal_exists"] is False

    # 3. check_duplicate_person must not recreate journal
    _ = people.check_duplicate_person("Mohammad Yahya Hussain")
    assert not journal.exists(), "check_duplicate_person recreated missing journal!"

    # 4. get_person_profile must not recreate journal
    profile = people.get_person_profile(p_id)
    assert not journal.exists(), "get_person_profile recreated missing journal!"
    assert profile["person"]["journal_exists"] is False
    assert profile["journal"]["exists"] is False
    assert profile["journal"]["content"] == ""

    # 5. read_journal must not recreate journal
    j_data = journals.read_journal(p_id)
    assert not journal.exists(), "read_journal recreated missing journal!"
    assert j_data["exists"] is False
    assert j_data["content"] == ""


def test_missing_person_folder_not_recreated_by_reads(isolated):
    """If person folder is missing, read paths must NEVER recreate folder or journal."""
    p_id = "mohammad_yahya_hussain"
    conn = db.get_connection()
    try:
        folder = db.find_person_folder(conn, p_id)
    finally:
        conn.close()
    assert folder is not None
    shutil.rmtree(folder)
    assert not folder.exists()

    # 1. list_people
    plist = people.list_people()
    target = next(p for p in plist if p["id"] == p_id)
    assert not folder.exists(), "list_people recreated missing folder!"
    assert target["folder"] is None
    assert target["folder_exists"] is False
    assert target["journal_exists"] is False

    # 2. get_person
    p = people.get_person(p_id)
    assert not folder.exists(), "get_person recreated missing folder!"
    assert p["folder"] is None
    assert p["folder_exists"] is False
    assert p["journal_exists"] is False

    # 3. profile
    profile = people.get_person_profile(p_id)
    assert not folder.exists(), "profile recreated missing folder!"
    assert profile["person"]["folder_exists"] is False
    assert profile["journal"]["exists"] is False


def test_explicit_ensure_journal_creates_folder_and_file(isolated):
    """Explicit mutating ensure_journal recreates folder and journal when called deliberately."""
    p_id = "mohammad_yahya_hussain"
    conn = db.get_connection()
    try:
        folder = db.find_person_folder(conn, p_id)
        assert folder is not None
        shutil.rmtree(folder)
        assert not folder.exists()

        created_path = db.ensure_journal(conn, p_id)
        assert created_path.is_file()
        assert folder.is_dir()
        assert "# Mohammad Yahya Hussain" in created_path.read_text(encoding="utf-8")
    finally:
        conn.close()


def test_create_person_normal_success_creates_exactly_one_folder_and_journal(isolated):
    """create_person creates exactly one canonical folder and journal.md."""
    created = people.create_person(
        name="Zainab Tariq",
        birth_year=2005,
        gender="female",
        group_ids=["family"],
    )
    p_id = created["id"]
    conn = db.get_connection()
    try:
        folder = db.find_person_folder(conn, p_id)
        assert folder is not None and folder.is_dir()
        journal = folder / "journal.md"
        assert journal.is_file()
        assert "# Zainab Tariq" in journal.read_text(encoding="utf-8")

        # Verify exactly one folder under people_dir
        matches = [p for p in config.PEOPLE_DIR.rglob(p_id) if p.is_dir()]
        assert len(matches) == 1
    finally:
        conn.close()


def test_create_person_filesystem_failure_rolls_back_atomically(isolated):
    """If journal creation fails, DB transaction is rolled back, no orphan folder/file remains,
    no snapshot is left on undo stack, and StorageError is raised."""
    mutation_history._MUTATION_STACK.clear()
    undo_depth_before = len(mutation_history._MUTATION_STACK)

    with patch("app.backend.db.ensure_journal", side_effect=OSError("Disk write I/O error")):
        with pytest.raises(errors.StorageError) as exc_info:
            people.create_person(
                name="Atomic Fail Test",
                aliases=["Fail Alias"],
                birth_year=1990,
                gender="male",
                group_ids=["family"],
            )

    assert "Failed to create canonical journal" in str(exc_info.value)

    # 1. Person row must NOT exist in DB
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT * FROM people WHERE name = 'Atomic Fail Test'").fetchone()
        assert row is None, "Failed person remained in people table!"

        # 2. Aliases must NOT remain
        alias_rows = conn.execute("SELECT * FROM aliases WHERE alias = 'Fail Alias'").fetchall()
        assert len(alias_rows) == 0, "Failed aliases remained!"

        # 3. No person_groups remain
        pg_rows = conn.execute(
            "SELECT * FROM person_groups WHERE person_id LIKE 'atomic_fail_test%'"
        ).fetchall()
        assert len(pg_rows) == 0, "Failed person_groups remained!"

        # 4. Fact sources must NOT remain
        fs_rows = conn.execute(
            "SELECT * FROM fact_sources WHERE entity_key LIKE 'atomic_fail_test%'"
        ).fetchall()
        assert len(fs_rows) == 0, "Failed fact_sources remained!"

        # 5. No orphan folder on disk
        folder = db.find_person_folder(conn, "atomic_fail_test")
        assert folder is None or not folder.exists()
    finally:
        conn.close()

    # 6. Mutation history stack must NOT contain the failed snapshot
    assert len(mutation_history._MUTATION_STACK) == undo_depth_before
    assert not any(s.get("description") == "Created person: Atomic Fail Test" for s in mutation_history._MUTATION_STACK)


def test_person_edit_preserves_journal_without_duplication(isolated):
    """Editing person metadata preserves canonical journal without duplication."""
    p_id = "mohammad_yahya_hussain"
    conn = db.get_connection()
    try:
        folder = db.find_person_folder(conn, p_id)
        assert folder is not None
        journal = folder / "journal.md"
        assert journal.is_file()
        journal.write_text("# Mohammad Yahya Hussain\n\nCustom notes.\n", encoding="utf-8")
    finally:
        conn.close()

    updated = people.update_person(
        p_id,
        note_en="Updated note",
        aliases=["Yahya", "MYH"],
    )
    assert updated["id"] == p_id
    assert updated["note_en"] == "Updated note"

    # Journal must still exist and contain custom notes
    assert journal.is_file()
    assert "Custom notes." in journal.read_text(encoding="utf-8")

    # Only one folder exists across whole people directory
    matches = [p for p in config.PEOPLE_DIR.rglob(p_id) if p.is_dir()]
    assert len(matches) == 1


def test_create_person_refuses_when_data_root_is_read_only(isolated):
    """create_person refuses mutation when DataRoot is marked read-only."""
    with patch.object(DataRootManager, "is_read_only", return_value=True):
        with pytest.raises(DataRootReadOnlyError):
            people.create_person(name="ReadOnly Test")



def test_cross_platform_spaces_and_unicode(tmp_path):
    """Test with path containing spaces and Unicode characters."""
    root = tmp_path / "Family Data Ünïcöde & Spaces"
    root.mkdir(parents=True, exist_ok=True)

    db_dir = root / "Database" / "Main"
    db_dir.mkdir(parents=True, exist_ok=True)
    prod_db = Path(__file__).resolve().parents[3] / "Database" / "Main" / "family.db"
    shutil.copy2(prod_db, db_dir / "family.db")

    people_dir = root / "Database" / "People" / "Family"
    people_dir.mkdir(parents=True, exist_ok=True)

    DataRootManager.set_override_root(root)
    try:
        db.migrate(db_dir / "family.db")
        p = people.create_person(
            name="Farhan Khan",
            group_ids=["family"],
        )
        assert p["id"] == "farhan_khan"
        conn = db.get_connection()
        try:
            folder = db.find_person_folder(conn, "farhan_khan")
            assert folder is not None and folder.exists()
            assert (folder / "journal.md").is_file()
        finally:
            conn.close()
    finally:
        DataRootManager.set_override_root(None)


def test_create_person_mkdir_succeeds_journal_write_fails(isolated):
    """TEST 1: mkdir succeeds, journal write fails.
    Verifies that the newly created person directory is cleanly removed,
    leaving no orphan folder, and SQLite transaction is rolled back."""
    target_id = "mkdir_succeeds_fail"
    orig_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if self.name == "journal.md" and target_id in str(self):
            # Target directory exists at this point because mkdir succeeded
            assert self.parent.exists(), "Expected parent folder to exist before writing journal"
            raise OSError("Simulated disk I/O failure during journal write")
        return orig_write_text(self, *args, **kwargs)

    undo_depth_before = len(mutation_history._MUTATION_STACK)

    with patch.object(Path, "write_text", new=failing_write_text):
        with pytest.raises(errors.StorageError) as exc_info:
            people.create_person(
                name="Mkdir Succeeds Fail",
                aliases=["Alias 1"],
                gender="female",
                group_ids=["family"],
            )

    assert "Failed to create canonical journal" in str(exc_info.value)

    # Verify DB rollback
    conn = db.get_connection()
    try:
        assert conn.execute("SELECT * FROM people WHERE id = ?", (target_id,)).fetchone() is None
        assert len(conn.execute("SELECT * FROM aliases WHERE person_id = ?", (target_id,)).fetchall()) == 0
        assert len(conn.execute("SELECT * FROM person_groups WHERE person_id = ?", (target_id,)).fetchall()) == 0
        assert len(conn.execute("SELECT * FROM fact_sources WHERE entity_key = ?", (target_id,)).fetchall()) == 0

        # Verify filesystem compensation: folder must NOT remain on disk
        folder = db.find_person_folder(conn, target_id)
        assert folder is None or not folder.exists()
        expected = db.expected_person_folder(conn, target_id)
        assert not expected.exists(), "Newly created folder was left on disk after write failure!"
    finally:
        conn.close()

    # Verify Undo stack depth restored
    assert len(mutation_history._MUTATION_STACK) == undo_depth_before
    assert not any(s.get("description") == "Created person: Mkdir Succeeds Fail" for s in mutation_history._MUTATION_STACK)


def test_create_person_partial_journal_file_cleaned_up_on_failure(isolated):
    """TEST 2: Partial journal file exists when write fails.
    Verifies that a partially-written file and newly created folder are both removed."""
    target_id = "partial_write_fail"
    orig_write_text = Path.write_text

    def partial_write_then_fail(self, *args, **kwargs):
        if self.name == "journal.md" and target_id in str(self):
            # Write partial corrupted data to disk
            self.write_bytes(b"# Partial corrupted data")
            assert self.exists() and self.stat().st_size > 0
            raise OSError("Simulated partial write crash mid-operation")
        return orig_write_text(self, *args, **kwargs)

    undo_depth_before = len(mutation_history._MUTATION_STACK)

    with patch.object(Path, "write_text", new=partial_write_then_fail):
        with pytest.raises(errors.StorageError):
            people.create_person(
                name="Partial Write Fail",
                group_ids=["family"],
            )

    conn = db.get_connection()
    try:
        expected = db.expected_person_folder(conn, target_id)
        # Both partial journal and folder must be gone
        assert not (expected / "journal.md").exists(), "Partial journal was left on disk!"
        assert not expected.exists(), "Folder was left on disk after partial journal failure!"
        assert conn.execute("SELECT * FROM people WHERE id = ?", (target_id,)).fetchone() is None
    finally:
        conn.close()

    assert len(mutation_history._MUTATION_STACK) == undo_depth_before


def test_create_person_pre_existing_folder_must_survive(isolated):
    """TEST 3: Pre-existing folder must survive.
    If the person folder existed prior to the attempted creation, compensation must NOT delete it."""
    target_id = "pre_existing_folder_person"
    conn = db.get_connection()
    expected_folder = db.expected_person_folder(conn, target_id, group_id="family")
    conn.close()

    expected_folder.mkdir(parents=True, exist_ok=True)
    marker_file = expected_folder / "existing_note.txt"
    marker_file.write_text("pre-existing data", encoding="utf-8")

    orig_write_text = Path.write_text

    def fail_write(self, *args, **kwargs):
        if self.name == "journal.md" and target_id in str(self):
            raise OSError("Simulated write failure")
        return orig_write_text(self, *args, **kwargs)

    with patch.object(Path, "write_text", new=fail_write):
        with pytest.raises(errors.StorageError):
            people.create_person(
                name="Pre Existing Folder Person",
                group_ids=["family"],
            )

    # Pre-existing folder MUST STILL EXIST!
    assert expected_folder.exists(), "Pre-existing folder was deleted by compensation!"
    assert marker_file.exists()
    assert marker_file.read_text(encoding="utf-8") == "pre-existing data"
    # Target journal must not exist
    assert not (expected_folder / "journal.md").exists()


def test_create_person_pre_existing_journal_must_never_be_deleted(isolated):
    """TEST 4: Pre-existing journal must never be deleted.
    If a journal file already existed at the target path before the attempt, compensation must preserve it."""
    target_id = "pre_existing_journal_person"
    conn = db.get_connection()
    expected_folder = db.expected_person_folder(conn, target_id, group_id="family")
    conn.close()

    expected_folder.mkdir(parents=True, exist_ok=True)
    existing_journal = expected_folder / "journal.md"
    existing_journal.write_text("# Existing Canonical Prose\n\nPreserve this.\n", encoding="utf-8")

    # Simulate failure after filesystem check (e.g. failure during link_fact_source)
    with patch("app.backend.services.people.db.link_fact_source", side_effect=RuntimeError("Simulated DB error")):
        with pytest.raises(RuntimeError):
            people.create_person(
                name="Pre Existing Journal Person",
                group_ids=["family"],
            )

    # Pre-existing journal and folder MUST REMAIN UNTOUCHED!
    assert existing_journal.exists(), "Pre-existing journal was deleted!"
    assert "Preserve this." in existing_journal.read_text(encoding="utf-8")
    assert expected_folder.exists()


def test_create_person_undo_stack_restored_with_prior_snapshots(isolated):
    """TEST 6: Undo stack restored with prior snapshots intact.
    Pushes prior snapshots, fails create_person, and verifies prior snapshots remain untouched."""
    mutation_history.record_pre_mutation_snapshot("Prior Snapshot Alpha")
    mutation_history.record_pre_mutation_snapshot("Prior Snapshot Beta")
    stack_depth_before = len(mutation_history._MUTATION_STACK)
    assert stack_depth_before >= 2

    with patch("app.backend.db.ensure_journal", side_effect=OSError("Disk failure")):
        with pytest.raises(errors.StorageError):
            people.create_person(name="Undo Stack Test Person", group_ids=["family"])

    # Stack depth returns to exactly prior depth
    assert len(mutation_history._MUTATION_STACK) == stack_depth_before
    assert mutation_history.get_last_mutation_description() == "Prior Snapshot Beta"
    assert any(s["description"] == "Prior Snapshot Alpha" for s in mutation_history._MUTATION_STACK)
    assert not any(s["description"] == "Created person: Undo Stack Test Person" for s in mutation_history._MUTATION_STACK)


def test_create_person_provenance_and_sources_rollback(isolated):
    """TEST: Provenance and sources transaction rollback.
    Verifies that no dangling fact_sources or uncommitted sources remain after rollback."""
    conn = db.get_connection()
    sources_before = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    fact_sources_before = conn.execute("SELECT COUNT(*) FROM fact_sources").fetchone()[0]
    conn.close()

    with patch("app.backend.db.ensure_journal", side_effect=OSError("Disk write error")):
        with pytest.raises(errors.StorageError):
            people.create_person(name="Provenance Test Person", group_ids=["family"])

    conn = db.get_connection()
    try:
        sources_after = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        fact_sources_after = conn.execute("SELECT COUNT(*) FROM fact_sources").fetchone()[0]
        dangling = conn.execute("SELECT * FROM fact_sources WHERE entity_key LIKE 'provenance_test_person%'").fetchall()
        assert len(dangling) == 0, "Dangling fact_sources left after rollback!"
        assert fact_sources_after == fact_sources_before
        assert sources_after == sources_before
    finally:
        conn.close()
