"""Canonical relationship service.

One implementation answers the React UI, the API, comparison, search and
Hermes. Family terms are computed by the preserved legacy kinship engine;
general relationships are merged as explicit facts without transitive
inference.
"""

import sqlite3

import build_family

from .. import db
from ..kinship import labels
from ..model import load_model, people_index
from . import errors


def _person_brief(model: dict, person_id: str) -> dict:
    person = people_index(model).get(person_id)
    if person is None:
        raise errors.NotFoundError(f"Unknown person id: {person_id}")
    return {"id": person["id"], "name": person["name"]}


def _general_rows(
    connection: sqlite3.Connection, first: str, second: str
) -> list[sqlite3.Row]:
    person_low, person_high = sorted((first, second))
    return connection.execute(
        """
        SELECT * FROM general_relationships
        WHERE person_a = ? AND person_b = ?
        """,
        (person_low, person_high),
    ).fetchall()


def _engine_pair(model: dict, first: str, second: str) -> dict:
    index = people_index(model)
    if first == second:
        return {
            "main": [{"en": "Self", "ur": "خود", "group": "primary"}],
            "additional": [],
        }
    entries = build_family._pair_relationship_entries(model, first, second, index)
    main = [
        item for item in entries if item["group"] in ("primary", "direct")
    ]
    cousins = [item for item in entries if item["group"] == "cousin"]
    if not main:
        # No direct role: the shortest/strongest cousin path becomes primary
        # and every remaining valid path is preserved under additional.
        cousins_sorted = sorted(
            cousins,
            key=lambda item: (
                _cousin_rank(item["en"]),
                item["en"].lower(),
            ),
        )
        if cousins_sorted:
            main = [cousins_sorted[0]]
            cousins = cousins_sorted[1:]
        else:
            cousins = []
    return {"main": main, "additional": cousins}


def _cousin_rank(en: str) -> tuple:
    """Deterministic rank for cousin display: (degree, removal, side order)."""
    text = " ".join(en.lower().split())
    degree = 99
    for word in (
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
    ):
        if text.startswith(word) or f" {word} " in f" {text} ":
            degree = {
                "first": 1,
                "second": 2,
                "third": 3,
                "fourth": 4,
                "fifth": 5,
                "sixth": 6,
                "seventh": 7,
                "eighth": 8,
                "ninth": 9,
                "tenth": 10,
            }[word]
            break
    removal = 0
    if "once removed" in text:
        removal = 1
    elif "twice removed" in text:
        removal = 2
    else:
        import re as _re

        match = _re.search(r"(\d+) times removed", text)
        if match:
            removal = int(match.group(1))
    side = 1 if "maternal" in text else (2 if "paternal" in text else 3)
    return (degree, removal, side)


def _family_entries(pair: dict) -> tuple[list[dict], list[dict]]:
    primary = [
        labels.normalize_family_entry(item)
        for item in pair.get("main", [])
    ]
    additional = [
        labels.normalize_family_entry(item)
        for item in pair.get("additional", [])
    ]
    return primary, additional


def _general_entries(
    rows: list[sqlite3.Row], first: str, second: str
) -> list[dict]:
    entries = []
    for row in rows:
        entries.append(
            labels.normalize_general_entry(
                row,
                from_person=first,
                label_a_to_b=row["label_a_to_b"],
                label_b_to_a=row["label_b_to_a"],
            )
        )
    return entries


def get_relationship(
    perspective_person_id: str, target_person_id: str
) -> dict:
    """Every meaningful relationship from perspective -> target."""
    model = load_model()
    perspective = _person_brief(model, perspective_person_id)
    target = _person_brief(model, target_person_id)
    pair = _engine_pair(model, perspective_person_id, target_person_id)
    family_primary, family_additional = _family_entries(pair)

    connection = db.get_connection()
    try:
        general_primary = _general_entries(
            _general_rows(connection, perspective_person_id, target_person_id),
            perspective_person_id,
            target_person_id,
        )
    finally:
        connection.close()

    # Explicit general relationships surface first; direct family facts and
    # derived direct blood roles come next; cousin paths remain additional.
    primary = general_primary + family_primary
    additional = family_additional
    return {
        "perspective": perspective,
        "target": target,
        "primary": primary,
        "additional": additional,
    }


def list_relationships_from(
    person_id: str,
    *,
    domain: str | None = None,
    direct_only: bool = False,
) -> list[dict]:
    model = load_model()
    _person_brief(model, person_id)
    index = people_index(model)
    connection = db.get_connection()
    try:
        rows = []
        ordered = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM people ORDER BY display_order, name"
            )
        ]
        for target_id in ordered:
            if target_id == person_id:
                continue
            pair = _engine_pair(model, person_id, target_id)
            family_primary, family_additional = _family_entries(pair)
            general_rows = _general_rows(connection, person_id, target_id)
            general_primary = _general_entries(
                general_rows, person_id, target_id
            )
            primary = general_primary + family_primary
            additional = family_additional
            if domain == "general":
                primary = general_primary
                additional = []
            elif domain == "family":
                primary = family_primary
                additional = family_additional
            if direct_only:
                additional = []
            if not primary and not additional:
                continue
            rows.append(
                {
                    "target": index[target_id],
                    "primary": primary,
                    "additional": additional,
                }
            )
        return rows
    finally:
        connection.close()


def compare_people(person_a: str, person_b: str) -> dict:
    return {
        "a": _person_brief(load_model(), person_a),
        "b": _person_brief(load_model(), person_b),
        "a_to_b": get_relationship(person_a, person_b),
        "b_to_a": get_relationship(person_b, person_a),
    }
