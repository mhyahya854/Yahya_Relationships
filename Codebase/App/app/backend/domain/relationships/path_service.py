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

from collections import defaultdict, deque
import sqlite3

from ..family import engine as legacy

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
    path_key = (
        entry.get("stored_fact_id")
        if (domain == "general" and entry.get("stored_fact_id"))
        else entry["relationship_type"]
    )
    return {
        "id": family_paths.canonical_path_id(
            domain, path_key, node_ids, edge_signature
        ),
        "domain": domain,
        "relationship_type": entry["relationship_type"],
        "semantic_id": entry.get("semantic_id", entry["relationship_type"]),
        "general_relationship_id": entry.get("general_relationship_id"),
        "stored_fact_id": entry.get("stored_fact_id"),
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
            target_gender = _gender_of(people_index, target_id)
            base = _child_label(target_gender)
            en, ur = _with_kind(base, kind)
            child_role = "son" if target_gender == "male" else ("daughter" if target_gender == "female" else "child")
            entry = labels.normalize_family_entry({
                "en": en,
                "ur": ur,
                "kind": "parent_child",
                "role": child_role,
                "target_gender": target_gender,
                "suffix": kind if kind and kind != "biological" else None,
            })
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
            target_gender = _gender_of(people_index, target_id)
            base = _parent_label(rel, target_gender)
            en, ur = _with_kind(base, kind)
            parent_role = rel.get("role") or ("mother" if target_gender == "female" else ("father" if target_gender == "male" else "parent"))
            entry = labels.normalize_family_entry({
                "en": en,
                "ur": ur,
                "kind": "parent_child",
                "role": parent_role,
                "target_gender": target_gender,
                "suffix": kind if kind and kind != "biological" else None,
            })
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
            entry = labels.normalize_family_entry({
                "en": en,
                "kind": "marriage",
                "target_gender": gender,
            })
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
        has_explicit_group = len(groups) > 0
        explicit_full = any(group.get("type") == "full" for group in groups)
        gender = _gender_of(people_index, target_id)
        if gender == "female":
            en = "Full sister" if explicit_full else "Sister"
        else:
            en = "Full brother" if explicit_full else "Brother"
        entry = labels.normalize_family_entry({
            "en": en,
            "kind": "sibling",
            "target_gender": gender,
            "explicit_full": explicit_full,
            "sibling_type": "full" if explicit_full else "biological",
            "stored_fact_kind": "sibling_group" if has_explicit_group else None,
            "derived": not has_explicit_group,
        })
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
                        derived=not has_explicit_group,
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
    include_affinal: bool = True,
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
        target_g = _gender_of(people_index, target_id)
        entry_data = {
            "en": en,
            "ur": ur,
            "kind": record["kind"],
            "side": side,
            "degree": degree,
            "removal": removal,
            "distance": record.get("distance"),
            "da": record.get("da"),
            "db": record.get("db"),
            "target_gender": target_g,
        }
        entry = labels.normalize_family_entry(entry_data)
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

    if include_affinal:
        target_gender = _gender_of(people_index, target_id)
        for marriage in model["marriages"]:
            if target_id not in (marriage["person1"], marriage["person2"]):
                continue
            if marriage.get("status") == "divorced":
                continue
            spouse_id = (
                marriage["person2"]
                if marriage["person1"] == target_id
                else marriage["person1"]
            )
            if spouse_id == perspective_id:
                continue
            spouse_paths = _derived_paths(
                model=model,
                people_index=people_index,
                perspective_id=perspective_id,
                target_id=spouse_id,
                explicit_sibling=False,
                max_depth=max_depth - 1,
                include_affinal=False,
            )
            for spouse_path in spouse_paths:
                spec = legacy.AFFINAL_SPOUSE_ROLES.get(
                    (spouse_path["relationship_type"], target_gender)
                )
                if not spec:
                    continue
                en, ur, affinal_role, side = spec
                node_ids = [node["id"] for node in spouse_path["nodes"]] + [target_id]
                if len(node_ids) - 1 > max_depth:
                    continue
                entry = labels.normalize_family_entry({
                    "semantic_id": affinal_role,
                    "en": en,
                    "ur": ur,
                    "kind": "affinal",
                    "affinal_role": affinal_role,
                    "side": side,
                    "target_gender": target_gender,
                    "derived": True,
                })
                paths.append(
                    _path_payload(
                        domain="family",
                        entry=entry,
                        node_ids=node_ids,
                        model=model,
                        people_index=people_index,
                        side=side,
                        common_ancestors=[
                            ancestor["id"]
                            for ancestor in spouse_path.get("common_ancestors", [])
                        ],
                        derived=True,
                    )
                )
    # Meaningful/simple paths first, deterministic ties.
    paths.sort(
        key=lambda path: (
            path["distance"],
            path["degree"] if path["degree"] is not None else 99,
            path["removal"] if path["removal"] is not None else 99,
            path["relationship_type"],
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


def _connection_route_payload(
    *,
    node_ids: list[str],
    edges: list[dict],
    people_index: dict,
) -> dict:
    """A display-only route through explicit direct facts.

    This is intentionally separate from kinship labels and general-relation
    labels.  It answers “how are these people connected?” without asserting
    that the endpoints have acquired a transitive friendship or another stored
    relationship.
    """
    edge_signature = "|".join(
        f"{edge['from']}:{edge['to']}:{edge['type']}:{edge['subtype']}"
        for edge in edges
    )
    return {
        "id": family_paths.canonical_path_id(
            "connection", "explicit_connection_route", node_ids, edge_signature
        ),
        "domain": "connection",
        "relationship_type": "explicit_connection_route",
        "semantic_id": "explicit_connection_route",
        "label_en": "Recorded connection route",
        "label_ur": None,
        "side": "",
        "degree": None,
        "removal": None,
        "distance": len(edges),
        "common_ancestors": [],
        "nodes": [
            {
                "id": person_id,
                "name": people_index.get(person_id, {}).get("name", person_id),
                "is_virtual": False,
            }
            for person_id in node_ids
        ],
        "edges": edges,
        "derived": True,
        "explanation": "",
    }


def _explicit_connection_routes(
    *,
    model: dict,
    people_index: dict,
    perspective_id: str,
    target_id: str,
    general_rows: list,
    max_depth: int,
    max_routes: int,
) -> tuple[list[dict], bool]:
    """Enumerate bounded mixed routes through recorded direct facts only.

    The canonical family engine remains responsible for kinship labels.  This
    helper never derives one: it simply traces direct parent/child, marriage,
    explicit sibling-group, and explicit general edges.  A route is returned
    only when it includes a general edge and has at least two steps, because
    direct family/general facts already have their own canonical path payload.
    """
    adjacency: dict[str, list[tuple[str, dict]]] = defaultdict(list)

    def add_pair(first: str, second: str, forward: dict, reverse: dict) -> None:
        adjacency[first].append((second, forward))
        adjacency[second].append((first, reverse))

    for relation in model["parent_child"]:
        parent_id = relation["parent"]
        child_id = relation["child"]
        kind = relation.get("kind") or "biological"
        add_pair(
            parent_id,
            child_id,
            {
                "from": parent_id,
                "to": child_id,
                "type": "parent_child",
                "subtype": kind,
                "role": "is parent of",
            },
            {
                "from": child_id,
                "to": parent_id,
                "type": "parent_child",
                "subtype": kind,
                "role": "is child of",
            },
        )

    for marriage in model["marriages"]:
        first = marriage["person1"]
        second = marriage["person2"]
        status = marriage.get("status") or "married"
        add_pair(
            first,
            second,
            {
                "from": first,
                "to": second,
                "type": "marriage",
                "subtype": status,
                "role": "is spouse of",
            },
            {
                "from": second,
                "to": first,
                "type": "marriage",
                "subtype": status,
                "role": "is spouse of",
            },
        )

    for group in model.get("sibling_groups", []):
        members = sorted(group["members"])
        subtype = group.get("type") or "sibling"
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                add_pair(
                    first,
                    second,
                    {
                        "from": first,
                        "to": second,
                        "type": "sibling_group",
                        "subtype": subtype,
                        "role": "is a sibling of",
                    },
                    {
                        "from": second,
                        "to": first,
                        "type": "sibling_group",
                        "subtype": subtype,
                        "role": "is a sibling of",
                    },
                )

    for row in general_rows:
        first = row["person_a"]
        second = row["person_b"]
        forward_entry = labels.normalize_general_entry(
            row,
            from_person=first,
            label_a_to_b=row["label_a_to_b"],
            label_b_to_a=row["label_b_to_a"],
        )
        reverse_entry = labels.normalize_general_entry(
            row,
            from_person=second,
            label_a_to_b=row["label_a_to_b"],
            label_b_to_a=row["label_b_to_a"],
        )
        add_pair(
            first,
            second,
            {
                "from": first,
                "to": second,
                "type": "general",
                "subtype": row["type"],
                "role": forward_entry["label_en"],
            },
            {
                "from": second,
                "to": first,
                "type": "general",
                "subtype": row["type"],
                "role": reverse_entry["label_en"],
            },
        )

    for person_id in adjacency:
        adjacency[person_id].sort(
            key=lambda item: (
                item[0],
                item[1]["type"],
                item[1]["subtype"],
                item[1]["role"],
            )
        )

    routes: list[dict] = []
    shortest_distance: int | None = None
    queue: deque[tuple[list[str], list[dict]]] = deque(
        [([perspective_id], [])]
    )
    explored = 0
    # All valid routes are still bounded by the public depth/path limits. This
    # extra work cap guards a dense user graph from combinatorial blow-up while
    # leaving ample space to discover the requested safe maximum of 50 routes.
    exploration_cap = max(2_000, max_routes * 500)
    truncated = False
    while queue:
        node_ids, edges = queue.popleft()
        if shortest_distance is not None and len(edges) >= shortest_distance:
            continue
        if len(edges) >= max_depth:
            continue
        current_id = node_ids[-1]
        for next_id, edge in adjacency.get(current_id, []):
            explored += 1
            if explored > exploration_cap:
                truncated = True
                queue.clear()
                break
            if next_id in node_ids:
                continue
            next_nodes = [*node_ids, next_id]
            next_edges = [*edges, edge]
            if next_id == target_id:
                if (
                    len(next_edges) > 1
                    and any(item["type"] == "general" for item in next_edges)
                ):
                    if shortest_distance is None:
                        shortest_distance = len(next_edges)
                    if len(next_edges) != shortest_distance:
                        continue
                    routes.append(
                        _connection_route_payload(
                            node_ids=next_nodes,
                            edges=next_edges,
                            people_index=people_index,
                        )
                    )
                    if len(routes) >= max_routes:
                        truncated = bool(queue) or True
                        queue.clear()
                        break
                continue
            queue.append((next_nodes, next_edges))

    routes.sort(
        key=lambda route: (
            route["distance"],
            [node["id"] for node in route["nodes"]],
            route["id"],
        )
    )
    return routes, truncated


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
        all_general_rows = connection.execute(
            "SELECT * FROM general_relationships ORDER BY id"
        ).fetchall()
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
    # A direct canonical relation or family derivation already answers this
    # pair.  Do not drown it in arbitrary social/family traversals: mixed
    # display-only routes are the fallback for otherwise-unrelated endpoints.
    connection_routes: list[dict] = []
    connection_truncated = False
    if not explicit and not derived:
        connection_routes, connection_truncated = _explicit_connection_routes(
            model=model,
            people_index=people_index,
            perspective_id=perspective_person_id,
            target_id=target_person_id,
            general_rows=all_general_rows,
            max_depth=max_depth,
            max_routes=max_paths + 1,
        )
    paths_by_id = {
        path["id"]: path for path in [*explicit, *derived, *connection_routes]
    }
    all_paths = list(paths_by_id.values())
    if not all_paths:
        raise AppError(
            f"No supported relationship path was found within max_depth "
            f"{max_depth}.",
            code="NO_RELATIONSHIP_PATH",
        )
    for path in all_paths:
        path["explanation"] = path_explanation(path, perspective, target)
    all_paths.sort(
        key=lambda path: (
            path["distance"],
            0 if path["domain"] == "family" else 1 if path["domain"] == "general" else 2,
            path["degree"] if path["degree"] is not None else 99,
            path["removal"] if path["removal"] is not None else 99,
            path["relationship_type"],
            [node["id"] for node in path["nodes"]],
        )
    )
    truncated = len(all_paths) > max_paths or connection_truncated
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
    if path.get("domain") == "connection":
        return (
            f"This display route follows recorded direct family and/or general "
            f"connections between {perspective['name']} and {target['name']}. "
            "It does not create a new transitive relationship label."
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
