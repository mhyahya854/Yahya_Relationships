"""Relationship-path service.

Given two people, this service returns objective graph paths that explain
every relationship label the canonical engine reports. Explicit facts
(parent-child, marriage, sibling groups, general relationships) become direct
paths; derived kinship terms are matched one-to-one with the canonical
engine's semantic records and rendered as concrete ancestor-chain paths.

Paths are derived data. They are never stored and never become the source of
truth.
"""

from __future__ import annotations

import sqlite3

import build_family as legacy

from ... import db
from ...kinship import labels
from ...model import load_model
from ...services.errors import AppError
from ..family import paths as family_paths
from ..family.paths import virtual_display_name

MAX_DEPTH_MIN = 1
MAX_DEPTH_MAX = 30
MAX_PATHS_MIN = 1
MAX_PATHS_MAX = 50
DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_PATHS = 10


def _validate_limits(max_depth: int, max_paths: int):
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or not (
        MAX_DEPTH_MIN <= max_depth <= MAX_DEPTH_MAX
    ):
        raise AppError(
            f"max_depth must be between {MAX_DEPTH_MIN} and {MAX_DEPTH_MAX}.",
            code="INVALID_MAX_DEPTH",
        )
    if not isinstance(max_paths, int) or isinstance(max_paths, bool) or not (
        MAX_PATHS_MIN <= max_paths <= MAX_PATHS_MAX
    ):
        raise AppError(
            f"max_paths must be between {MAX_PATHS_MIN} and {MAX_PATHS_MAX}.",
            code="INVALID_MAX_PATHS",
        )


def _gender_of(people_index: dict, person_id: str) -> str | None:
    return people_index.get(person_id, {}).get("gender")


def _normalise_entry(en: str, ur: str | None = None) -> dict:
    return labels.normalize_family_entry({"en": en, "ur": ur})


def _parent_label(rel: dict, gender: str | None) -> str:
    role = rel.get("role")
    if role in ("mother", "father"):
        return {"mother": "Mother", "father": "Father"}[role]
    if gender == "female":
        return "Mother"
    if gender == "male":
        return "Father"
    return "Parent"


def _child_label(gender: str | None) -> str:
    return {
        "male": "Son",
        "female": "Daughter",
    }.get(gender, "Child")


def _with_kind(base: str, kind: str | None) -> tuple[str, str | None]:
    if kind and kind != "biological":
        return f"{base} ({kind})", None
    return base, None


def _edge_role(from_id: str, to_id: str, model: dict) -> tuple[str, str]:
    """(type, subtype, role) for one directed step."""
    for rel in model["parent_child"]:
        if rel["parent"] == from_id and rel["child"] == to_id:
            return ("parent_child", rel["kind"], "is parent of")
        if rel["parent"] == to_id and rel["child"] == from_id:
            return ("parent_child", rel["kind"], "is child of")
    for marriage in model["marriages"]:
        if {marriage["person1"], marriage["person2"]} == {from_id, to_id}:
            return ("marriage", marriage.get("status", "married"), "is spouse of")
    for group in model.get("sibling_groups", []):
        if from_id in group["members"] and to_id in group["members"]:
            subtype = group.get("type") or "sibling"
            return ("sibling_group", subtype, "is a sibling of")
    return ("unknown", "", "is connected to")


def _edge_for_virtual(from_id: str, to_id: str, model: dict) -> dict:
    # Ancestor chains treat virtual full-sibling ancestors exactly like the
    # engine does: as calculation-only biological parents.
    return {
        "from": from_id,
        "to": to_id,
        "type": "parent_child",
        "subtype": "biological",
        "role": "is parent of"
        if from_id.startswith(family_paths.VIRTUAL_PREFIX)
        else "is child of",
    }


