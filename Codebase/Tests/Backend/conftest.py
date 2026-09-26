"""Isolated, fictional Data Roots for every backend test."""

import json
import sys
from pathlib import Path

import pytest

CODEBASE = Path(__file__).resolve().parents[2]
SCRIPTS = CODEBASE / "Scripts"

for path in (CODEBASE, CODEBASE / "App", SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from Tests.synthetic_mosaic import build as build_synthetic_root


@pytest.fixture(autouse=True)
def _isolated_user_bootstrap(tmp_path, monkeypatch):
    """Never read the real user pointer or a checkout database during tests."""
    root = tmp_path / "synthetic-data-root"
    build_synthetic_root(root)
    bootstrap = tmp_path / "user-config" / "bootstrap.json"
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(json.dumps({"active_root": str(root), "updated_at": "synthetic-test"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(bootstrap))
    monkeypatch.delenv("PEOPLE_RELATIONSHIPS_ROOT", raising=False)
    from app.backend.data_root import DataRootManager

    DataRootManager.set_override_root(None)
    from app.backend.domain.family import engine

    engine.rebind_active_root()
    yield root
    DataRootManager.set_override_root(None)
    monkeypatch.setenv("PEOPLE_RELATIONSHIPS_BOOTSTRAP", str(bootstrap))
    engine.rebind_active_root()


@pytest.fixture()
def isolated(_isolated_user_bootstrap):
    from app.backend.data_root import DataRootManager
    from app.backend.domain.mutations.history import _MUTATION_STACK

    DataRootManager.set_override_root(_isolated_user_bootstrap)
    _MUTATION_STACK.clear()
    yield _isolated_user_bootstrap
    _MUTATION_STACK.clear()
    DataRootManager.set_override_root(None)


@pytest.fixture()
def client(isolated):
    from fastapi.testclient import TestClient
    from app.backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client
