"""Test fixtures that isolate writes and never use the real OS bootstrap.

Frozen read-only tests retain their established source-data fixture; tests that
write request a fresh copied Data Root through ``isolated``.
"""

import json
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


@pytest.fixture(autouse=True)
def _isolated_user_bootstrap(tmp_path, monkeypatch):
    """Redirect the user-level bootstrap pointer file to a per-test temp path.

    The real ``%APPDATA%/people-relationships/bootstrap.json`` must never be
    read or written by any test.  The temporary pointer preserves the historical
    source-data fixture for read-only frozen tests; tests that write request the
    ``isolated`` fixture, and Phase-8 bootstrap tests replace this pointer with
    their own unconfigured temporary location.
    """
    bootstrap = tmp_path / "user-config" / "bootstrap.json"
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(
        json.dumps({"active_root": str(REPO.resolve()), "updated_at": "test-fixture"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PEOPLE_RELATIONSHIPS_BOOTSTRAP",
        str(bootstrap),
    )
    yield
    from app.backend.data_root import DataRootManager

    DataRootManager.set_override_root(None)
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(bootstrap))
    engine = sys.modules.get("app.backend.domain.family.engine")
    if engine is not None:
        engine.rebind_active_root()


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

    from app.backend.domain.mutations.history import _MUTATION_STACK
    _MUTATION_STACK.clear()

    yield tmp_path
    _MUTATION_STACK.clear()
    DataRootManager.set_override_root(None)


@pytest.fixture()
def client(isolated):
    from fastapi.testclient import TestClient

    from app.backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client
