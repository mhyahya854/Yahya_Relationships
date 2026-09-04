"""Test suite for Data Safety, Filesystem-Aware Undo, Guided Backup Restore, and Data Root Portability."""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.backend.data_root.errors import (
    BackupManifestInvalidError,
    DataRootDestinationConflictError,
    DataRootInvalidError,
    DataRootNotFoundError,
    DataRootReadOnlyError,
    RestoreError,
    UndoFilesystemConflictError,
)
from app.backend.data_root.manager import DataRootManager
from app.backend.data_root.validation import audit_data_root, safe_repair_data_root
from app.backend.domain.backups import create_backup, restore_backup, verify_backup
from app.backend.domain.mutations import history as mutation_history
from app.backend.services import data_root as data_root_service
from app.backend.services import people, family, general


def test_data_root_manager_resolution(isolated):
    assert DataRootManager.resolve_active_root() == isolated
    assert DataRootManager.get_people_dir() in (isolated / "Database" / "People", isolated / "people")
    assert DataRootManager.get_backups_dir() in (isolated / "Backups", isolated / "backups")
    assert DataRootManager.get_config_dir() in (isolated / "Database" / "Config", isolated / "config")


def test_audit_data_root_healthy(isolated):
    health = audit_data_root(isolated)
    assert health.ok is True
    assert health.database is not None
    assert health.database.integrity == "ok"
    assert health.database.people_count >= 1


def test_reconciliation_detects_mismatches(isolated):
    people_dir = DataRootManager.get_people_dir(isolated)
    # 1. Create a DB person with NO folder (Missing folder)
    p = people.create_person(name="Test Missing Folder Person", group_id="family")
    missing_pid = p["id"]
    folder = people_dir / "Family" / missing_pid
    if folder.exists():
        shutil.rmtree(folder)

    # 2. Create an Orphan folder (Folder on disk, absent from DB)
    orphan_dir = people_dir / "Family" / "orphan_test_id"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "journal.md").write_text("# Orphan\n\nText")

    # 3. Create an Archived-Active Mismatch
    p_arch = people.create_person(name="Test Mismatch Person", group_id="family")
    mismatch_pid = p_arch["id"]
    active_f = people_dir / "Family" / mismatch_pid
    archived_f = people_dir / "_archived" / mismatch_pid
    archived_f.parent.mkdir(parents=True, exist_ok=True)
    if active_f.exists():
        shutil.move(str(active_f), str(archived_f))

    # Audit root
    health = audit_data_root(isolated)
    assert health.ok is False

    issue_codes = [i.code for i in health.issues]
    assert "MISSING_PERSON_FOLDER" in issue_codes
    assert "ORPHAN_PERSON_FOLDER" in issue_codes
    assert "ARCHIVED_ACTIVE_MISMATCH" in issue_codes

    # Run safe repair
    repair_res = safe_repair_data_root(isolated)
    assert repair_res["ok"] is True
    assert repair_res["repaired"] >= 2

    # Verify missing folder & mismatch were repaired
    post_health = audit_data_root(isolated)
    post_codes = [i.code for i in post_health.issues]
    assert "MISSING_PERSON_FOLDER" not in post_codes
    assert "ARCHIVED_ACTIVE_MISMATCH" not in post_codes
    # Orphan folder remains for manual inspection (NEVER auto-deleted)
    assert "ORPHAN_PERSON_FOLDER" in post_codes


def test_filesystem_aware_undo_add_person(isolated):
    people_dir = DataRootManager.get_people_dir(isolated)
    # Create person
    p = people.create_person(name="Undo Test Person", group_id="friends")
    pid = p["id"]
    journal_file = people_dir / "Friends" / pid / "journal.md"
    assert journal_file.exists()

    # Undo
    undo_res = mutation_history.undo_last_mutation()
    assert undo_res["ok"] is True

    # DB person is gone AND folder/journal is removed
    assert not journal_file.exists()
    assert not (people_dir / "Friends" / pid).exists()
    with pytest.raises(Exception):
        people.get_person(pid)


