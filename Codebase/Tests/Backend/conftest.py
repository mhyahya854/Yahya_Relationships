"""Test fixtures. Every test runs against a fresh copy of family.db under a
temporary data root so the real database is never mutated by tests."""

import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
CODEBASE = Path(__file__).resolve().parents[2]
SCRIPTS = CODEBASE / "Scripts"

for path in (CODEBASE, SCRIPTS, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Fresh People Relationships data root backed by a copy of family.db."""
    from app.backend import config, db as db_module
    from app.backend.data_root import DataRootManager

    db_source = DataRootManager.get_database_path(REPO)
    db_target = tmp_path / "Database" / "Main" / "family.db"
    db_target.parent.mkdir(parents=True, exist_ok=True)
    if db_source.exists():
        shutil.copy2(db_source, db_target)

    def root_for(*parts: str) -> Path:
        path = tmp_path.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    people_src = DataRootManager.get_people_dir(REPO)
    people_target = tmp_path / "Database" / "People"
    people_target.parent.mkdir(parents=True, exist_ok=True)
    if people_src.exists():
        shutil.copytree(people_src, people_target, dirs_exist_ok=True)
    else:
        root_for("Database", "People")

    root_for("Database", "Config")
    root_for("Backups")
    root_for("Database", "Exports")

    DataRootManager.set_override_root(tmp_path)
    db_module.migrate(db_target)

    # Legacy path fallbacks for test compatibility
    db_root = tmp_path / "family.db"
    if not db_root.exists() and db_target.exists():
        shutil.copy2(db_target, db_root)

    legacy_people = tmp_path / "people"
    if not legacy_people.exists() and people_target.exists():
        shutil.copytree(people_target, legacy_people, dirs_exist_ok=True)

    legacy_backups = tmp_path / "backups"
    if not legacy_backups.exists():
        (tmp_path / "Backups").mkdir(parents=True, exist_ok=True)

    legacy_config = tmp_path / "config"
    if not legacy_config.exists():
        (tmp_path / "Database" / "Config").mkdir(parents=True, exist_ok=True)

    yield tmp_path
    DataRootManager.set_override_root(None)


@pytest.fixture()
def client(isolated):
    from fastapi.testclient import TestClient

    from app.backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client
