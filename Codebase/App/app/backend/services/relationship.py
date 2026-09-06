"""Canonical relationship service.

One implementation answers the React UI, the API, comparison, search and
Hermes. Family terms are computed by the preserved legacy kinship engine;
general relationships are merged as explicit facts without transitive
inference.
"""

import sqlite3

from ..domain.family import engine as build_family

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


def _cousin_rank(item: any) -> tuple:
    """Deterministic rank for cousin display: (degree, removal, side order)."""
    if isinstance(item, dict):
        norm = labels.normalize_family_entry(item)
    else:
        norm = labels.normalize_family_entry({"en": str(item)})
    degree = norm.get("degree") if norm.get("degree") is not None else 99
    removal = norm.get("removal") if norm.get("removal") is not None else 0
    side_val = norm.get("side")
    side_order = 1 if side_val == "maternal" else (2 if side_val == "paternal" else 3)
    return (degree, removal, side_order)


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


def _bind_paths_and_metadata(
    entries: list[dict],
    all_paths: list[dict],
    model: dict,
    perspective_id: str,
    target_id: str,
) -> None:
    # Direct fact lookup
    direct_pc = next(
        (
            rel
            for rel in model.get("parent_child", [])
            if (rel["parent"] == perspective_id and rel["child"] == target_id)
            or (rel["parent"] == target_id and rel["child"] == perspective_id)
        ),
        None,
    )
    direct_marriage = next(
        (
            m
            for m in model.get("marriages", [])
            if {m["person1"], m["person2"]} == {perspective_id, target_id}
        ),
        None,
    )
    direct_sibling = next(
        (
            g
            for g in model.get("sibling_groups", [])
            if perspective_id in g["members"] and target_id in g["members"]
        ),
        None,
    )

    for idx, entry in enumerate(entries):
        if entry.get("domain") == "general" and entry.get("general_relationship_id") is not None:
            entry["id"] = f"{target_id}:general:{entry['general_relationship_id']}"
        else:
            entry["id"] = f"{target_id}:{entry['relationship_type']}:{idx}"
        matching: list[dict] = []
        for p in all_paths:
            if p["domain"] == entry["domain"]:
                if entry["domain"] == "general":
                    if (
                        entry.get("general_relationship_id") is not None
                        and p.get("general_relationship_id") is not None
                    ):
                        if p["general_relationship_id"] == entry["general_relationship_id"]:
                            matching.append(p)
                    elif (
                        entry.get("stored_fact_id") is not None
                        and p.get("stored_fact_id") is not None
                    ):
                        if p["stored_fact_id"] == entry["stored_fact_id"]:
                            matching.append(p)
                    elif p["relationship_type"] == entry["relationship_type"]:
                        matching.append(p)
                else:
                    if p["relationship_type"] == entry["relationship_type"]:
                        matching.append(p)
                    elif (
                        entry.get("degree") is not None
                        and p.get("degree") == entry.get("degree")
                        and (entry.get("removal") or 0) == (p.get("removal") or 0)
                        and (not entry.get("side") or entry.get("side") == p.get("side"))
                    ):
                        matching.append(p)

        entry["path_ids"] = [p["id"] for p in matching]
        if matching:
            p0 = matching[0]
            if not entry.get("side") and p0.get("side"):
                entry["side"] = p0["side"]
            if entry.get("degree") is None and p0.get("degree") is not None:
                entry["degree"] = p0["degree"]
            if entry.get("removal") is None and p0.get("removal") is not None:
                entry["removal"] = p0["removal"]
            if not entry.get("common_ancestors") and p0.get("common_ancestors"):
                entry["common_ancestors"] = p0["common_ancestors"]
            if not entry.get("explanation") and p0.get("explanation"):
                entry["explanation"] = p0["explanation"]

        # Tag stored direct facts accurately based on structural provenance
        is_family = entry.get("domain") == "family"
        fact_kind = entry.get("stored_fact_kind") or entry.get("kind")
        rel_type = entry.get("relationship_type", "")

        is_pc_entry = fact_kind == "parent_child" or (
            direct_pc is not None
            and any(
                k in rel_type
                for k in ("father", "mother", "parent", "son", "daughter", "child")
            )
        )
        if direct_pc and is_family and is_pc_entry:
            entry["derived"] = False
            entry["stored_fact_kind"] = "parent_child"
            entry["kind"] = direct_pc.get("kind", "biological")
            entry["role"] = direct_pc.get("role", "parent")
        elif direct_marriage and is_family and (fact_kind == "marriage" or rel_type in ("husband", "wife")):
            entry["derived"] = False
            entry["stored_fact_kind"] = "marriage"
            entry["status"] = direct_marriage.get("status", "married")
            entry["year"] = direct_marriage.get("year")
        elif is_family and (fact_kind == "sibling" or "brother" in rel_type or "sister" in rel_type):
            if direct_sibling:
                entry["derived"] = False
                entry["stored_fact_kind"] = "sibling_group"
                entry["sibling_group_id"] = direct_sibling.get("id")
            else:
                entry["derived"] = True
                entry["stored_fact_kind"] = None


def get_relationship(
    perspective_person_id: str, target_person_id: str
) -> dict:
    """Every meaningful relationship from perspective -> target."""
    model = load_model()
    perspective = _person_brief(model, perspective_person_id)
    target = _person_brief(model, target_person_id)

    if perspective_person_id == target_person_id:
        self_entry = labels.normalize_family_entry({"en": "Self", "ur": "خود", "derived": False})
        self_entry["id"] = f"{target_person_id}:self:0"
        self_entry["path_ids"] = []
        return {
            "perspective": perspective,
            "target": target,
            "primary": [self_entry],
            "additional": [],
        }

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

    # Load proof paths to bind objective evidence to each entry
    from ..domain.relationships import path_service
    all_paths: list[dict] = []
    try:
        paths_res = path_service.get_relationship_paths(
            perspective_person_id, target_person_id, max_depth=15, max_paths=50
        )
        all_paths = paths_res.get("paths", [])
    except Exception:
        all_paths = []

    _bind_paths_and_metadata(family_primary, all_paths, model, perspective_person_id, target_person_id)
    _bind_paths_and_metadata(family_additional, all_paths, model, perspective_person_id, target_person_id)
    _bind_paths_and_metadata(general_primary, all_paths, model, perspective_person_id, target_person_id)

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
