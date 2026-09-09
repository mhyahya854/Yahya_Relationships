"""Phase 8 Data Root state, purity, atomicity, and cross-root isolation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from app.backend import db
from app.backend.data_root.errors import DataRootDestinationConflictError, DataRootError, DataRootInvalidError
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.backups import create_backup
from app.backend.domain.mutations.history import can_undo, undo_last_mutation
from app.backend.domain.maintenance import MaintenanceLockContext
from app.backend.services import data_root as service
from app.backend.services.people import create_person


@pytest.fixture(autouse=True)
def clean_manager(monkeypatch, tmp_path):
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(tmp_path / "settings" / "bootstrap.json"))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    DataRootManager.set_override_root(None)
    from app.backend.domain.mutations.history import clear_mutation_history

    clear_mutation_history()
    yield
    clear_mutation_history()
    DataRootManager.set_override_root(None)


def bootstrap_path() -> Path:
    return Path(os.environ["PEOPLE_RELATIONSHIPS_BOOTSTRAP"])


def make_root(tmp_path: Path, name: str, owner: str = "Synthetic Owner") -> Path:
    root = tmp_path / name
    service.initialize_new_data_root(str(root), owner)
    return root


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def staging_paths(parent: Path) -> list[Path]:
    return list(parent.glob(".dr-*-*"))


def test_explicit_absent_bootstrap_is_unconfigured_without_repo_fallback(tmp_path):
    status = service.get_data_root_status()
    assert status["state"] == "UNCONFIGURED"
    assert status["configured"] is False
    assert status["active_root"] is None
    assert not bootstrap_path().parent.exists()


@pytest.mark.parametrize("payload", ["{", "[]", "{}", '{"active_root": null}', '{"active_root": 3}', '{"active_root": ""}'])
def test_malformed_bootstrap_is_structured_invalid(payload):
    bootstrap_path().parent.mkdir(parents=True)
    bootstrap_path().write_text(payload, encoding="utf-8")
    status = service.get_data_root_status()
    assert status["state"] == "INVALID"
    assert status["configured"] is True
    assert status["first_run"] is False
    assert status["health"]["issues"][0]["code"] == "BOOTSTRAP_INVALID"


def test_missing_configured_root_is_not_first_run(tmp_path):
    missing = tmp_path / "missing"
    DataRootManager.set_active_root_pointer(missing)
    status = service.get_data_root_status()
    assert status["state"] == "MISSING"
    assert status["configured"] is True
    assert status["first_run"] is False
    assert not missing.exists()


def test_healthy_root_status_exposes_machine_fields(tmp_path):
    root = make_root(tmp_path, "healthy", "Status Owner")
    status = service.get_data_root_status()
    assert status["state"] == "HEALTHY"
    assert status["schema_version"] == 2
    assert status["root_id"]
    assert status["data_root_format_version"] == 1
    assert status["active_root"] == str(root.resolve())


def test_healthy_read_only_root_has_distinct_state(tmp_path, monkeypatch):
    root = make_root(tmp_path, "read-only")
    original = DataRootManager.is_read_only
    monkeypatch.setattr(
        DataRootManager,
        "is_read_only",
        classmethod(lambda cls, candidate=None: Path(candidate or root).resolve() == root.resolve()),
    )
    assert service.get_data_root_status()["state"] == "READ_ONLY"
    monkeypatch.setattr(DataRootManager, "is_read_only", original)


def test_corrupt_database_is_invalid(tmp_path):
    root = tmp_path / "corrupt"
    (root / "Database" / "Main").mkdir(parents=True)
    (root / "Database" / "People").mkdir(parents=True)
    (root / "Database" / "Main" / "family.db").write_bytes(b"not sqlite")
    DataRootManager.set_active_root_pointer(root)
    status = service.get_data_root_status()
    assert status["state"] == "INVALID"
    assert any(issue["code"] == "DATABASE_ERROR" for issue in status["health"]["issues"])


def test_missing_journal_is_repairable(tmp_path):
    root = make_root(tmp_path, "repairable")
    next((root / "Database" / "People").rglob("journal.md")).unlink()
    assert service.get_data_root_status()["state"] == "REPAIRABLE"


def test_status_and_missing_candidate_reads_create_nothing(tmp_path):
    missing = tmp_path / "never-created" / "candidate"
    before = list(tmp_path.rglob("*"))
    inspected = service.inspect_data_root(str(missing))
    status = service.get_data_root_status()
    after = list(tmp_path.rglob("*"))
    assert inspected["state"] == "MISSING"
    assert status["state"] == "UNCONFIGURED"
    assert before == after
    assert not missing.exists()


def test_candidate_inspection_returns_metadata_without_switching(tmp_path):
    root_a = make_root(tmp_path, "root-a", "Owner A")
    root_b = make_root(tmp_path, "root-b", "Owner B")
    service.switch_data_root(str(root_a))
    before = bootstrap_path().read_bytes()
    candidate = service.inspect_data_root(str(root_b))
    assert candidate["can_switch"] is True
    assert candidate["person_count"] == 1
    assert candidate["journal_count"] == 1
    assert candidate["schema_version"] == 2
    assert candidate["root_id"]
    assert bootstrap_path().read_bytes() == before


def test_candidate_rejects_arbitrary_folder(tmp_path):
    random_dir = tmp_path / "random"
    random_dir.mkdir()
    (random_dir / "note.txt").write_text("user file", encoding="utf-8")
    candidate = service.inspect_data_root(str(random_dir))
    assert candidate["can_switch"] is False
    assert candidate["issues"][0]["code"] == "DATA_ROOT_INVALID"


def test_candidate_rejects_backup_snapshot(tmp_path):
    root = make_root(tmp_path, "source")
    backup = Path(create_backup("candidate rejection", root=root)["path"])
    candidate = service.inspect_data_root(str(backup))
    assert candidate["is_backup_snapshot"] is True
    assert candidate["can_switch"] is False
    assert candidate["issues"][0]["code"] == "BACKUP_SNAPSHOT_REJECTED"


def test_bootstrap_write_is_utf8_json_with_canonical_absolute_path(tmp_path):
    root = make_root(tmp_path, "unicode — عائلة", "Owner")
    payload = json.loads(bootstrap_path().read_text(encoding="utf-8"))
    assert Path(payload["active_root"]) == root.resolve()
    assert payload["updated_at"].endswith("Z")
    assert payload["root_id"]
    assert not list(bootstrap_path().parent.glob(".bootstrap-*.tmp"))


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_bootstrap_failure_preserves_old_bytes_and_cleans_temp(tmp_path, monkeypatch, failure):
    root_a = make_root(tmp_path, "root-a")
    root_b = tmp_path / "root-b"
    old = bootstrap_path().read_bytes()
    import app.backend.data_root.manager as manager

    if failure == "fsync":
        monkeypatch.setattr(manager.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("fsync failure")))
    else:
        monkeypatch.setattr(manager.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failure")))
    with pytest.raises(OSError):
        DataRootManager.set_active_root_pointer(root_b)
    assert bootstrap_path().read_bytes() == old
    assert DataRootManager.resolve_active_root() == root_a.resolve()
    assert not list(bootstrap_path().parent.glob(".bootstrap-*.tmp"))


def test_create_new_uses_user_owner_and_default_perspective(tmp_path):
    root = make_root(tmp_path, "new", "Amina Example")
    connection = sqlite3.connect(root / "Database" / "Main" / "family.db")
    try:
        owner = connection.execute("SELECT id, name, gender FROM people").fetchone()
        focus = connection.execute("SELECT value FROM metadata WHERE key='focus_person'").fetchone()[0]
        schema = connection.execute("SELECT value FROM metadata WHERE key='app_schema_version'").fetchone()[0]
    finally:
        connection.close()
    assert owner == ("amina_example", "Amina Example", None)
    assert focus == owner[0]
    assert schema == "2"
    assert json.loads((root / "Database" / "Config" / "state.json").read_text())["perspective_person_id"] == owner[0]
    assert len(list((root / "Database" / "People").rglob("journal.md"))) == 1


@pytest.mark.parametrize("kind", ["random", "valid"])
def test_create_new_refuses_every_nonempty_destination(tmp_path, kind):
    active = make_root(tmp_path, "active")
    target = tmp_path / "target"
    if kind == "random":
        target.mkdir()
        (target / "user.txt").write_text("keep", encoding="utf-8")
    else:
        service.initialize_new_data_root(str(target), "Other Owner")
        service.switch_data_root(str(active))
    old = bootstrap_path().read_bytes()
    with pytest.raises(DataRootDestinationConflictError):
        service.initialize_new_data_root(str(target), "New Owner")
    assert bootstrap_path().read_bytes() == old
    assert target.exists()


def test_create_new_accepts_existing_empty_directory(tmp_path):
    target = tmp_path / "empty"
    target.mkdir()
    result = service.initialize_new_data_root(str(target), "Empty Target Owner", "unknown")
    assert result["ok"] is True
    assert service.inspect_data_root(str(target))["can_switch"] is True


@pytest.mark.parametrize("failure_point", ["structure", "database", "owner", "validation"])
def test_create_failure_before_publication_is_atomic(tmp_path, monkeypatch, failure_point):
    old_root = make_root(tmp_path, "old")
    old_pointer = bootstrap_path().read_bytes()
    target = tmp_path / "new"
    if failure_point == "structure":
        monkeypatch.setattr(DataRootManager, "ensure_structure", classmethod(lambda cls, *args, **kwargs: (_ for _ in ()).throw(OSError("structure"))))
    elif failure_point == "database":
        monkeypatch.setattr(service.db, "initialize_database", lambda *_: (_ for _ in ()).throw(OSError("database")))
    elif failure_point == "owner":
        monkeypatch.setattr(service, "_create_initial_owner", lambda *_: (_ for _ in ()).throw(OSError("owner")))
    else:
        monkeypatch.setattr(service, "audit_data_root", lambda *_: (_ for _ in ()).throw(OSError("validation")))
    with pytest.raises(OSError):
        service.initialize_new_data_root(str(target), "Failure Owner")
    assert bootstrap_path().read_bytes() == old_pointer
    assert DataRootManager.resolve_active_root() == old_root.resolve()
    assert not target.exists()
    assert not staging_paths(tmp_path)


def test_create_pointer_failure_keeps_complete_inactive_root(tmp_path, monkeypatch):
    old_root = make_root(tmp_path, "old")
    old_pointer = bootstrap_path().read_bytes()
    target = tmp_path / "published"
    original = DataRootManager.set_active_root_pointer

    def fail_for_target(cls, new_root):
        if Path(new_root).resolve() == target.resolve():
            raise OSError("pointer")
        return original(new_root)

    monkeypatch.setattr(DataRootManager, "set_active_root_pointer", classmethod(fail_for_target))
    with pytest.raises(DataRootError) as caught:
        service.initialize_new_data_root(str(target), "Published Owner")
    assert caught.value.code == "BOOTSTRAP_UPDATE_FAILED"
    assert bootstrap_path().read_bytes() == old_pointer
    assert DataRootManager.resolve_active_root() == old_root.resolve()
    assert service.inspect_data_root(str(target))["can_switch"] is True
    assert not staging_paths(tmp_path)


def test_switch_healthy_root_and_same_root_noop(tmp_path):
    root_a = make_root(tmp_path, "a", "A")
    root_b = make_root(tmp_path, "b", "B")
    service.switch_data_root(str(root_a))
    changed = service.switch_data_root(str(root_b))
    same = service.switch_data_root(str(root_b))
    assert changed["unchanged"] is False
    assert same["unchanged"] is True
    assert DataRootManager.resolve_active_root() == root_b.resolve()


def test_switch_accepts_healthy_read_only_candidate(tmp_path, monkeypatch):
    root_a = make_root(tmp_path, "a")
    root_b = make_root(tmp_path, "b")
    service.switch_data_root(str(root_a))
    monkeypatch.setattr(DataRootManager, "is_read_only", classmethod(lambda cls, root=None: Path(root).resolve() == root_b.resolve()))
    result = service.switch_data_root(str(root_b))
    assert result["candidate"]["state"] == "READ_ONLY"
    assert DataRootManager.resolve_active_root() == root_b.resolve()


def test_switch_blocks_corrupt_and_unsupported_schema(tmp_path):
    root_a = make_root(tmp_path, "a")
    corrupt = tmp_path / "corrupt"
    (corrupt / "Database" / "Main").mkdir(parents=True)
    (corrupt / "Database" / "People").mkdir(parents=True)
    (corrupt / "Database" / "Main" / "family.db").write_bytes(b"bad")
    with pytest.raises(DataRootInvalidError):
        service.switch_data_root(str(corrupt))
    newer = make_root(tmp_path, "newer")
    connection = sqlite3.connect(newer / "Database" / "Main" / "family.db")
    connection.execute("UPDATE metadata SET value='99' WHERE key='app_schema_version'")
    connection.execute("PRAGMA user_version=99")
    connection.commit()
    connection.close()
    service.switch_data_root(str(root_a))
    with pytest.raises(DataRootInvalidError):
        service.switch_data_root(str(newer))


def test_switch_clears_cross_root_undo_history(tmp_path):
    root_a = make_root(tmp_path, "a", "Alice Root A")
    root_b = make_root(tmp_path, "b", "Bob Root B")
    service.switch_data_root(str(root_a))
    create_person(name="Root A mutation")
    assert can_undo() is True
    before_b = file_hash(root_b / "Database" / "Main" / "family.db")
    service.switch_data_root(str(root_b))
    assert can_undo() is False
    with pytest.raises(Exception):
        undo_last_mutation()
    assert file_hash(root_b / "Database" / "Main" / "family.db") == before_b


def test_restore_external_backup_to_separate_new_root(tmp_path):
    source = make_root(tmp_path, "source", "Restore Owner")
    create_person(name="Restored Person")
    backup = Path(create_backup("external restore", root=source)["path"])
    source_hashes = {str(path.relative_to(backup)): file_hash(path) for path in backup.rglob("*") if path.is_file()}
    destination = tmp_path / "destination"
    result = service.restore_backup_to_data_root(str(backup), str(destination))
    assert result["ok"] is True
    assert DataRootManager.resolve_active_root() == destination.resolve()
    assert service.inspect_data_root(str(destination))["person_count"] == 2
    assert source_hashes == {str(path.relative_to(backup)): file_hash(path) for path in backup.rglob("*") if path.is_file()}
    assert not staging_paths(tmp_path)


@pytest.mark.parametrize("relation", ["same", "destination_inside_source", "source_inside_destination"])
def test_restore_rejects_overlapping_source_and_destination(tmp_path, relation):
    source_root = make_root(tmp_path, "source")
    backup = Path(create_backup("paths", root=source_root)["path"])
    if relation == "same":
        destination = backup
    elif relation == "destination_inside_source":
        destination = backup / "new-root"
    else:
        destination = tmp_path / "outer"
        nested_backup = destination / "backup"
        nested_backup.parent.mkdir()
        import shutil
        shutil.copytree(backup, nested_backup)
        backup = nested_backup
    with pytest.raises(DataRootDestinationConflictError):
        service.restore_backup_to_data_root(str(backup), str(destination))


def test_restore_failure_leaves_pointer_source_and_destination_unchanged(tmp_path, monkeypatch):
    active = make_root(tmp_path, "active")
    backup = Path(create_backup("failure", root=active)["path"])
    backup_manifest_hash = file_hash(backup / "manifest.json")
    pointer = bootstrap_path().read_bytes()
    destination = tmp_path / "destination"
    monkeypatch.setattr(service, "restore_backup", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("restore copy")))
    with pytest.raises(OSError):
        service.restore_backup_to_data_root(str(backup), str(destination))
    assert bootstrap_path().read_bytes() == pointer
    assert file_hash(backup / "manifest.json") == backup_manifest_hash
    assert not destination.exists()
    assert not staging_paths(tmp_path)


def test_restore_pointer_failure_keeps_complete_inactive_root(tmp_path, monkeypatch):
    active = make_root(tmp_path, "active")
    backup = Path(create_backup("pointer failure", root=active)["path"])
    destination = tmp_path / "restored"
    old_pointer = bootstrap_path().read_bytes()
    monkeypatch.setattr(DataRootManager, "set_active_root_pointer", classmethod(lambda cls, root: (_ for _ in ()).throw(OSError("pointer"))))
    with pytest.raises(DataRootError) as caught:
        service.restore_backup_to_data_root(str(backup), str(destination))
    assert caught.value.code == "BOOTSTRAP_UPDATE_FAILED"
    assert bootstrap_path().read_bytes() == old_pointer
    assert service.inspect_data_root(str(destination))["can_switch"] is True


def test_move_copies_only_runtime_payload_and_retains_old_root(tmp_path):
    source = make_root(tmp_path, "source", "Move Owner")
    (source / "Codebase").mkdir()
    (source / "Codebase" / "secret.py").write_text("not runtime", encoding="utf-8")
    (source / "Documentation").mkdir()
    (source / "Documentation" / "notes.md").write_text("not runtime", encoding="utf-8")
    root_id = DataRootManager.read_root_metadata(source)["root_id"]
    destination = tmp_path / "destination"
    result = service.move_data_root(str(destination))
    assert result["ok"] is True
    assert result["old_root_retained"] is True
    assert source.exists()
    assert not (destination / "Codebase").exists()
    assert not (destination / "Documentation").exists()
    assert DataRootManager.read_root_metadata(destination)["root_id"] == root_id
    assert list((source / "Backups" / "Safety" / "Pre-Organization").iterdir())
    assert service._runtime_inventory(source) == service._runtime_inventory(destination)


@pytest.mark.parametrize("failure", ["copy", "inventory", "publication"])
def test_move_failure_before_publication_leaves_clean_destination(tmp_path, monkeypatch, failure):
    source = make_root(tmp_path, "source")
    pointer = bootstrap_path().read_bytes()
    destination = tmp_path / "destination"
    if failure == "copy":
        monkeypatch.setattr(service, "_copy_runtime_payload", lambda *_: (_ for _ in ()).throw(OSError("copy")))
    elif failure == "inventory":
        original = service._runtime_inventory
        calls = {"count": 0}

        def mismatch(root):
            calls["count"] += 1
            rows = original(root)
            return rows + ([{"path": "missing", "size": 0, "sha256": "x"}] if calls["count"] == 2 else [])

        monkeypatch.setattr(service, "_runtime_inventory", mismatch)
    else:
        monkeypatch.setattr(service, "_publish", lambda *_: (_ for _ in ()).throw(OSError("publication")))
    with pytest.raises((OSError, DataRootInvalidError)):
        service.move_data_root(str(destination))
    assert bootstrap_path().read_bytes() == pointer
    assert DataRootManager.resolve_active_root() == source.resolve()
    assert not destination.exists()
    assert not staging_paths(tmp_path)
    assert list((source / "Backups" / "Safety" / "Pre-Organization").iterdir())


def test_move_pointer_failure_keeps_old_root_authoritative(tmp_path, monkeypatch):
    source = make_root(tmp_path, "source")
    destination = tmp_path / "destination"
    old_pointer = bootstrap_path().read_bytes()
    monkeypatch.setattr(DataRootManager, "set_active_root_pointer", classmethod(lambda cls, root: (_ for _ in ()).throw(OSError("pointer"))))
    with pytest.raises(DataRootError) as caught:
        service.move_data_root(str(destination))
    assert caught.value.code == "BOOTSTRAP_UPDATE_FAILED"
    assert bootstrap_path().read_bytes() == old_pointer
    assert DataRootManager.resolve_active_root() == source.resolve()
    assert service.inspect_data_root(str(destination))["can_switch"] is True


def test_maintenance_conflict_blocks_root_change(tmp_path):
    source = make_root(tmp_path, "source")
    other = make_root(tmp_path, "other")
    service.switch_data_root(str(source))
    with MaintenanceLockContext("TEST_OPERATION"):
        with pytest.raises(Exception):
            service.switch_data_root(str(other))


def test_backend_health_is_reachable_when_unconfigured_and_malformed(tmp_path):
    from fastapi.testclient import TestClient
    from app.backend.api.main import app

    with TestClient(app) as client:
        first = client.get("/api/health")
        assert first.status_code == 200
        assert first.json()["service_ok"] is True
        assert first.json()["status"] == "DATA_ROOT_UNCONFIGURED"
        bootstrap_path().parent.mkdir(parents=True, exist_ok=True)
        bootstrap_path().write_text("{", encoding="utf-8")
        malformed = client.get("/api/health")
        assert malformed.status_code == 200
        assert malformed.json()["service_ok"] is True
        assert malformed.json()["status"] == "DATA_ROOT_INVALID"


@pytest.mark.parametrize("gender", ["male", "female", "unknown"])
def test_create_owner_uses_each_supported_optional_gender(tmp_path, gender):
    root = tmp_path / gender
    result = service.initialize_new_data_root(str(root), f"{gender.title()} Owner", gender)
    connection = sqlite3.connect(root / "Database" / "Main" / "family.db")
    try:
        assert connection.execute("SELECT gender FROM people WHERE id=?", (result["owner_id"],)).fetchone()[0] == gender
    finally:
        connection.close()


def test_inspect_existing_empty_directory_is_pure(tmp_path):
    target = tmp_path / "empty"
    target.mkdir()
    before = list(target.iterdir())
    result = service.inspect_data_root(str(target))
    assert result["is_empty"] is True
    assert result["can_switch"] is False
    assert list(target.iterdir()) == before


@pytest.mark.parametrize("candidate_kind", ["missing", "random", "backup"])
def test_switch_rejects_non_root_candidates_without_pointer_change(tmp_path, candidate_kind):
    active = make_root(tmp_path, "active")
    pointer = bootstrap_path().read_bytes()
    if candidate_kind == "missing":
        candidate = tmp_path / "missing"
    elif candidate_kind == "random":
        candidate = tmp_path / "random"
        candidate.mkdir()
        (candidate / "keep.txt").write_text("keep", encoding="utf-8")
    else:
        candidate = Path(create_backup("switch rejection", root=active)["path"])
        pointer = bootstrap_path().read_bytes()
    with pytest.raises(DataRootInvalidError):
        service.switch_data_root(str(candidate))
    assert bootstrap_path().read_bytes() == pointer
    assert DataRootManager.resolve_active_root() == active.resolve()


def test_restore_refuses_nonempty_destination_without_overwrite(tmp_path):
    active = make_root(tmp_path, "active")
    backup = Path(create_backup("restore refusal", root=active)["path"])
    destination = tmp_path / "nonempty"
    destination.mkdir()
    protected = destination / "user.txt"
    protected.write_text("keep", encoding="utf-8")
    with pytest.raises(DataRootDestinationConflictError):
        service.restore_backup_to_data_root(str(backup), str(destination))
    assert protected.read_text(encoding="utf-8") == "keep"


def test_move_refuses_nonempty_destination_without_overwrite(tmp_path):
    make_root(tmp_path, "active")
    destination = tmp_path / "nonempty"
    destination.mkdir()
    protected = destination / "user.txt"
    protected.write_text("keep", encoding="utf-8")
    with pytest.raises(DataRootDestinationConflictError):
        service.move_data_root(str(destination))
    assert protected.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("direction", ["destination_in_source", "source_in_destination"])
def test_move_rejects_containment_in_both_directions(tmp_path, direction):
    source = make_root(tmp_path, "source")
    destination = source / "nested" if direction == "destination_in_source" else tmp_path
    with pytest.raises(DataRootDestinationConflictError):
        service.move_data_root(str(destination))


def test_safe_repair_restores_supported_items_and_preserves_orphan(tmp_path):
    root = make_root(tmp_path, "repair")
    journal = next((root / "Database" / "People").rglob("journal.md"))
    journal.unlink()
    orphan = root / "Database" / "People" / "Other" / "human-review"
    orphan.mkdir(parents=True)
    (orphan / "notes.md").write_text("preserve", encoding="utf-8")
    result = service.safe_repair_active_data_root()
    assert result["ok"] is True
    assert journal.exists()
    assert (orphan / "notes.md").read_text(encoding="utf-8") == "preserve"


def test_restore_preserves_backed_up_root_identity(tmp_path):
    source = make_root(tmp_path, "source")
    root_id = DataRootManager.read_root_metadata(source)["root_id"]
    backup = Path(create_backup("identity", root=source)["path"])
    destination = tmp_path / "restored"
    service.restore_backup_to_data_root(str(backup), str(destination))
    assert DataRootManager.read_root_metadata(destination)["root_id"] == root_id


def test_move_excludes_recognized_runtime_transients(tmp_path):
    source = make_root(tmp_path, "source")
    transient_files = [
        source / "Database" / "Main" / "family.db-wal",
        source / "Database" / "Main" / "family.db-shm",
        source / "Database" / "People" / ".journal-test.tmp",
        source / "Backups" / ".backup_staging_test" / "partial.bin",
    ]
    for path in transient_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"transient")
    destination = tmp_path / "moved"
    service.move_data_root(str(destination))
    assert not (destination / "Database" / "Main" / "family.db-wal").exists()
    assert not (destination / "Database" / "Main" / "family.db-shm").exists()
    assert not (destination / "Database" / "People" / ".journal-test.tmp").exists()
    assert not (destination / "Backups" / ".backup_staging_test").exists()


def test_invalid_candidate_inspection_does_not_change_pointer(tmp_path):
    active = make_root(tmp_path, "active")
    pointer = bootstrap_path().read_bytes()
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    service.inspect_data_root(str(invalid))
    assert bootstrap_path().read_bytes() == pointer
    assert DataRootManager.resolve_active_root() == active.resolve()
