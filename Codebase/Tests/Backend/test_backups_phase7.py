"""Phase 7 backup and recovery contract tests. All roots are isolated."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.backend import config
from app.backend.data_root.errors import (
    BackupError,
    DataRootReadOnlyError,
    MaintenanceOperationInProgressError,
    RestoreError,
)
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.backups import (
    BackupCategory,
    SafetyReason,
    create_backup,
    restore_backup,
    verify_backup,
)
from app.backend.domain.backups.manifest import file_sha256, read_backup_manifest
from app.backend.domain.backups.paths import resolve_backup_reference
from app.backend.domain.maintenance import MaintenanceLockContext
from app.backend.services import backups as backup_service


def _created(isolated: Path, label: str = "Phase 7") -> dict:
    return create_backup(label=label, root=isolated)


def _manifest(path: Path) -> dict:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, data: dict) -> None:
    (path / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _tree_digest(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in path.rglob("*")
        if item.is_file()
    }


def _active_state(root: Path) -> tuple[bytes, dict[str, str], dict[str, str]]:
    return (
        DataRootManager.get_database_path(root).read_bytes(),
        _tree_digest(DataRootManager.get_people_dir(root)),
        _tree_digest(DataRootManager.get_config_dir(root)),
    )


def _issue_codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def test_manual_backup_is_staged_verified_and_published_under_manual(isolated):
    created = _created(isolated)
    path = Path(created["path"])
    assert path.parent == isolated / "Backups" / "Manual"
    assert created["verification"]["ok"] is True
    assert not list(path.parent.glob(".backup_staging_*"))


def test_safety_backup_uses_structured_reason(isolated):
    created = create_backup(
        "Before restore",
        BackupCategory.SAFETY,
        SafetyReason.PRE_RESTORE,
        isolated,
    )
    assert Path(created["path"]).parent == isolated / "Backups" / "Safety" / "Pre-Restore"
    assert created["manifest"]["safety_reason"] == "pre_restore"


def test_automatic_category_is_supported_without_scheduler(isolated):
    created = create_backup("Reserved", BackupCategory.AUTOMATIC, root=isolated)
    assert Path(created["path"]).parent == isolated / "Backups" / "Automatic"


def test_safety_reason_is_required_only_for_safety(isolated):
    with pytest.raises(BackupError):
        create_backup("Bad", BackupCategory.SAFETY, root=isolated)
    with pytest.raises(BackupError):
        create_backup("Bad", BackupCategory.MANUAL, SafetyReason.PRE_REPAIR, isolated)


def test_same_tick_ids_are_unique_and_never_overwrite(isolated):
    first = _created(isolated, "same")
    second = _created(isolated, "same")
    assert first["id"] != second["id"]
    assert Path(first["path"]).is_dir() and Path(second["path"]).is_dir()


def test_label_is_preserved_but_path_slug_is_portable(isolated):
    created = _created(isolated, "  Family: Before / Trip ✈  ")
    assert created["manifest"]["label"] == "Family: Before / Trip ✈"
    assert all(char not in created["id"] for char in ":/\\✈ ")


def test_sqlite_wal_open_connection_is_snapshotted_consistently(isolated):
    database = DataRootManager.get_database_path(isolated)
    connection = sqlite3.connect(str(database))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('phase7_wal', 'committed')")
    connection.commit()
    created = _created(isolated, "WAL")
    backup_connection = sqlite3.connect(str(Path(created["path"]) / "data" / "family.db"))
    try:
        assert backup_connection.execute("SELECT value FROM metadata WHERE key='phase7_wal'").fetchone()[0] == "committed"
        assert backup_connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        backup_connection.close()
        connection.close()
    assert not list(Path(created["path"]).rglob("family.db-*"))


def test_people_empty_journal_and_config_are_included_but_temps_are_not(isolated):
    people = DataRootManager.get_people_dir(isolated)
    empty = people / "Family" / "empty_phase7" / "journal.md"
    empty.parent.mkdir(parents=True)
    empty.write_bytes(b"")
    (empty.parent / ".journal-draft.tmp").write_text("private temp", encoding="utf-8")
    config_file = DataRootManager.get_config_dir(isolated) / "phase7.json"
    config_file.write_text('{"portable":true}', encoding="utf-8")
    created = _created(isolated)
    path = Path(created["path"])
    assert (path / "people" / "Family" / "empty_phase7" / "journal.md").read_bytes() == b""
    assert not list(path.rglob("*.tmp"))
    assert (path / "config" / "phase7.json").read_bytes() == config_file.read_bytes()


def test_backups_are_not_recursively_snapshotted(isolated):
    first = _created(isolated, "first")
    second = _created(isolated, "second")
    assert not any("Backups" in entry["path"].split("/") for entry in second["manifest"]["files"])
    assert Path(first["path"]).is_dir()


def test_manifest_entries_are_deterministically_sorted(isolated):
    manifest = _created(isolated)["manifest"]
    paths = [entry["path"] for entry in manifest["files"]]
    assert paths == sorted(paths)


@pytest.mark.parametrize("failure_target", ["database", "people", "manifest", "verification"])
def test_creation_failure_never_publishes_partial_snapshot(isolated, monkeypatch, failure_target):
    from app.backend.domain.backups import create as module

    if failure_target == "database":
        monkeypatch.setattr(module, "_snapshot_sqlite", lambda *_: (_ for _ in ()).throw(OSError("db")))
    elif failure_target == "people":
        monkeypatch.setattr(module, "_copy_tree_safe", lambda *_: (_ for _ in ()).throw(OSError("people")))
    elif failure_target == "manifest":
        monkeypatch.setattr(module, "build_backup_manifest", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("manifest")))
    else:
        monkeypatch.setattr(module, "verify_backup", lambda *_: {"ok": False, "issues": []})
    with pytest.raises(Exception):
        _created(isolated)
    manual = isolated / "Backups" / "Manual"
    assert not [item for item in manual.iterdir() if item.name.startswith("backup-")]
    assert not list(manual.glob(".backup_staging_*"))


def test_symlink_in_snapshot_input_is_refused_and_cleaned(isolated):
    people = DataRootManager.get_people_dir(isolated)
    link = people / "outside-link"
    outside = isolated.parent / "outside-phase7.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")
    with pytest.raises(BackupError) as caught:
        _created(isolated)
    assert caught.value.code == "BACKUP_SYMLINK_UNSAFE"


def test_valid_backup_verifies_with_structured_compatibility(isolated):
    result = verify_backup(Path(_created(isolated)["path"]))
    assert result["ok"] is True
    assert result["status"] == "verified"
    assert result["compatibility"] == {
        "ok": True,
        "status": "supported",
        "backup_schema": config.APP_SCHEMA_VERSION,
        "current_schema": config.APP_SCHEMA_VERSION,
    }


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda data: data.update(kind="wrong"), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data.pop("files"), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data["files"].append(dict(data["files"][0])), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data["files"][0].update(path="/absolute"), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data["files"][0].update(path="../escape"), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data["files"][0].update(sha256="bad"), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data["files"][0].update(size_bytes=-1), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data.update(file_count=999), "BACKUP_MANIFEST_INVALID"),
        (lambda data: data.update(total_size_bytes=999), "BACKUP_MANIFEST_INVALID"),
    ],
)
def test_malformed_manifest_contract_is_rejected(isolated, mutation, code):
    path = Path(_created(isolated)["path"])
    data = _manifest(path)
    mutation(data)
    _write_manifest(path, data)
    assert code in _issue_codes(verify_backup(path))


def test_malformed_json_is_rejected(isolated):
    path = Path(_created(isolated)["path"])
    (path / "manifest.json").write_text("{", encoding="utf-8")
    assert "BACKUP_MANIFEST_INVALID" in _issue_codes(verify_backup(path))


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda file: file.write_bytes(file.read_bytes() + b"x"), "BACKUP_SIZE_MISMATCH"),
        (lambda file: file.write_bytes(b"x" * file.stat().st_size), "BACKUP_HASH_MISMATCH"),
        (lambda file: file.unlink(), "BACKUP_MISSING_FILE"),
    ],
)
def test_payload_tampering_is_rejected(isolated, change, code):
    path = Path(_created(isolated)["path"])
    file = path / "data" / "family.db"
    change(file)
    assert code in _issue_codes(verify_backup(path))


def test_unexpected_payload_file_is_rejected(isolated):
    path = Path(_created(isolated)["path"])
    (path / "people" / "unexpected.txt").write_text("x", encoding="utf-8")
    assert "BACKUP_UNEXPECTED_FILE" in _issue_codes(verify_backup(path))


def test_person_and_journal_count_mismatches_are_rejected(isolated):
    path = Path(_created(isolated)["path"])
    data = _manifest(path)
    data["person_count"] += 1
    data["journal_count"] += 1
    _write_manifest(path, data)
    codes = _issue_codes(verify_backup(path))
    assert {"BACKUP_PERSON_COUNT_MISMATCH", "BACKUP_JOURNAL_COUNT_MISMATCH"} <= codes


def test_newer_schema_is_blocked_even_when_hashes_are_valid(isolated):
    path = Path(_created(isolated)["path"])
    database = path / "data" / "family.db"
    connection = sqlite3.connect(str(database))
    connection.execute("UPDATE metadata SET value=? WHERE key='app_schema_version'", (str(config.APP_SCHEMA_VERSION + 1),))
    connection.execute(f"PRAGMA user_version={config.APP_SCHEMA_VERSION + 1}")
    connection.commit()
    connection.close()
    data = _manifest(path)
    entry = next(item for item in data["files"] if item["path"] == "data/family.db")
    old_size = entry["size_bytes"]
    entry.update(sha256=file_sha256(database), size_bytes=database.stat().st_size)
    data["total_size_bytes"] += entry["size_bytes"] - old_size
    data["sqlite_schema_version"] = config.APP_SCHEMA_VERSION + 1
    data["schema_version"] = config.APP_SCHEMA_VERSION + 1
    _write_manifest(path, data)
    result = verify_backup(path)
    assert result["status"] == "incompatible"
    assert "BACKUP_SCHEMA_TOO_NEW" in _issue_codes(result)


def test_legacy_top_level_v1_snapshot_is_discoverable_and_verifiable(isolated):
    source = Path(_created(isolated)["path"])
    legacy = isolated / "Backups" / "legacy-phase7"
    shutil.copytree(source, legacy)
    data = _manifest(legacy)
    data["format"] = data.pop("kind")
    for key in ("backup_format_version", "category", "safety_reason", "app_version"):
        data.pop(key, None)
    _write_manifest(legacy, data)
    result = next(item for item in backup_service.list_backups(isolated) if item["id"] == "legacy-phase7")
    assert result["category"] == "legacy"
    assert result["verified"] is True


@pytest.mark.parametrize("reference", ["../escape", "..\\escape", "/tmp/escape", "C:\\escape", "nested/id"])
def test_public_backup_id_resolution_rejects_paths(isolated, reference):
    with pytest.raises(BackupError) as caught:
        resolve_backup_reference(reference, isolated)
    assert caught.value.code == "BACKUP_ID_INVALID"


def test_restore_replaces_database_people_and_config_exact_payload(isolated):
    config_file = DataRootManager.get_config_dir(isolated) / "phase7.json"
    config_file.write_text("before", encoding="utf-8")
    created = _created(isolated)
    backup_path = Path(created["path"])
    expected_db = (backup_path / "data" / "family.db").read_bytes()
    expected_people = _tree_digest(backup_path / "people")
    config_file.write_text("after", encoding="utf-8")
    (DataRootManager.get_people_dir(isolated) / "Family" / "new" / "journal.md").parent.mkdir(parents=True)
    (DataRootManager.get_people_dir(isolated) / "Family" / "new" / "journal.md").write_text("new", encoding="utf-8")
    restored = restore_backup(created["id"], root=isolated)
    assert restored["ok"] is True
    assert DataRootManager.get_database_path(isolated).read_bytes() == expected_db
    assert _tree_digest(DataRootManager.get_people_dir(isolated)) == expected_people
    assert config_file.read_text(encoding="utf-8") == "before"


def test_restore_creates_verified_pre_restore_safety_backup_first(isolated):
    created = _created(isolated)
    restored = restore_backup(created["id"], root=isolated)
    safety = resolve_backup_reference(restored["safety_backup_id"], isolated)
    assert safety.parent == isolated / "Backups" / "Safety" / "Pre-Restore"
    assert verify_backup(safety)["ok"] is True


def test_restore_preserves_chosen_and_older_backups(isolated):
    first = _created(isolated, "first")
    second = _created(isolated, "second")
    restored = restore_backup(first["id"], root=isolated)
    assert Path(first["path"]).is_dir() and Path(second["path"]).is_dir()
    assert resolve_backup_reference(restored["safety_backup_id"], isolated).is_dir()


def test_wrong_confirmation_is_blocked_before_safety_mutation(isolated):
    created = _created(isolated)
    before = len(backup_service.list_backups(isolated))
    for token in ("restore", " RESTORE", "RESTORE "):
        with pytest.raises(RestoreError) as caught:
            restore_backup(created["id"], confirmation_token=token, root=isolated)
        assert caught.value.code == "RESTORE_CONFIRMATION_REQUIRED"
    assert len(backup_service.list_backups(isolated)) == before


def test_corrupt_backup_is_blocked_before_safety_mutation(isolated):
    created = _created(isolated)
    (Path(created["path"]) / "data" / "family.db").write_bytes(b"bad")
    before = len(backup_service.list_backups(isolated))
    with pytest.raises(RestoreError) as caught:
        restore_backup(created["id"], root=isolated)
    assert caught.value.code == "BACKUP_CORRUPTED"
    assert len(backup_service.list_backups(isolated)) == before


def test_read_only_root_blocks_create_and_restore_but_not_verify(isolated, monkeypatch):
    created = _created(isolated)
    monkeypatch.setattr(DataRootManager, "is_read_only", classmethod(lambda cls, root=None: True))
    assert verify_backup(Path(created["path"]))["ok"] is True
    with pytest.raises(DataRootReadOnlyError):
        _created(isolated, "blocked")
    with pytest.raises(DataRootReadOnlyError):
        restore_backup(created["id"], root=isolated)


def test_maintenance_conflict_blocks_create_and_restore(isolated):
    created = _created(isolated)
    with MaintenanceLockContext("OTHER"):
        with pytest.raises(MaintenanceOperationInProgressError):
            _created(isolated, "blocked")
        with pytest.raises(MaintenanceOperationInProgressError):
            restore_backup(created["id"], root=isolated)


@pytest.mark.parametrize("component", ["family.db", "People", "Config"])
def test_switch_failure_rolls_back_database_people_and_config_exactly(isolated, monkeypatch, component):
    from app.backend.domain.backups import restore as module

    created = _created(isolated)
    config_file = DataRootManager.get_config_dir(isolated) / "after.json"
    config_file.write_text("after", encoding="utf-8")
    before = _active_state(isolated)
    original = module._switch_component

    def fail(active, staged, rollback):
        if active.name == component:
            raise OSError(f"injected {component}")
        return original(active, staged, rollback)

    monkeypatch.setattr(module, "_switch_component", fail)
    with pytest.raises(RestoreError) as caught:
        restore_backup(created["id"], root=isolated)
    assert caught.value.code == "RESTORE_FAILED"
    assert _active_state(isolated) == before


def test_post_restore_health_failure_rolls_back_exactly(isolated, monkeypatch):
    from app.backend.domain.backups import restore as module

    created = _created(isolated)
    before = _active_state(isolated)
    monkeypatch.setattr(module, "_post_restore_health", lambda *_: (_ for _ in ()).throw(RuntimeError("health")))
    with pytest.raises(RestoreError):
        restore_backup(created["id"], root=isolated)
    assert _active_state(isolated) == before


def test_failed_restore_writes_no_success_history(isolated, monkeypatch):
    from app.backend.domain.backups import restore as module

    created = _created(isolated)
    monkeypatch.setattr(module, "_post_restore_health", lambda *_: (_ for _ in ()).throw(RuntimeError("health")))
    with pytest.raises(RestoreError):
        restore_backup(created["id"], root=isolated)
    assert not (DataRootManager.get_config_dir(isolated) / "restore-history.json").exists()


def test_successful_restore_appends_human_readable_history(isolated):
    created = _created(isolated)
    result = restore_backup(created["id"], root=isolated)
    history = json.loads((DataRootManager.get_config_dir(isolated) / "restore-history.json").read_text(encoding="utf-8"))
    assert history[-1]["result"] == "success"
    assert history[-1]["restored_backup_id"] == created["id"]
    assert history[-1]["safety_backup_id"] == result["safety_backup_id"]


def test_rollback_failure_is_distinct_and_preserves_recovery_assets(isolated, monkeypatch):
    from app.backend.domain.backups import restore as module

    created = _created(isolated)
    original_switch = module._switch_component
    calls = 0

    def fail_after_db(active, staged, rollback):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("switch")
        return original_switch(active, staged, rollback)

    monkeypatch.setattr(module, "_switch_component", fail_after_db)
    monkeypatch.setattr(module, "_rollback_component", lambda *_: (_ for _ in ()).throw(OSError("rollback")))
    with pytest.raises(RestoreError) as caught:
        restore_backup(created["id"], root=isolated)
    assert caught.value.code == "RESTORE_ROLLBACK_FAILED"
    assert Path(caught.value.detail["staging_path"]).exists()
    assert Path(caught.value.detail["rollback_path"]).exists()


def test_listing_returns_all_categories_and_structured_metadata(isolated):
    _created(isolated, "manual")
    create_backup("automatic", BackupCategory.AUTOMATIC, root=isolated)
    create_backup("repair", BackupCategory.SAFETY, SafetyReason.PRE_REPAIR, isolated)
    listed = backup_service.list_backups(isolated)
    assert {item["category"] for item in listed} >= {"manual", "automatic", "safety"}
    assert all("compatibility" in item and "total_size_bytes" in item for item in listed)


def test_api_details_verify_restore_reject_path_ids(client):
    for suffix in ("..%5Cescape", "C:%5Cescape", "nested%2Fid"):
        assert client.get(f"/api/backups/{suffix}").status_code in {400, 404}


def test_api_round_trip_exposes_preview_and_verification(client):
    created = client.post("/api/backups", json={"label": "API Phase 7"})
    assert created.status_code == 200
    backup_id = created.json()["backup"]["id"]
    details = client.get(f"/api/backups/{backup_id}").json()["backup"]
    assert details["replaces"] == ["SQLite database", "People folders and Journals", "portable Config"]
    verified = client.post(f"/api/backups/{backup_id}/verify").json()
    assert verified["ok"] is True
    assert client.post(f"/api/backups/{backup_id}/restore", json={"confirmation_token": ""}).status_code == 400
