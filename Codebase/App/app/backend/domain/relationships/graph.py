"""Graph neighbour/expansion service.

The Relationships graph is fed explicit node/edge data from the backend so
React never re-derives genealogy. Expansion returns only the requested
objective neighbourhood plus relationship-to-perspective labels computed by
the canonical engine.
"""

from __future__ import annotations

from ..family import engine as legacy

from ...model import load_model
from ...services.errors import AppError

VALID_FILTERS = {"parents", "children", "siblings", "spouses", "general", "all"}
FAMILY_FILTERS = {"parents", "children", "siblings", "spouses"}


def _edge_id(edge_type: str, subtype: str, source: str, target: str) -> str:
    return f"{edge_type}:{subtype}:{source}:{target}"


def _norm(edge_type: str, subtype: str, a: str, b: str):
    """Canonical ordering for undirected edge kinds."""
    if edge_type in ("marriage", "sibling_group", "general"):
        a, b = sorted((a, b))
    return (edge_type, subtype, a, b)


def _person_brief(person: dict) -> dict:
    return {
        "id": person["id"],
        "name": person["name"],
        "gender": person.get("gender"),
        "birth_year": person.get("birth_year"),
    }


def _relation_to(model: dict, index: dict, perspective_id: str, target_id: str):
    """First primary relationship label from perspective -> target."""
    if perspective_id == target_id:
        return None
    pair = legacy._viewer_pair(model, perspective_id, target_id, index)
    items = pair.get("main") or []
    if not items:
        return None
    first = items[0]
    return {
        "label_en": first.get("en"),
        "label_ur": first.get("ur"),
    }