def _path_payload(
    *,
    domain: str,
    entry: dict,
    node_ids: list[str],
    model: dict,
    people_index: dict,
    side: str | None = None,
    degree: int | None = None,
    removal: int | None = None,
    common_ancestors: list[str] | None = None,
    derived: bool,
) -> dict:
    nodes = []
    for node_id in node_ids:
        if family_paths.is_virtual_node(node_id):
            nodes.append(
                {
                    "id": node_id,
                    "name": virtual_display_name(node_id),
                    "is_virtual": True,
                }
            )
        else:
            person = people_index.get(node_id, {})
            nodes.append(
                {
                    "id": node_id,
                    "name": person.get("name", node_id),
                    "is_virtual": False,
                }
            )
    edges = []
    for index in range(len(node_ids) - 1):
        from_id, to_id = node_ids[index], node_ids[index + 1]
        if family_paths.is_virtual_node(from_id) or family_paths.is_virtual_node(
            to_id
        ):
            edges.append(_edge_for_virtual(from_id, to_id, model))
        else:
            edge_type, subtype, role = _edge_role(from_id, to_id, model)
            edges.append(
                {
                    "from": from_id,
                    "to": to_id,
                    "type": edge_type,
                    "subtype": subtype,
                    "role": role,
                }
            )
    edge_signature = "|".join(
        f"{edge['from']}:{edge['to']}:{edge['type']}:{edge['subtype']}"
        for edge in edges
    )
    return {
        "id": family_paths.canonical_path_id(
            domain, entry["relationship_type"], node_ids, edge_signature
        ),
        "domain": domain,
        "relationship_type": entry["relationship_type"],
        "label_en": entry["label_en"],
        "label_ur": entry["label_ur"],
        "side": side or "",
        "degree": degree,
        "removal": removal,
        "distance": len(edges),
        "common_ancestors": [
            {
                "id": ancestor_id,
                "name": (
                    virtual_display_name(ancestor_id)
                    if family_paths.is_virtual_node(ancestor_id)
                    else people_index.get(ancestor_id, {}).get(
                        "name", ancestor_id
                    )
                ),
                "is_virtual": family_paths.is_virtual_node(ancestor_id),
            }
            for ancestor_id in (common_ancestors or [])
        ],
        "nodes": nodes,
        "edges": edges,
        "derived": derived,
    }


def _same_parents(model: dict, people_index: dict, first: str, second: str) -> list[str]:
    def parents_of(person_id: str) -> list[str]:
        return sorted(
            rel["parent"]
            for rel in model["parent_child"]
            if rel["child"] == person_id and rel.get("kind") == "biological"
        )

    parents_a = parents_of(first)
    parents_b = parents_of(second)
    if parents_a and parents_a == parents_b:
        return parents_a
    return []


def _shared_sibling_group(model: dict, first: str, second: str) -> list[dict]:
    return [
        group
        for group in model.get("sibling_groups", [])
        if first in group["members"] and second in group["members"]
    ]


def _explicit_paths(
    *,
    model: dict,
    people_index: dict,
    perspective_id: str,
    target_id: str,
    general_rows: list,
) -> tuple[list[dict], bool]:
    """Direct factual paths (parent/child, spouse, sibling, general)."""
    paths = []
    sibling_present = False

    # Parent / child --------------------------------------------------------
    for rel in model["parent_child"]:
        kind = rel.get("kind")
        if rel["parent"] == perspective_id and rel["child"] == target_id:
            base = _child_label(_gender_of(people_index, target_id))
            en, ur = _with_kind(base, kind)
            entry = _normalise_entry(en, ur)
            paths.append(
                _path_payload(
                    domain="family",
                    entry=entry,
                    node_ids=[perspective_id, target_id],
                    model=model,
                    people_index=people_index,
                    derived=False,
                )
            )
        elif rel["parent"] == target_id and rel["child"] == perspective_id:
            base = _parent_label(rel, _gender_of(people_index, target_id))
            en, ur = _with_kind(base, kind)
            entry = _normalise_entry(en, ur)
            paths.append(
                _path_payload(
                    domain="family",
                    entry=entry,
                    node_ids=[perspective_id, target_id],
                    model=model,
                    people_index=people_index,
                    derived=False,
                )
            )

    # Marriage --------------------------------------------------------------
    for marriage in model["marriages"]:
        if {marriage["person1"], marriage["person2"]} == {
            perspective_id,
            target_id,
        }:
            gender = _gender_of(people_index, target_id)
            en = "Wife" if gender == "female" else "Husband"
            entry = _normalise_entry(en)
            paths.append(
                _path_payload(
                    domain="family",
                    entry=entry,
                    node_ids=[perspective_id, target_id],
                    model=model,
                    people_index=people_index,
                    derived=False,
                )
            )

    # Siblings --------------------------------------------------------------
    shared_parents = _same_parents(model, people_index, perspective_id, target_id)
    groups = _shared_sibling_group(model, perspective_id, target_id)
    if shared_parents or groups:
        sibling_present = True
        explicit_full = any(group.get("type") == "full" for group in groups)
        gender = _gender_of(people_index, target_id)
        if gender == "female":
            en = "Full sister" if explicit_full else "Sister"
        else:
            en = "Full brother" if explicit_full else "Brother"
        entry = _normalise_entry(en)
        if shared_parents:
            # Canonical proof: through one shared parent (mother preferred).
            parents_by_gender = sorted(
                shared_parents,
                key=lambda person_id: (
                    0 if _gender_of(people_index, person_id) == "female" else 1,
                    person_id,
                ),
            )
            for parent_id in parents_by_gender[:1]:
                paths.append(
                    _path_payload(
                        domain="family",
                        entry=entry,
                        node_ids=[perspective_id, parent_id, target_id],
                        model=model,
                        people_index=people_index,
                        common_ancestors=shared_parents,
                        derived=False,
                    )
                )
        else:
            group = groups[0]
            paths.append(
                _path_payload(
                    domain="family",
                    entry=entry,
                    node_ids=[perspective_id, target_id],
                    model=model,
                    people_index=people_index,
                    derived=False,
                )
            )

    # General relationships -------------------------------------------------
    for row in general_rows:
        entry = labels.normalize_general_entry(
            row,
            from_person=perspective_id,
            label_a_to_b=row["label_a_to_b"],
            label_b_to_a=row["label_b_to_a"],
        )
        paths.append(
            _path_payload(
                domain="general",
                entry=entry,
                node_ids=[perspective_id, target_id],
                model=model,
                people_index=people_index,
                derived=False,
            )
        )
    return paths, sibling_present


