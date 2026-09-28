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
    return {
        "id": person_id if person_id in people_index(model) else person["id"],
        "canonical_id": person["id"],
        "name": person["name"],
    }


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


def display_rank_key(entry: dict) -> tuple:
    """Canonical, person-independent ordering for relationship display.

    The tuple keeps a legitimate family role ahead of unrelated general labels,
    then gives direct canonical family facts (spouse, parent/child, sibling)
    priority over longer derived identities. Among derived family identities it
    favors a blood role over an affinal variant, then the shortest human-
    readable proof. Every non-winning entry remains available as an additional
    relationship.
    """
    distance = entry.get("path_distance") or entry.get("distance")
    if not isinstance(distance, int) or distance < 1:
        distance = 1 if not entry.get("derived") else 99
    domain_order = 0 if entry.get("domain") == "family" else 1
    relationship_type = str(entry.get("relationship_type") or "").casefold()
    fact_kind = str(entry.get("stored_fact_kind") or entry.get("kind") or "").casefold()
    affinal = (
        fact_kind in {"marriage", "affinal"}
        or "in_law" in relationship_type
        or relationship_type in {"chachi", "mami", "phopha", "khalu"}
        or any(word in relationship_type for word in ("husband", "wife", "spouse"))
    )
    stored_order = 0 if not entry.get("derived", False) else 1
    direct_family_order = 0 if domain_order == 0 and stored_order == 0 and distance == 1 else 1
    degree = entry.get("degree") if entry.get("degree") is not None else 99
    removal = entry.get("removal") if entry.get("removal") is not None else 99
    side = entry.get("side")
    side_order = 0 if side == "maternal" else (1 if side == "paternal" else 2)
    semantic = str(entry.get("semantic_id") or relationship_type)
    label = str(entry.get("label_en") or "").casefold()
    return (
        domain_order,
        direct_family_order,
        1 if affinal else 0,
        distance,
        stored_order,
        degree,
        removal,
        side_order,
        semantic,
        label,
    )


def _rank_relationship_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=display_rank_key)


def _family_entries(pair: dict) -> tuple[list[dict], list[dict]]:
    def normalize(item: dict) -> dict:
        entry = labels.normalize_family_entry(item)
        da = item.get("da")
        db = item.get("db")
        if isinstance(da, int) and isinstance(db, int):
            entry["path_distance"] = da + db
        return entry

    primary = [normalize(item) for item in pair.get("main", [])]
    additional = [normalize(item) for item in pair.get("additional", [])]
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
            entry["path_distance"] = min(
                path.get("distance", 99) for path in matching
            )
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

    persp_id = perspective.get("canonical_id", perspective["id"])
    tgt_id = target.get("canonical_id", target["id"])

    if persp_id == tgt_id:
        self_entry = labels.normalize_family_entry({"en": "Self", "ur": "خود", "derived": False})
        self_entry["id"] = f"{tgt_id}:self:0"
        self_entry["path_ids"] = []
        return {
            "perspective": perspective,
            "target": target,
            "primary": [self_entry],
            "additional": [],
        }

    pair = _engine_pair(model, persp_id, tgt_id)
    family_primary, family_additional = _family_entries(pair)

    connection = db.get_connection()
    try:
        general_primary = _general_entries(
            _general_rows(connection, persp_id, tgt_id),
            persp_id,
            tgt_id,
        )
    finally:
        connection.close()

    # Load proof paths to bind objective evidence to each entry
    from ..domain.relationships import path_service
    all_paths: list[dict] = []
    try:
        paths_res = path_service.get_relationship_paths(
            persp_id, tgt_id, max_depth=15, max_paths=50
        )
        all_paths = paths_res.get("paths", [])
    except Exception:
        all_paths = []

    _bind_paths_and_metadata(family_primary, all_paths, model, persp_id, tgt_id)
    _bind_paths_and_metadata(family_additional, all_paths, model, persp_id, tgt_id)
    _bind_paths_and_metadata(general_primary, all_paths, model, persp_id, tgt_id)

    # One deterministic easiest role is the calm default. Alternatives remain
    # canonical evidence and are never deleted or collapsed into a new fact.
    ranked = _rank_relationship_entries(
        general_primary + family_primary + family_additional
    )
    primary = ranked[:1]
    additional = ranked[1:]
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
            ranked = _rank_relationship_entries(
                general_primary + family_primary + family_additional
            )
            primary = ranked[:1]
            additional = ranked[1:]
            if domain == "general":
                ranked = _rank_relationship_entries(general_primary)
                primary = ranked[:1]
                additional = ranked[1:]
            elif domain == "family":
                ranked = _rank_relationship_entries(family_primary + family_additional)
                primary = ranked[:1]
                additional = ranked[1:]
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