def get_graph_neighbors(
    person_id: str,
    *,
    perspective_id: str | None = None,
    filters: list[str] | None = None,
) -> dict:
    model = load_model()
    index = {person["id"]: person for person in model["people"]}
    if person_id not in index:
        raise AppError(f"Unknown person id: {person_id}", code="NOT_FOUND")
    requested = filters or ["parents", "children", "siblings", "spouses", "general"]
    unknown = set(requested) - VALID_FILTERS
    if unknown:
        raise AppError(
            f"Unknown expansion filter(s): {sorted(unknown)}",
            code="INVALID_FILTER",
        )
    if "all" in requested:
        active = VALID_FILTERS - {"all"}
    else:
        active = set(requested)

    person = index[person_id]
    perspective_id = perspective_id or model["metadata"].get("focus_person")
    if perspective_id not in index:
        perspective_id = model["metadata"].get("focus_person")

    neighbour_ids: list[str] = []
    edge_defs: list[tuple[str, str, str, str]] = []  # type, subtype, source, target

    for rel in model["parent_child"]:
        kind = rel.get("kind") or "biological"
        if rel["parent"] == person_id and "children" in active:
            neighbour_ids.append(rel["child"])
            edge_defs.append(
                ("parent_child", kind, person_id, rel["child"])
            )
        elif rel["child"] == person_id and "parents" in active:
            neighbour_ids.append(rel["parent"])
            edge_defs.append(
                ("parent_child", kind, rel["parent"], person_id)
            )

    if "spouses" in active:
        for marriage in model["marriages"]:
            if marriage["person1"] == person_id:
                neighbour_ids.append(marriage["person2"])
                edge_defs.append(
                    _norm(
                        "marriage",
                        marriage.get("status", "married"),
                        person_id,
                        marriage["person2"],
                    )
                )
            elif marriage["person2"] == person_id:
                neighbour_ids.append(marriage["person1"])
                edge_defs.append(
                    _norm(
                        "marriage",
                        marriage.get("status", "married"),
                        person_id,
                        marriage["person1"],
                    )
                )

    if "siblings" in active:
        for group in model.get("sibling_groups", []):
            if person_id in group["members"]:
                for member in group["members"]:
                    if member != person_id:
                        neighbour_ids.append(member)
                        edge_defs.append(
                            _norm(
                                "sibling_group",
                                group.get("type") or "sibling",
                                person_id,
                                member,
                            )
                        )
        # Biological siblings without an explicit group.
        def bio_parents(pid: str):
            return {
                rel["parent"]
                for rel in model["parent_child"]
                if rel["child"] == pid and rel.get("kind") == "biological"
            }

        own_parents = bio_parents(person_id)
        if own_parents:
            for other in model["people"]:
                if other["id"] == person_id:
                    continue
                if bio_parents(other["id"]) == own_parents:
                    neighbour_ids.append(other["id"])
                    edge_defs.append(
                        _norm(
                            "sibling_group",
                            "biological",
                            person_id,
                            other["id"],
                        )
                    )

    node_ids = [person_id]
    if "general" in active:
        connection = None
        try:
            from ... import db

            connection = db.get_connection()
            rows = connection.execute(
                """
                SELECT * FROM general_relationships
                WHERE person_a = ? OR person_b = ?
                """,
                (person_id, person_id),
            ).fetchall()
        finally:
            if connection is not None:
                connection.close()
        for row in rows:
            other = (
                row["person_b"]
                if row["person_a"] == person_id
                else row["person_a"]
            )
            neighbour_ids.append(other)
            edge_defs.append(
                _norm("general", row["type"], person_id, other)
            )

    # Deduplicate while preserving deterministic order.
    seen_nodes = set(node_ids)
    ordered_nodes = list(node_ids)
    for neighbour_id in neighbour_ids:
        if neighbour_id not in seen_nodes:
            seen_nodes.add(neighbour_id)
            ordered_nodes.append(neighbour_id)

    # Context edges among the returned set (couples, sibling groups, general).
    neighbour_set = set(ordered_nodes)
    for marriage in model["marriages"]:
        a, b = marriage["person1"], marriage["person2"]
        if {a, b} <= neighbour_set:
            candidate = _norm(
                "marriage", marriage.get("status", "married"), a, b
            )
            if candidate not in edge_defs:
                edge_defs.append(candidate)
    if active & FAMILY_FILTERS:
        for group in model.get("sibling_groups", []):
            members = group["members"]
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    if {a, b} <= neighbour_set:
                        candidate = _norm(
                            "sibling_group",
                            group.get("type") or "sibling",
                            a,
                            b,
                        )
                        if candidate not in edge_defs:
                            edge_defs.append(candidate)
    if "general" in active:
        connection = None
        try:
            from ... import db

            connection = db.get_connection()
            rows = connection.execute(
                """
                SELECT person_a, person_b, type FROM general_relationships
                """
            ).fetchall()
        finally:
            if connection is not None:
                connection.close()
        for row in rows:
            a, b = row["person_a"], row["person_b"]
            if {a, b} <= neighbour_set:
                candidate = _norm("general", row["type"], a, b)
                if candidate not in edge_defs:
                    edge_defs.append(candidate)

    nodes = []
    for neighbour_id in ordered_nodes:
        node = _person_brief(index[neighbour_id])
        node["is_perspective"] = neighbour_id == perspective_id
        relation = _relation_to(model, index, perspective_id, neighbour_id)
        if relation:
            node["relation_label_en"] = relation["label_en"]
            node["relation_label_ur"] = relation["label_ur"]
        nodes.append(node)

    edges = []
    seen_edges = set()
    for edge_type, subtype, source, target in edge_defs:
        if (edge_type, subtype, source, target) in seen_edges:
            continue
        seen_edges.add((edge_type, subtype, source, target))
        edges.append(
            {
                "id": _edge_id(edge_type, subtype, source, target),
                "source": source,
                "target": target,
                "domain": "general"
                if edge_type == "general"
                else "family",
                "type": edge_type,
                "subtype": subtype,
            }
        )
    return {
        "center": _person_brief(index[person_id]),
        "perspective": _person_brief(index[perspective_id]),
        "filters": sorted(active),
        "nodes": nodes,
        "edges": edges,
    }
