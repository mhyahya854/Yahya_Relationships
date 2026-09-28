"""The legacy builder and model loader must agree on fictional fixture data."""

import os
import subprocess
import sys
from pathlib import Path

CODEBASE = Path(__file__).resolve().parents[2]
BUILDER = CODEBASE / "Scripts" / "build_family.py"


def _run_builder(root, *args):
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        cwd=str(CODEBASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        env={**os.environ, "PEOPLE_RELATIONSHIPS_ROOT": str(root)},
    )


def test_legacy_check_passes(isolated):
    result = _run_builder(isolated, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Valid: 15 people, 16 parent-child facts, 4 marriages." in result.stdout
    assert "arbitrary-perspective checks PASS" in result.stdout


def test_model_loader_parity_with_builder(isolated):
    from app.backend.domain.family import engine as build_family

    from app.backend.model import load_model

    db_path = isolated / "Database" / "relationships.db"
    builder_model = build_family.read_sqlite_model(db_path)
    app_model = load_model(db_path)
    assert app_model == builder_model


def test_engine_pair_matches_legacy_viewer_labels(isolated):
    """Refactored grouping must never drop an engine label."""
    from app.backend.domain.family import engine as build_family

    from app.backend.services.relationship import get_relationship

    data = build_family.read_sqlite_model(isolated / "Database" / "relationships.db")
    index = {p["id"]: p for p in data["people"]}
    for first in data["people"][:12]:
        for second in data["people"][:12]:
            legacy = build_family._viewer_pair(data, first["id"], second["id"], index)
            legacy_labels = {
                item["en"].lower()
                for item in legacy["main"] + legacy["additional"]
            }
            result = get_relationship(first["id"], second["id"])
            app_labels = {
                item["label_en"].lower()
                for item in result["primary"] + result["additional"]
            }
            assert app_labels == legacy_labels, (
                f"{first['id']} -> {second['id']}"
            )
