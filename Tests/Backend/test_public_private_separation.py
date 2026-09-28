"""Public checkout and private Data Root boundary regressions."""

import json
import subprocess
from pathlib import Path

import pytest

from app.backend.data_root.errors import DataRootInvalidError
from app.backend.data_root.manager import DataRootManager
from app.backend.services.data_root import get_data_root_status
from app.backend.services.data_root import move_data_root
from app.backend.services.data_root import initialize_new_data_root, switch_data_root, restore_backup_to_data_root


REPO = Path(__file__).resolve().parents[2]


def test_checkout_and_its_children_are_rejected_but_sibling_is_allowed():
    for candidate in (REPO, REPO / "Database", REPO / "Mosaic - Local Private Data"):
        with pytest.raises(DataRootInvalidError):
            DataRootManager.assert_private_root(candidate)
    DataRootManager.assert_private_root(REPO.parent / "Mosaic - Local Private Data")


def test_repository_root_contains_no_private_payload_and_is_the_git_root():
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert Path(git_root).resolve() == REPO
    for private_name in (
        "Database",
        "People",
        "Backups",
        "Raw",
        "Media",
        ".mosaic-quarantine",
        "Mosaic - Local Private Data",
        "Local Private Data",
    ):
        assert not (REPO / private_name).exists(), private_name


def test_source_checkout_is_never_bootstrap_fallback(tmp_path, monkeypatch):
    pointer = tmp_path / "missing-bootstrap.json"
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(pointer))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    DataRootManager.set_override_root(None)
    status = get_data_root_status()
    assert status["state"] == "UNCONFIGURED"
    assert status["active_root"] is None


def test_checkout_pointer_is_invalid_and_external_synthetic_root_is_healthy(tmp_path, monkeypatch, _isolated_user_bootstrap):
    pointer = tmp_path / "bootstrap.json"
    pointer.write_text(json.dumps({"active_root": str(REPO)}), encoding="utf-8")
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(pointer))
    DataRootManager.set_override_root(None)
    assert get_data_root_status()["state"] == "INVALID"
    external = _isolated_user_bootstrap
    DataRootManager.set_active_root_pointer(external)
    status = get_data_root_status()
    assert status["state"] == "HEALTHY"
    assert Path(status["active_root"]) == external


def test_symlink_alias_to_checkout_is_rejected(tmp_path):
    alias = tmp_path / "checkout-alias"
    try:
        alias.symlink_to(REPO, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Creating a directory symlink is unavailable here")
    with pytest.raises(DataRootInvalidError):
        DataRootManager.assert_private_root(alias)


def test_relocation_blocks_quarantined_payload(tmp_path, _isolated_user_bootstrap):
    root = _isolated_user_bootstrap
    # Build the path without relying on a real Raw approval or personal data.
    claimed = root / ".mosaic-quarantine" / "raw-moves" / ("rawmove_" + "0" * 32) / "payload"
    claimed.parent.mkdir(parents=True)
    claimed.write_bytes(b"synthetic retained source")
    with pytest.raises(DataRootInvalidError) as error:
        move_data_root(str(tmp_path / "new-private-root"))
    assert error.value.detail["code"] == "RAW_QUARANTINE_PENDING"
    assert claimed.read_bytes() == b"synthetic retained source"


def test_create_existing_and_restore_use_external_roots(tmp_path, _isolated_user_bootstrap):
    original = _isolated_user_bootstrap
    created_path = tmp_path / "created-private-root"
    created = initialize_new_data_root(str(created_path), "Tessa Rowan", "female")
    assert created["ok"] is True
    assert (created_path / "Database" / "relationships.db").is_file()
    assert DataRootManager.bootstrap_status()["active_root"] == created_path
    switched = switch_data_root(str(original))
    assert switched["ok"] is True
    assert DataRootManager.bootstrap_status()["active_root"] == original
    from app.backend.domain.backups import create_backup

    backup = create_backup("Synthetic restoration sample", root=original)
    restored_path = tmp_path / "restored-private-root"
    restored = restore_backup_to_data_root(backup["path"], str(restored_path))
    assert restored["ok"] is True
    assert DataRootManager.bootstrap_status()["active_root"] == restored_path
    assert (original / "Database" / "relationships.db").is_file()


def test_phase12_history_and_raw_resolve_beneath_private_root(_isolated_user_bootstrap):
    from app.backend.domain import raw_intake

    root = _isolated_user_bootstrap
    result = raw_intake.scan_raw()
    assert result["summary"]["items"] >= 1
    assert raw_intake.history_path(root).is_file()
    assert raw_intake.history_path(root).is_relative_to(root)
    assert raw_intake.raw_directory(root).is_relative_to(root)


def test_verified_relocation_keeps_old_synthetic_root(tmp_path, _isolated_user_bootstrap):
    original = _isolated_user_bootstrap
    (original / "Media").mkdir()
    (original / "Media" / "synthetic-image.txt").write_text("fictional media placeholder", encoding="utf-8")
    target = tmp_path / "relocated-private-root"
    result = move_data_root(str(target))
    assert result["ok"] is True and result["old_root_retained"] is True
    assert (original / "Media" / "synthetic-image.txt").is_file()
    assert (target / "Media" / "synthetic-image.txt").read_text(encoding="utf-8") == "fictional media placeholder"
    assert DataRootManager.bootstrap_status()["active_root"] == target
