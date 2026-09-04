"""The legacy builder and its regression audits must keep passing on the
real database, and the new model loader must agree with it exactly."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CODEBASE = Path(__file__).resolve().parents[2]
BUILDER = CODEBASE / "Scripts" / "build_family.py"
DB_PATH = REPO / "Database" / "Main" / "family.db"


def _run_builder(*args):
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        cwd=str(CODEBASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def test_legacy_check_passes():
    result = _run_builder("--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Valid: 35 people, 44 parent-child facts, 12 marriages." in result.stdout
    assert "arbitrary-perspective checks PASS" in result.stdout


def test_model_loader_parity_with_builder():
    from app.backend.domain.family import engine as build_family

    from app.backend.model import load_model

    builder_model = build_family.read_sqlite_model(DB_PATH)
    app_model = load_model(DB_PATH)
    assert app_model == builder_model


def test_engine_pair_matches_legacy_viewer_labels():
    """Refactored grouping must never drop an engine label."""
    from app.backend.domain.family import engine as build_family

    from app.backend.services.relationship import get_relationship

    data = build_family.read_sqlite_model(DB_PATH)
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