def _derived_en(
    *,
    people_index: dict,
    target_id: str,
    record: dict,
    explicit_sibling: bool,
) -> tuple[str, str | None, str | None, int | None, int | None] | None:
    """English label text for one canonical derived record, mirroring the
    engine's derived-label table (side included in the label text)."""
    kind = record["kind"]
    target_gender = _gender_of(people_index, target_id)
    side = record.get("side", "")
    side_word = side if side in ("maternal", "paternal") else ""

    if kind == "ancestor":
        distance = record["distance"]
        if distance < 2:
            return None
        if distance == 2:
            base = "Grandfather" if target_gender == "male" else "Grandmother"
            en = f"{side.capitalize()} {base}" if side_word else base
            return en, None, side, None, None
        prefix = "great-" * (distance - 2)
        base = "grandfather" if target_gender == "male" else "grandmother"
        return f"{prefix}{base}", None, None, None, None

    if kind == "descendant":
        distance = record["distance"]
        if distance < 2:
            return None
        base = "grandson" if target_gender == "male" else "granddaughter"
        if distance == 2:
            en = "Grandson" if target_gender == "male" else "Granddaughter"
        else:
            prefix = "great-" * (distance - 2)
            en = f"{prefix}{base}"
        return en, None, None, None, None

    if kind == "collateral":
        da = record["da"]
        db = record["db"]
        if da == 1 and db == 1:
            if explicit_sibling:
                return None
            en = "Half sister" if target_gender == "female" else "Half brother"
            return en, None, None, None, None
        if da == 1 and db >= 2:
            depth = db - 1
            base = "niece" if target_gender == "female" else "nephew"
            if depth == 1:
                en = "Niece" if target_gender == "female" else "Nephew"
            else:
                prefix = (
                    "grand" if depth == 2 else f"great-" * (depth - 2) + "grand"
                )
                en = f"{prefix}{base}"
            return en, None, None, None, None
        if db == 1 and da >= 2:
            base = "uncle" if target_gender == "male" else "aunt"
            if da == 2:
                if side_word:
                    en = f"{side} {base}".capitalize()
                else:
                    en = base.capitalize()
            else:
                prefix = "great-" * (da - 2)
                if side_word:
                    en = f"{prefix}{side} {base}".capitalize()
                else:
                    en = f"{prefix}{base}".capitalize()
            return en, None, side, None, None
        if da >= 2 and db >= 2:
            degree = min(da, db) - 1
            removal = abs(da - db)
            if degree >= 1:
                side_text = f"{side_word} " if side_word else ""
                en = side_text + legacy._cousin_en(degree, removal)
                return en, legacy._cousin_ur(degree, removal), side, degree, removal
    return None


