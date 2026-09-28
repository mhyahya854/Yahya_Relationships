"""Failure-atomic Data Root lifecycle service."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any, Dict

from .. import config, db
from ..data_root import DataRootHealth, DataRootManager, DataRootState, ValidationIssue
from ..data_root.errors import (
    DataRootDestinationConflictError,
    DataRootError,
    DataRootInvalidError,
    DataRootNotFoundError,
    DataRootReadOnlyError,
)
from ..data_root.validation import audit_data_root, safe_repair_data_root
from ..domain.backups import BackupCategory, SafetyReason, create_backup, restore_backup, verify_backup
from ..domain.backups.paths import native_io_path, remove_tree
from ..domain.maintenance import MaintenanceLockContext, is_maintenance_locked
from ..domain.raw_intake import _destination_path_for_existing, _locked

_REPAIRABLE_CODES = {"MISSING_PERSON_FOLDER", "MISSING_JOURNAL", "ARCHIVED_ACTIVE_MISMATCH"}
_RUNTIME_NAMES = (
    "Database",
    "People",
    "Backups",
    "Raw",
    "Media",
    ".mosaic-quarantine",
    "family.db",
    "people",
    "config",
    "backups",
    "sources",
    "exports",
    "logs",
)


def _state_for_health(health: DataRootHealth) -> DataRootState:
    if health.layout_mode == "missing":
        return DataRootState.MISSING
    blocking = [issue for issue in health.issues if issue.severity == "error"]
    if blocking and all(issue.code in _REPAIRABLE_CODES for issue in blocking):
        return DataRootState.REPAIRABLE
    if blocking or health.database is None or health.database.integrity != "ok":
        return DataRootState.INVALID
    if health.read_only:
        return DataRootState.READ_ONLY
    if any(issue.code in _REPAIRABLE_CODES for issue in health.issues):
        return DataRootState.REPAIRABLE
    return DataRootState.HEALTHY


def _invalid_bootstrap_health() -> DataRootHealth:
    return DataRootHealth(
        ok=False,
        read_only=False,
        layout_mode="bootstrap_invalid",
        root_path="",
        issues=[
            ValidationIssue(
                code="BOOTSTRAP_INVALID",
                severity="error",
                message="Your saved data-location setting could not be read.",
                suggested_action="Choose an existing Data Root, restore a backup, or retry.",
            )
        ],
    )


def _unconfigured_health() -> DataRootHealth:
    return DataRootHealth(
        ok=False,
        read_only=False,
        layout_mode="unconfigured",
        root_path="",
        issues=[],
    )


def _metadata_fields(root: Path | None) -> Dict[str, Any]:
    metadata = DataRootManager.read_root_metadata(root) if root else {}
    return {
        "root_id": metadata.get("root_id"),
        "data_root_format_version": metadata.get("version"),
    }


def get_data_root_status() -> Dict[str, Any]:
    authority = DataRootManager.bootstrap_status()
    locked, operation = is_maintenance_locked()
    if authority["invalid"]:
        health = _invalid_bootstrap_health()
        state = DataRootState.INVALID
        active_root = None
    elif not authority["configured"]:
        active_root = None
        health = _unconfigured_health()
        state = DataRootState.UNCONFIGURED
    else:
        active_root = authority["active_root"]
        health = audit_data_root(active_root)
        state = _state_for_health(health)
    if locked:
        state = DataRootState.MAINTENANCE

    root = active_root if isinstance(active_root, Path) else None
    result = {
        "configured": bool(authority["configured"]),
        "first_run": state is DataRootState.UNCONFIGURED,
        "state": state.value,
        "active_root": str(root) if root else None,
        "last_configured_root": str(root) if root else None,
        "database_path": str(DataRootManager.get_database_path(root)) if root else None,
        "people_dir": str(DataRootManager.get_people_dir(root)) if root else None,
        "backups_dir": str(DataRootManager.get_backups_dir(root)) if root else None,
        "config_dir": str(DataRootManager.get_config_dir(root)) if root else None,
        "read_only": health.read_only,
        "maintenance_locked": locked,
        "maintenance_operation": operation,
        "schema_version": health.database.schema_version if health.database else None,
        "health": health.to_dict(),
    }
    result.update(_metadata_fields(root))
    return result


def inspect_data_root(path: str) -> Dict[str, Any]:
    """Inspect a candidate without creating, repairing, or activating it."""
    candidate = Path(path).expanduser().resolve()
    is_directory = candidate.is_dir()
    base: Dict[str, Any] = {
        "path": str(candidate),
        "exists": candidate.exists(),
        "is_directory": is_directory,
        "is_backup_snapshot": DataRootManager.is_backup_snapshot(candidate),
        "valid_structure": False,
        "state": DataRootState.INVALID.value,
        "read_only": False,
        "health": None,
        "schema_version": None,
        "data_root_format_version": None,
        "root_id": None,
        "person_count": 0,
        "journal_count": 0,
        "issues": [],
        "can_switch": False,
        "is_empty": is_directory and not any(candidate.iterdir()),
    }
    if not candidate.exists():
        base["state"] = DataRootState.MISSING.value
        base["issues"] = [{"code": "DATA_ROOT_MISSING", "severity": "error", "message": "The selected path does not exist."}]
        return base
    if not is_directory or candidate.is_symlink():
        base["issues"] = [{"code": "UNSAFE_ROOT_PATH", "severity": "error", "message": "The selected path is not a safe directory."}]
        return base
    if base["is_backup_snapshot"]:
        base["issues"] = [{"code": "BACKUP_SNAPSHOT_REJECTED", "severity": "error", "message": "A backup snapshot cannot be used as a live Data Root."}]
        return base
    try:
        DataRootManager.validate_data_root_structure(candidate)
        base["valid_structure"] = True
    except DataRootError as exc:
        base["issues"] = [exc.to_dict()]
        return base

    health = audit_data_root(candidate)
    state = _state_for_health(health)
    base.update(
        {
            "state": state.value,
            "read_only": health.read_only,
            "health": health.to_dict(),
            "schema_version": health.database.schema_version if health.database else None,
            "person_count": health.database.people_count if health.database else 0,
            "journal_count": sum(
                1
                for item in native_io_path(DataRootManager.get_people_dir(candidate)).rglob("*")
                if item.is_file()
                and item.name in {"journal.md", "journal(personal thoughts).md"}
            ),
            "issues": [issue.to_dict() for issue in health.issues],
            "can_switch": state in {DataRootState.HEALTHY, DataRootState.READ_ONLY},
            **_metadata_fields(candidate),
        }
    )
    return base


def inspect_backup_snapshot(path: str) -> Dict[str, Any]:
    """Verify an explicitly selected external backup without changing it."""
    backup = Path(path).expanduser().resolve()
    if not backup.is_dir() or backup.is_symlink():
        return {"ok": False, "path": str(backup), "status": "missing", "issues": [{"code": "BACKUP_NOT_FOUND", "message": "The selected backup directory was not found."}]}
    result = verify_backup(backup)
    result["path"] = str(backup)
    return result


def validate_active_data_root() -> Dict[str, Any]:
    return audit_data_root().to_dict()


def safe_repair_active_data_root() -> Dict[str, Any]:
    if DataRootManager.is_read_only():
        raise DataRootReadOnlyError()
    return safe_repair_data_root()


def _target_is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _prepare_new_destination(target: Path) -> bool:
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise DataRootDestinationConflictError(f"Destination '{target}' is not a safe directory.")
        if any(target.iterdir()):
            raise DataRootDestinationConflictError(
                f"Destination '{target}' is not empty. Use Existing Data Root instead if it contains data."
            )
        return True
    return False


def _staging_path(target: Path, operation: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.parent / f".dr-{operation[0]}-{uuid.uuid4().hex[:8]}"


def _publish(staging: Path, target: Path, target_was_empty: bool) -> None:
    removed_empty = False
    try:
        if target_was_empty:
            target.rmdir()
            removed_empty = True
        staging.rename(target)
    except Exception:
        if removed_empty and not target.exists():
            target.mkdir()
        raise


def _clear_root_bound_state() -> None:
    from ..domain.family.engine import rebind_active_root
    from ..domain.mutations.history import clear_mutation_history

    clear_mutation_history()
    rebind_active_root()


def _validate_application_model(root: Path) -> None:
    from ..model import load_model, validate_model

    validate_model(load_model(DataRootManager.get_database_path(root)))


def _create_initial_owner(root: Path, owner_name: str, owner_gender: str | None) -> str:
    from ..domain.canonical.ids import generate_canonical_person_id
    from ..domain.canonical.template import initialize_person_folder
    from .people import _next_person_id, _slugify

    name = str(owner_name).strip()
    if not name:
        raise DataRootInvalidError("Your name is required.", detail={"code": "OWNER_NAME_REQUIRED"})
    if owner_gender not in (None, "male", "female", "unknown"):
        raise DataRootInvalidError("Unsupported gender value.", detail={"code": "OWNER_GENDER_INVALID"})
    connection = db.get_connection(DataRootManager.get_database_path(root))
    try:
        connection.execute("BEGIN")
        canonical = db.is_canonical_connection(connection)
        if canonical:
            owner_id = generate_canonical_person_id(name)
            now = db.utc_now()
            connection.execute(
                """
                INSERT INTO people
                  (id, name, display_order, gender, category, created_at, updated_at)
                VALUES (?, ?, 0, ?, 'Me', ?, ?)
                """,
                (owner_id, name, owner_gender, now, now),
            )
        else:
            owner_id = _next_person_id(connection, _slugify(name))
            connection.execute(
                "INSERT INTO people (id, name, display_order, gender) VALUES (?, ?, 0, ?)",
                (owner_id, name, owner_gender),
            )
        connection.execute(
            "INSERT INTO person_groups (person_id, group_id, is_primary) VALUES (?, 'family', 1)",
            (owner_id,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('focus_person', ?)",
            (owner_id,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('title', ?)",
            (config.APP_NAME,),
        )
        connection.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('revision', '1')")
        if canonical:
            initialize_person_folder(
                root / "People" / "Me" / owner_id,
                owner_id,
                name,
                primary_category="Me",
                gender=owner_gender,
            )
        else:
            db.ensure_journal(connection, owner_id, root=root)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    (DataRootManager.get_config_dir(root) / "state.json").write_text(
        json.dumps({"perspective_person_id": owner_id}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return owner_id


def initialize_new_data_root(target_path: str, owner_name: str, owner_gender: str | None = None) -> Dict[str, Any]:
    """Build, validate, publish, then activate one genuinely new Data Root."""
    target = Path(target_path).expanduser().resolve()
    DataRootManager.assert_private_root(target)
    target_was_empty = _prepare_new_destination(target)
    staging = _staging_path(target, "initialize")
    published = False
    owner_id = ""
    with MaintenanceLockContext(f"INITIALIZE_DATA_ROOT:{target.name}"):
        try:
            DataRootManager.ensure_structure(staging, create=True, canonical=True)
            db.initialize_database(DataRootManager.get_database_path(staging))
            owner_id = _create_initial_owner(staging, owner_name, owner_gender)
            health = audit_data_root(staging)
            if _state_for_health(health) is not DataRootState.HEALTHY:
                raise DataRootInvalidError("New Data Root failed validation.", detail=health.to_dict())
            _validate_application_model(staging)
            _publish(staging, target, target_was_empty)
            published = True
            try:
                DataRootManager.set_active_root_pointer(target)
            except Exception as exc:
                raise DataRootError(
                    "The new Data Root is complete, but its location could not be activated.",
                    code="BOOTSTRAP_UPDATE_FAILED",
                    detail={"created_root": str(target)},
                ) from exc
            _clear_root_bound_state()
        except Exception:
            if not published:
                remove_tree(staging, ignore_errors=True)
            raise
    return {"ok": True, "active_root": str(target), "owner_id": owner_id, "health": audit_data_root(target).to_dict()}


def switch_data_root(target_path: str) -> Dict[str, Any]:
    target = Path(target_path).expanduser().resolve()
    DataRootManager.assert_private_root(target)
    current = DataRootManager.bootstrap_status().get("active_root")
    if isinstance(current, Path) and target == current:
        return {"ok": True, "active_root": str(current), "unchanged": True, "candidate": inspect_data_root(str(current))}
    candidate = inspect_data_root(str(target))
    if not candidate["can_switch"]:
        issue_code = candidate["issues"][0].get("code", "CANDIDATE_BLOCKED") if candidate["issues"] else "CANDIDATE_BLOCKED"
        raise DataRootInvalidError(
            "The selected Data Root is not safe to use.",
            detail={"code": issue_code, "candidate": candidate},
        )
    with MaintenanceLockContext(f"SWITCH_DATA_ROOT:{target.name}"):
        DataRootManager.set_active_root_pointer(target)
        _clear_root_bound_state()
    return {"ok": True, "active_root": str(target), "unchanged": False, "candidate": candidate}


def _is_transient(relative: Path) -> bool:
    name = relative.name
    transient_prefixes = (".backup_staging_", ".restore_staging_", ".restore_rollback_", ".raw_move_staging_", ".bootstrap-", ".journal-")
    return (
        "__pycache__" in relative.parts
        or name.endswith((".tmp", "-wal", "-shm"))
        or any(part.startswith(transient_prefixes) for part in relative.parts)
    )


def _sha256_stream(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link_like(path: Path) -> bool:
    try:
        data = path.lstat()
    except OSError:
        return False
    attributes = int(getattr(data, "st_file_attributes", 0) or 0)
    return path.is_symlink() or bool(attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _walk_runtime_files(root: Path, payload: Path) -> list[Path]:
    if _is_link_like(payload):
        raise DataRootInvalidError(f"Runtime payload contains an unsafe link: {payload.relative_to(root).as_posix()}")
    if payload.is_file():
        return [payload]
    files: list[Path] = []
    stack = [payload]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda value: value.name.casefold()):
                item = Path(entry.path)
                relative = item.relative_to(root)
                if _is_transient(relative):
                    continue
                if entry.is_symlink() or _is_link_like(item):
                    raise DataRootInvalidError(f"Runtime payload contains an unsafe link: {relative.as_posix()}")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(item)
                elif entry.is_file(follow_symlinks=False):
                    files.append(item)
    return sorted(files, key=lambda value: value.as_posix())


def _runtime_payloads(root: Path) -> list[Path]:
    """Visit case aliases once on Windows while retaining distinct POSIX roots."""
    payloads: list[Path] = []
    native_root = native_io_path(root)
    for name in _RUNTIME_NAMES:
        candidate = native_root / name
        if _is_link_like(candidate):
            raise DataRootInvalidError("Runtime payload contains an unsafe link.")
        if not candidate.exists():
            continue
        if any(os.path.samefile(candidate, existing) for existing in payloads):
            continue
        payloads.append(candidate)
    return payloads


def _runtime_inventory(root: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    scan_root = native_io_path(root)
    for payload in _runtime_payloads(root):
        for item in _walk_runtime_files(scan_root, payload):
            relative = item.relative_to(scan_root)
            if _is_transient(relative):
                continue
            rows.append(
                {
                    "path": relative.as_posix(),
                    "size": item.stat().st_size,
                    "sha256": _sha256_stream(item),
                }
            )
    return rows


def _runtime_directories(root: Path) -> list[str]:
    """Include empty canonical directories in relocation parity."""
    found: list[str] = []
    native_root = native_io_path(root)
    for payload in _runtime_payloads(root):
        if payload.is_file():
            continue
        if _is_link_like(payload):
            raise DataRootInvalidError("Runtime payload contains an unsafe link.")
        stack = [payload]
        while stack:
            directory = stack.pop()
            relative = directory.relative_to(native_root)
            if _is_transient(relative):
                continue
            found.append(relative.as_posix())
            for child in directory.iterdir():
                if _is_link_like(child):
                    raise DataRootInvalidError("Runtime payload contains an unsafe link.")
                if child.is_dir():
                    stack.append(child)
    return sorted(found)


def _copy_runtime_payload(source: Path, destination: Path) -> None:
    native_destination = native_io_path(destination)
    native_source = native_io_path(source)
    native_destination.mkdir(parents=True, exist_ok=False)
    for relative in _runtime_directories(source):
        (native_destination / Path(relative)).mkdir(parents=True, exist_ok=True)
    for row in _runtime_inventory(source):
        relative = Path(row["path"])
        target = native_destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(native_source / relative, target)


def _check_raw_move_relocation_state(active_root: Path) -> None:
    """Allow only verified retained copies owned by completed Raw moves."""
    quarantine = active_root / ".mosaic-quarantine" / "raw-moves"
    connection = db.get_connection(DataRootManager.get_database_path(active_root))
    try:
        operations = connection.execute(
            "SELECT op.id, op.status, op.error_message, op.expected_sha256, "
            "op.destination_relative_path, item.processing_state "
            "FROM raw_move_operations op JOIN raw_items item ON item.id=op.raw_item_id"
        ).fetchall()
    finally:
        connection.close()
    if any(row["status"] in {"PREPARED", "DESTINATION_VERIFIED"} for row in operations):
        raise DataRootInvalidError(
            "A pending Raw move blocks relocation; recover or review it first.",
            detail={"code": "RAW_MOVE_PENDING"},
        )
    allowed = {
        f"{row['id']}/payload": row for row in operations
        if row["status"] == "COMPLETED" and row["error_message"] == "CLEANUP_PENDING"
        and row["processing_state"] == "MOVED"
    }
    found: set[str] = set()
    if quarantine.exists():
        if _is_link_like(quarantine) or not quarantine.is_dir():
            raise DataRootInvalidError("Unsafe Raw quarantine blocks relocation.", detail={"code": "RAW_QUARANTINE_PENDING"})
        for entry in quarantine.rglob("*"):
            if _is_link_like(entry):
                raise DataRootInvalidError("Unsafe Raw quarantine blocks relocation.", detail={"code": "RAW_QUARANTINE_PENDING"})
            if entry.is_dir():
                continue
            relative = entry.relative_to(quarantine).as_posix()
            row = allowed.get(relative)
            if row is None or not entry.is_file() or _sha256_stream(entry) != row["expected_sha256"]:
                raise DataRootInvalidError("Unverified Raw quarantine blocks relocation.", detail={"code": "RAW_QUARANTINE_PENDING"})
            destination = _destination_path_for_existing(active_root, row["destination_relative_path"])
            if not destination.is_file() or _is_link_like(destination) or _sha256_stream(destination) != row["expected_sha256"]:
                raise DataRootInvalidError("Unverified Raw destination blocks relocation.", detail={"code": "RAW_QUARANTINE_PENDING"})
            found.add(relative)
    if found != set(allowed):
        raise DataRootInvalidError("Missing retained Raw quarantine blocks relocation.", detail={"code": "RAW_QUARANTINE_PENDING"})


def move_data_root(destination_path: str) -> Dict[str, Any]:
    active_root = DataRootManager.resolve_active_root()
    destination = Path(destination_path).expanduser().resolve()
    DataRootManager.assert_private_root(destination)
    if _target_is_within(destination, active_root) or _target_is_within(active_root, destination):
        raise DataRootDestinationConflictError("The move destination and active Data Root cannot contain one another.")
    target_was_empty = _prepare_new_destination(destination)
    staging = _staging_path(destination, "move")
    published = False
    with _locked(active_root), MaintenanceLockContext(f"MOVE_DATA_ROOT:{destination.name}"):
        _check_raw_move_relocation_state(active_root)
        # Reject unsafe runtime links before backup creation traverses the root.
        _runtime_inventory(active_root)
        _runtime_directories(active_root)
        safety_backup = create_backup(
            label=f"Before moving to {destination.name}",
            category=BackupCategory.SAFETY,
            safety_reason=SafetyReason.PRE_ORGANIZATION,
            root=active_root,
            _maintenance_held=True,
        )
        expected = _runtime_inventory(active_root)
        expected_directories = _runtime_directories(active_root)
        try:
            _copy_runtime_payload(active_root, staging)
            actual = _runtime_inventory(staging)
            current_source = _runtime_inventory(active_root)
            if (current_source != expected or actual != expected
                    or _runtime_directories(staging) != expected_directories):
                raise DataRootInvalidError("Moved runtime payload failed exact inventory verification.")
            health = audit_data_root(staging)
            if _state_for_health(health) not in {DataRootState.HEALTHY, DataRootState.READ_ONLY}:
                raise DataRootInvalidError("Moved Data Root failed health validation.", detail=health.to_dict())
            _validate_application_model(staging)
            _publish(staging, destination, target_was_empty)
            published = True
            try:
                DataRootManager.set_active_root_pointer(destination)
            except Exception as exc:
                raise DataRootError(
                    "The verified copy is complete, but it could not be activated. The old location remains active.",
                    code="BOOTSTRAP_UPDATE_FAILED",
                    detail={"created_root": str(destination)},
                ) from exc
            _clear_root_bound_state()
        except Exception:
            if not published:
                remove_tree(staging, ignore_errors=True)
            raise
    return {
        "ok": True,
        "previous_root": str(active_root),
        "new_root": str(destination),
        "old_root_retained": True,
        "safety_backup_id": safety_backup["id"],
        "inventory_files": len(expected),
        "health": audit_data_root(destination).to_dict(),
    }


def restore_backup_to_data_root(backup_path: str, target_root: str) -> Dict[str, Any]:
    backup = Path(backup_path).expanduser().resolve()
    destination = Path(target_root).expanduser().resolve()
    DataRootManager.assert_private_root(destination)
    if not backup.is_dir() or backup.is_symlink():
        raise DataRootNotFoundError(f"Backup path '{backup}' is not a safe directory.")
    if _target_is_within(destination, backup) or _target_is_within(backup, destination):
        raise DataRootDestinationConflictError("Backup source and destination cannot contain one another.")
    verification = verify_backup(backup)
    if not verification["ok"]:
        raise DataRootInvalidError("Backup verification failed.", detail=verification)
    target_was_empty = _prepare_new_destination(destination)
    staging = _staging_path(destination, "restore")
    published = False
    with MaintenanceLockContext(f"RESTORE_TO_NEW_ROOT:{destination.name}"):
        try:
            DataRootManager.ensure_structure(staging, create=True)
            result = restore_backup(
                backup,
                confirmation_token="RESTORE",
                root=staging,
                _allow_path=True,
                _require_safety_backup=False,
                _maintenance_held=True,
            )
            health = audit_data_root(staging)
            if _state_for_health(health) is not DataRootState.HEALTHY:
                raise DataRootInvalidError("Restored Data Root failed validation.", detail=health.to_dict())
            _validate_application_model(staging)
            _publish(staging, destination, target_was_empty)
            published = True
            try:
                DataRootManager.set_active_root_pointer(destination)
            except Exception as exc:
                raise DataRootError(
                    "The restored Data Root is complete, but it could not be activated.",
                    code="BOOTSTRAP_UPDATE_FAILED",
                    detail={"created_root": str(destination)},
                ) from exc
            _clear_root_bound_state()
        except Exception:
            if not published:
                remove_tree(staging, ignore_errors=True)
            raise
    return {
        "ok": True,
        "active_root": str(destination),
        "restore_result": result,
        "verification": verification,
        "health": audit_data_root(destination).to_dict(),
    }
