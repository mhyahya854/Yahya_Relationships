"""Project root / path resolution must be identical from any cwd."""

from pathlib import Path

import pytest

from app.backend import config
from app.backend.data_root.manager import DataRootManager, _repo_root

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CODEBASE_ROOT = PROJECT_ROOT / "Codebase"


@pytest.mark.parametrize("cwd", ["/", "codebase", "tmp"])
def test_config_roots_are_cwd_independent(tmp_path, monkeypatch, cwd):
    if cwd == "/":
        target = Path("/").resolve()
    elif cwd == "codebase":
        target = CODEBASE_ROOT
    else:
        target = tmp_path
    monkeypatch.chdir(target)

    assert config.PROJECT_ROOT == PROJECT_ROOT
    assert config.CODEBASE_ROOT == CODEBASE_ROOT
    assert config.DOCUMENTATION_ROOT == PROJECT_ROOT / "Documentation"
    assert config.VENDOR_DIR == CODEBASE_ROOT / "Resources" / "Vendor"
    assert config.SCRIPTS_DIR == CODEBASE_ROOT / "Scripts"
    assert _repo_root() == PROJECT_ROOT


def test_explicit_root_getters_use_canonical_layout(tmp_path):
    root = tmp_path / "root"
    (root / "Database" / "Main").mkdir(parents=True)
    (root / "Database" / "Main" / "family.db").touch()
    (root / "Database" / "People").mkdir(parents=True)
    (root / "Database" / "Config").mkdir(parents=True)
    (root / "Database" / "Exports").mkdir(parents=True)
    (root / "Backups").mkdir(parents=True)

    assert (
        DataRootManager.get_database_path(root)
        == root / "Database" / "Main" / "family.db"
    )
    assert DataRootManager.get_people_dir(root) == root / "Database" / "People"
    assert DataRootManager.get_backups_dir(root) == root / "Backups"
    assert DataRootManager.get_config_dir(root) == root / "Database" / "Config"
    assert DataRootManager.get_exports_dir(root) == root / "Database" / "Exports"


def test_real_project_root_getters(tmp_path, monkeypatch):
    """The real project root resolves to the canonical layout from any cwd."""
    monkeypatch.chdir(tmp_path)
    root = PROJECT_ROOT
    assert (
        DataRootManager.get_database_path(root)
        == root / "Database" / "Main" / "family.db"
    )
    assert DataRootManager.get_people_dir(root) == root / "Database" / "People"
    assert DataRootManager.get_backups_dir(root) == root / "Backups"
    assert DataRootManager.get_config_dir(root) == root / "Database" / "Config"
    assert DataRootManager.get_exports_dir(root) == root / "Database" / "Exports"


def test_missing_configured_root_never_falls_back_or_creates_db(tmp_path, monkeypatch):
    """If bootstrap points to a missing or disconnected root:
    - It must resolve to that configured path, NEVER falling back to repo/codebase.
    - It must not create fallback directories.
    - It must not create an empty SQLite database at fallback or target.
    - Calling migrate() or ensure_structure() must refuse silently creating data.
    - audit_data_root() must report structured DATA_ROOT_MISSING.
    """
    import json
    from app.backend import db as db_module
    from app.backend.data_root.errors import DataRootNotFoundError
    from app.backend.data_root.validation import audit_data_root

    # Explicitly clear any override so resolution goes through bootstrap
    DataRootManager.set_override_root(None)

    missing_root = tmp_path / "NonExistentDrive" / "MissingDataRoot"
    bootstrap_file = tmp_path / "bootstrap.json"
    bootstrap_file.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_file.write_text(
        json.dumps({"active_root": str(missing_root)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(bootstrap_file))

    # 1. Resolve active root: must be the configured path, NOT fallback
    resolved = DataRootManager.resolve_active_root()
    assert resolved == missing_root.resolve()
    assert resolved != PROJECT_ROOT
    assert resolved != CODEBASE_ROOT
    assert not resolved.exists()
    assert DataRootManager.is_active_root_available() is False

    # 2. Refuses silent directory creation on missing root
    with pytest.raises(DataRootNotFoundError) as exc_info:
        DataRootManager.ensure_structure()
    assert exc_info.value.detail.get("code") == "DATA_ROOT_NOT_FOUND"

    # 3. Refuses silent database migration/creation on missing root
    with pytest.raises(DataRootNotFoundError):
        db_module.migrate()

    # 4. Audit reports structured missing root error
    health = audit_data_root(resolved)
    assert health.ok is False
    assert health.layout_mode == "missing"
    assert any(i.code == "DATA_ROOT_MISSING" for i in health.issues)

    # 5. Verify no accidental directories or databases were created anywhere
    assert not (CODEBASE_ROOT / "Database").exists()
    assert not (CODEBASE_ROOT / "family.db").exists()
    assert not missing_root.exists()


def test_disconnected_drive_simulation_and_api_health(tmp_path, monkeypatch):
    """Simulate a disconnected external drive (e.g. D:\\) configured as active root:
    - FastAPI /api/health must return structured DATA_ROOT_NOT_FOUND error.
    - No replacement database must be initialized or created.
    """
    import json
    from fastapi.testclient import TestClient
    from app.backend.api.main import app

    DataRootManager.set_override_root(None)

    disconnected_drive_root = Path("D:/DisconnectedDrive_Simulation_Test/People_Relationships")
    bootstrap_file = tmp_path / "bootstrap_disc.json"
    bootstrap_file.write_text(
        json.dumps({"active_root": str(disconnected_drive_root)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(bootstrap_file))

    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["status"] == "DATA_ROOT_NOT_FOUND"
        assert str(disconnected_drive_root) in data["data_root"]

    # Verify no database file created in Codebase
    assert not (CODEBASE_ROOT / "Database").exists()
    assert not (CODEBASE_ROOT / "family.db").exists()


def test_db_open_modes_existing_vs_initialize(tmp_path):
    """Distinguish OPEN_EXISTING from INITIALIZE_NEW explicitly."""
    from app.backend import db as db_module
    from app.backend.data_root.errors import DataRootNotFoundError

    missing_db = tmp_path / "uninitialized" / "family.db"

    # Default OPEN_EXISTING mode refuses to create
    with pytest.raises(DataRootNotFoundError):
        db_module.get_connection(missing_db, mode=db_module.DatabaseOpenMode.OPEN_EXISTING)

    with pytest.raises(DataRootNotFoundError):
        db_module.migrate(missing_db, mode=db_module.DatabaseOpenMode.OPEN_EXISTING)

    assert not missing_db.exists()

    # Explicit INITIALIZE_NEW mode creates and initializes schema
    db_module.initialize_database(missing_db)
    assert missing_db.exists()

    # Once created, OPEN_EXISTING succeeds
    conn = db_module.get_connection(missing_db, mode=db_module.DatabaseOpenMode.OPEN_EXISTING)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()