def test_filesystem_conflict_blocks_undo(isolated):
    people_dir = DataRootManager.get_people_dir(isolated)
    # Create person
    p = people.create_person(name="Conflict Test Person", group_id="friends")
    pid = p["id"]
    journal_file = people_dir / "Friends" / pid / "journal.md"
    assert journal_file.exists()

    # User modifies journal externally!
    journal_file.write_text("# Conflict Test Person\n\nExternal secret notes added!", encoding="utf-8")

    # Attempt normal Undo -> Must fail with UndoFilesystemConflictError
    with pytest.raises(UndoFilesystemConflictError) as exc_info:
        mutation_history.undo_last_mutation(force_archive_conflicts=False)

    assert exc_info.value.code == "UNDO_FILESYSTEM_CONFLICT"
    assert str(journal_file) in exc_info.value.detail["affected_paths"]

    # Force archive conflicts -> Moves modified journal to _archived and restores DB
    undo_res = mutation_history.undo_last_mutation(force_archive_conflicts=True)
    assert undo_res["ok"] is True
    assert not journal_file.exists()
    archived_items = list((people_dir / "_archived").glob(f"conflict_{pid}_*"))
    assert len(archived_items) >= 1


def test_filesystem_aware_undo_delete_person(isolated):
    people_dir = DataRootManager.get_people_dir(isolated)
    p = people.create_person(name="Delete Undo Test Person", group_id="colleagues")
    pid = p["id"]
    active_folder = people_dir / "Colleagues" / pid
    assert active_folder.exists()

    # Delete person
    del_res = people.delete_person(pid, force=True)
    assert del_res["deleted"] == pid
    assert not active_folder.exists()
    archived_folder = Path(del_res["folder_archived"])
    assert archived_folder.exists()

    # Undo deletion
    undo_res = mutation_history.undo_last_mutation()
    assert undo_res["ok"] is True

    # Folder moved back to Colleagues AND DB person restored
    assert active_folder.exists()
    assert not archived_folder.exists()
    restored = people.get_person(pid)
    assert restored["name"] == "Delete Undo Test Person"


def test_backup_create_verify_restore(isolated):
    # Create a test backup
    b_res = create_backup(label="unit_test_backup", root=isolated)
    b_id = b_res["id"]
    assert b_res["verification"]["ok"] is True

    # Make a mutation (Add a new person)
    p = people.create_person(name="Post Backup Person", group_id="family")
    post_id = p["id"]
    assert people.get_person(post_id) is not None

    # Restore backup
    rest_res = restore_backup(b_id, confirmation_token="RESTORE", root=isolated)
    assert rest_res["ok"] is True
    assert rest_res["restored_backup_id"] == b_id
    assert rest_res["safety_backup_id"].startswith("backup-")

    # Person created after backup is now gone (restored to pre-mutation state)
    with pytest.raises(Exception):
        people.get_person(post_id)

    # SQLite integrity passes post-restore
    health = audit_data_root(isolated)
    assert health.ok is True


def test_restore_invalid_token_raises(isolated):
    b_res = create_backup(label="token_test", root=isolated)
    with pytest.raises(RestoreError):
        restore_backup(b_res["id"], confirmation_token="WRONG", root=isolated)


def test_data_root_move(isolated, tmp_path):
    dest_dir = tmp_path.parent / "moved_data_root"

    # Move active data root
    res = data_root_service.move_data_root(str(dest_dir))
    assert res["ok"] is True
    assert DataRootManager.resolve_active_root() == dest_dir.resolve()

    # Restore pointer back for clean test teardown
    DataRootManager.set_active_root_pointer(isolated)


def test_data_root_switch_rejects_backup_snapshot(isolated):
    b_res = create_backup(label="snapshot_test", root=isolated)
    backup_path = b_res["path"]

    with pytest.raises(DataRootInvalidError) as exc_info:
        data_root_service.switch_data_root(backup_path)

    assert exc_info.value.detail["code"] == "BACKUP_SNAPSHOT_REJECTED"
