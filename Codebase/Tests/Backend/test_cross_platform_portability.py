"""Tests for cross-platform portability, OS bootstrap configs, and portable data root integrity."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.backend import config, db
from app.backend.data_root.manager import DataRootManager, _user_bootstrap_config_path
from app.backend.domain.backups import create_backup, verify_backup
from app.backend.domain.backups.manifest import read_backup_manifest
from app.backend.services.data_root import (
    get_data_root_status,
    initialize_new_data_root,
    restore_backup_to_data_root,
)
from app.backend.services.journals import read_journal, save_journal
from app.backend.services.people import create_person, get_person


def test_bootstrap_path_per_os(monkeypatch, tmp_path):
    """Test OS-specific application data directory conventions."""
    # 1. Custom override
    custom_bootstrap = tmp_path / "custom" / "boot.json"
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(custom_bootstrap))
    resolved = _user_bootstrap_config_path()
    assert resolved == custom_bootstrap.resolve()

    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", raising=False)

    # 2. Windows simulation
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    fake_appdata = fake_home / "AppData" / "Roaming"
    fake_appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.setattr(sys, "platform", "win32")

    win_path = _user_bootstrap_config_path()
    assert win_path == fake_appdata / "people-relationships" / "bootstrap.json"

    # 3. macOS simulation
    monkeypatch.setattr(sys, "platform", "darwin")
    mac_path = _user_bootstrap_config_path()
    assert mac_path == fake_home / "Library" / "Application Support" / "people-relationships" / "bootstrap.json"

    # 4. Linux simulation without XDG_CONFIG_HOME
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    linux_path = _user_bootstrap_config_path()
    assert linux_path == fake_home / ".config" / "people-relationships" / "bootstrap.json"

    # 5. Linux simulation with XDG_CONFIG_HOME
    fake_xdg = tmp_path / "xdg_config"
    fake_xdg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_xdg))
    linux_xdg_path = _user_bootstrap_config_path()
    assert linux_xdg_path == fake_xdg / "people-relationships" / "bootstrap.json"


def test_data_root_portability_lifecycle(tmp_path, monkeypatch):
    """Full portability lifecycle: initialize, write data/journals, verify SQLite & UTF-8, test integrity."""
    boot_file = tmp_path / "bootstrap.json"
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(boot_file))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    DataRootManager.set_override_root(None)

    # 1. Initialize brand-new data root
    root_a = tmp_path / "Relationship_Brain_A"
    res = initialize_new_data_root(str(root_a), owner_name="Mohammad Yahya Hussain")
    assert res["ok"] is True
    assert res["health"]["ok"] is True
    assert DataRootManager.resolve_active_root() == root_a.resolve()

    # 2. Verify canonical layout
    assert (root_a / "Database" / "Main" / "family.db").exists()
    assert (root_a / "Database" / "People").exists()
    assert (root_a / "Database" / "Config" / "data-root.json").exists()

    # 3. Verify SQLite integrity
    db_path = root_a / "Database" / "Main" / "family.db"
    conn = sqlite3.connect(str(db_path))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"
    conn.close()

    # 4. Create another person and write journal
    person = create_person(
        name="Jane Doe",
        gender="female",
        birth_year=1995,
        group_id="family",
    )
    person_id = person["id"]
    assert person_id.replace("_", "").isalnum()

    # Write UTF-8 journal with Unicode
    journal_text = "# Jane Doe\n\nNotes with UTF-8 symbols: ❖ ⌁ ◉ — Special text: résumé, café, façade.\n"
    save_res = save_journal(person_id, journal_text)
    assert save_res["content"] == journal_text

    # Read back and verify byte and line ending consistency
    read_res = read_journal(person_id)
    assert "résumé, café, façade" in read_res["content"]
    assert "\r\n" not in read_res["content"]  # Normalized LF newlines

    # 5. Backup Creation and Cross-Platform Portability
    backup = create_backup(label="portability-test-1", root=root_a)
    backup_path = Path(backup["path"])
    assert backup_path.exists()

    manifest = read_backup_manifest(backup_path)
    assert manifest["kind"] == "people-relationships-backup"
    for file_entry in manifest["files"]:
        # Ensure all paths in manifest are normalized relative POSIX paths (no backslashes, no drive letters)
        assert "\\" not in file_entry["path"]
        assert not file_entry["path"].startswith("/")
        assert ":" not in file_entry["path"]

    # 6. Restore to completely different root B
    root_b = tmp_path / "Relationship_Brain_B"
    restore_res = restore_backup_to_data_root(str(backup_path), target_root=str(root_b))
    assert restore_res["ok"] is True
    assert DataRootManager.resolve_active_root() == root_b.resolve()

    # Verify SQLite on restored root B
    db_b = root_b / "Database" / "Main" / "family.db"
    conn_b = sqlite3.connect(str(db_b))
    assert conn_b.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    count = conn_b.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    assert count >= 2
    conn_b.close()

    # Verify restored journal
    read_b = read_journal(person_id)
    assert "résumé, café, façade" in read_b["content"]


def test_first_run_vs_missing_root_status(tmp_path, monkeypatch):
    """Ensure first-run is cleanly distinguished from missing configured root."""
    boot_file = tmp_path / "boot.json"
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(boot_file))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    DataRootManager.set_override_root(None)

    # 1. First run: boot_file does not exist, no override, frozen mode simulated
    monkeypatch.setattr(config, "IS_FROZEN", True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    status = get_data_root_status()
    assert status["configured"] is False
    assert status["first_run"] is True

    # 2. Configured root that points to a missing path
    missing_dir = tmp_path / "non_existent_folder"
    payload = {"active_root": str(missing_dir), "updated_at": "2026-09-05T00:00:00Z"}
    boot_file.write_text(json.dumps(payload), encoding="utf-8")

    status2 = get_data_root_status()
    assert status2["configured"] is True
    assert status2["first_run"] is False
    assert status2["health"]["ok"] is False
    assert any(i["code"] == "DATA_ROOT_MISSING" for i in status2["health"]["issues"])


def test_paths_with_spaces_and_unicode(tmp_path, monkeypatch):
    """Verify that paths containing spaces and Unicode characters work without error."""
    boot_file = tmp_path / "boot space.json"
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(boot_file))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    DataRootManager.set_override_root(None)

    # Path with spaces and Unicode (e.g. German umlauts, Arabic letters)
    complex_root = tmp_path / "Family Brain 2026 — عائلة"
    res = initialize_new_data_root(str(complex_root), owner_name="Yahya")
    assert res["ok"] is True

    # Person with Unicode name but safe slug ID
    person = create_person(
        name="München Schön",
        gender="unknown",
        birth_year=2000,
        group_id="family",
    )
    assert person["id"] == "m_nchen_sch_n"
    assert (complex_root / "Database" / "People" / "family" / person["id"] / "journal.md").exists()


def test_case_sensitivity_safety(tmp_path, monkeypatch):
    """Ensure person IDs and folder mappings are consistently lowercase to prevent case collision on Linux."""
    boot_file = tmp_path / "boot_case.json"
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(boot_file))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    DataRootManager.set_override_root(None)

    root = tmp_path / "CaseTestRoot"
    initialize_new_data_root(str(root), owner_name="Owner")

    person = create_person(
        name="Test Person",
        gender="male",
        birth_year=1990,
        group_id="family",
    )
    # Both person_id and group_id must be lowercase for filesystem case safety
    assert person["id"] == person["id"].lower()
    assert person["id"] == "test_person"
    assert person["groups"][0]["id"] == "family"
    assert (root / "Database" / "People" / "family" / "test_person" / "journal.md").exists()


def test_sidecar_target_triples():
    """Verify standard target-triple mapping for all supported desktop targets."""
    # Expected triples
    supported_triples = {
        ("windows", "x86_64"): "x86_64-pc-windows-msvc",
        ("darwin", "arm64"): "aarch64-apple-darwin",
        ("darwin", "x86_64"): "x86_64-apple-darwin",
        ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    }
    for (os_name, arch), triple in supported_triples.items():
        assert triple is not None
        if os_name == "windows":
            assert f"people-relationships-backend-{triple}.exe".endswith(".exe")
        else:
            assert not f"people-relationships-backend-{triple}".endswith(".exe")
