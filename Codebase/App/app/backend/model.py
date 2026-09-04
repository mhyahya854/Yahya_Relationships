"""Canonical family model loading and validation bridge.

The existing Python kinship engine inside ``build_family.py`` remains the
single canonical implementation for family facts, path derivation and
kinship auditing. The application never re-implements genealogy; it loads
the same structured model the legacy builder uses and calls the same
functions.
"""

import sqlite3
from pathlib import Path

from .domain.family import engine as build_family
from . import config, db


def load_model(db_path: Path | None = None) -> dict:
    """Read the family.db model exactly as the legacy builder sees it."""
    connection = db.get_connection(db_path)
    try:
        return _model_from_connection(connection)
    finally:
        connection.close()


def _model_from_connection(connection: sqlite3.Connection) -> dict:
    """Mirror build_family.read_sqlite_model over an open connection."""
    metadata = {}
    for row in connection.execute("SELECT key, value FROM metadata"):
        key, value = row["key"], row["value"]
        if key.startswith("_"):
            continue
        if key == "revision":
            metadata[key] = int(value)
        else:
            metadata[key] = value
    metadata["source_batches"] = [
        row["file_path"]
        for row in connection.execute("SELECT file_path FROM sources ORDER BY id")
    ]

    people = []
    for row in connection.execute("SELECT * FROM people ORDER BY display_order, id"):
        person = {
            "id": row["id"],
            "name": row["name"],
            "branch": row["branch"],
            "relation_en": row["legacy_relation_en"],
            "relation_ur": row["legacy_relation_ur"],
            "note_en": row["note_en"],
            "note_ur": row["note_ur"],
        }
        for key in ("birth_year", "gender", "marital_status", "photo_path"):
            if row[key] is not None:
                person[key] = row[key]
        aliases = [
            alias_row["alias"]
            for alias_row in connection.execute(
                """
                SELECT alias FROM aliases
                WHERE person_id = ? ORDER BY display_order
                """,
                (row["id"],),
            )
        ]
        if aliases:
            person["aliases"] = aliases
        people.append(person)

    parent_child = [
        {
            "parent": row["parent_id"],
            "child": row["child_id"],
            "role": row["role"],
            "kind": row["kind"],
        }
        for row in connection.execute("SELECT * FROM parent_child ORDER BY id")
    ]

    marriages = []
    for row in connection.execute("SELECT * FROM marriages ORDER BY display_order, id"):
        marriage = {
            "person1": row["spouse_a"],
            "person2": row["spouse_b"],
            "status": row["status"],
        }
        if row["year"] is not None:
            marriage["year"] = row["year"]
        if row["children_status"] is not None:
            marriage["children_status"] = row["children_status"]
        marriages.append(marriage)

    sibling_groups = []
    for row in connection.execute(
        "SELECT * FROM sibling_groups ORDER BY display_order, id"
    ):
        members = [
            member_row["person_id"]
            for member_row in connection.execute(
                """
                SELECT person_id FROM sibling_group_members
                WHERE group_id = ? ORDER BY member_order, person_id
                """,
                (row["id"],),
            )
        ]
        group = {
            "id": row["id"],
            "members": members,
            "ordered": bool(row["is_ordered"]),
            "label_en": row["label_en"],
            "label_ur": row["label_ur"],
        }
        if row["type"] is not None:
            group["type"] = row["type"]
        sibling_groups.append(group)

    review_notes = [
        {"id": row["id"], "status": row["status"], "text": row["text"]}
        for row in connection.execute(
            "SELECT * FROM review_notes ORDER BY display_order, id"
        )
    ]
    return {
        "metadata": metadata,
        "people": people,
        "parent_child": parent_child,
        "marriages": marriages,
        "sibling_groups": sibling_groups,
        "review_notes": review_notes,
    }


def validate_model(model: dict) -> None:
    """Raise ValueError with human-readable problems when invalid."""
    build_family.validate(model)


def run_family_audits(model: dict) -> dict:
    """Run the legacy derived-kinship and arbitrary-perspective audits."""
    derived = build_family._audit_derived(model)
    viewer = build_family._kinship_regression_audit(model)
    return {"derived_focus_cousin_paths": derived["focus_cousin_paths"], "people": viewer}


def family_snapshot(model: dict) -> dict:
    """Objective facts index used by family screens (never kinship labels)."""
    people_index = {person["id"]: person for person in model["people"]}
    snapshot = build_family._viewer_snapshot(model)
    return snapshot


def people_index(model: dict) -> dict:
    return {person["id"]: person for person in model["people"]}