def _derived_paths(
    *,
    model: dict,
    people_index: dict,
    perspective_id: str,
    target_id: str,
    explicit_sibling: bool,
    max_depth: int,
) -> list[dict]:
    paths = []
    records = family_paths.pair_record_paths(
        model, perspective_id, target_id, people_index
    )
    for record in records:
        label = _derived_en(
            people_index=people_index,
            target_id=target_id,
            record=record,
            explicit_sibling=explicit_sibling,
        )
        if label is None:
            continue
        en, ur, side, degree, removal = label
        node_ids = family_paths.concrete_path_nodes(record)
        if len(node_ids) - 1 > max_depth:
            continue
        entry = _normalise_entry(en, ur)
        common = [
            ancestor
            for ancestor in record.get("common_ancestors", [])
        ]
        paths.append(
            _path_payload(
                domain="family",
                entry=entry,
                node_ids=node_ids,
                model=model,
                people_index=people_index,
                side=side,
                degree=degree,
                removal=removal,
                common_ancestors=common,
                derived=True,
            )
        )
    # Meaningful/simple paths first, deterministic ties.
    paths.sort(
        key=lambda path: (
            path["distance"],
            path["label_en"].casefold(),
            [node["id"] for node in path["nodes"]],
        )
    )
    return paths


def _general_rows_for(connection: sqlite3.Connection, first: str, second: str):
    low, high = sorted((first, second))
    return connection.execute(
        """
        SELECT * FROM general_relationships
        WHERE person_a = ? AND person_b = ?
        """,
        (low, high),
    ).fetchall()


def get_relationship_paths(
    perspective_person_id: str,
    target_person_id: str,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_paths: int = DEFAULT_MAX_PATHS,
) -> dict:
    _validate_limits(max_depth, max_paths)
    model = load_model()
    people_index = {person["id"]: person for person in model["people"]}
    if perspective_person_id not in people_index:
        raise AppError(
            f"Unknown perspective person: {perspective_person_id}",
            code="NOT_FOUND",
        )
    if target_person_id not in people_index:
        raise AppError(
            f"Unknown target person: {target_person_id}",
            code="NOT_FOUND",
        )
    perspective = {
        "id": people_index[perspective_person_id]["id"],
        "name": people_index[perspective_person_id]["name"],
    }
    target = {
        "id": people_index[target_person_id]["id"],
        "name": people_index[target_person_id]["name"],
    }
    if perspective_person_id == target_person_id:
        return {
            "perspective": perspective,
            "target": target,
            "paths": [],
            "truncated": False,
        }

    connection = db.get_connection()
    try:
        general_rows = _general_rows_for(
            connection, perspective_person_id, target_person_id
        )
    finally:
        connection.close()

    explicit, sibling_present = _explicit_paths(
        model=model,
        people_index=people_index,
        perspective_id=perspective_person_id,
        target_id=target_person_id,
        general_rows=general_rows,
    )
    derived = _derived_paths(
        model=model,
        people_index=people_index,
        perspective_id=perspective_person_id,
        target_id=target_person_id,
        explicit_sibling=sibling_present,
        max_depth=max_depth,
    )
    all_paths = explicit + derived
    if not all_paths:
        raise AppError(
            f"No supported relationship path was found within max_depth "
            f"{max_depth}.",
            code="NO_RELATIONSHIP_PATH",
        )
    truncated = len(all_paths) > max_paths
    return {
        "perspective": perspective,
        "target": target,
        "paths": all_paths[:max_paths],
        "truncated": truncated,
    }


def path_explanation(path: dict, perspective: dict, target: dict) -> str:
    """Deterministic, template-based prose for a returned path (no AI)."""
    if not path.get("nodes"):
        return ""
    label = path.get("label_en", "")
    side = path.get("side")
    side_text = f"{side} side" if side in ("maternal", "paternal") else ""
    ancestors = path.get("common_ancestors") or []
    ancestor_text = ""
    if ancestors:
        names = ", ".join(ancestor["name"] for ancestor in ancestors)
        ancestor_text = f" through shared ancestor{'s' if len(ancestors) > 1 else ''} {names}"
    if path.get("domain") == "general":
        return (
            f"{target['name']} is directly connected to {perspective['name']} "
            f"by the recorded relationship “{label}”. No family derivation is involved."
        )
    if path.get("derived"):
        distance = path.get("distance", 0)
        return (
            f"This {side_text or 'family'} path spans {distance} recorded family "
            f"steps{ancestor_text}, which makes {target['name']} a {label} of "
            f"{perspective['name']}."
        )
    return (
        f"{target['name']} is directly recorded as {label} of "
        f"{perspective['name']}."
    )
