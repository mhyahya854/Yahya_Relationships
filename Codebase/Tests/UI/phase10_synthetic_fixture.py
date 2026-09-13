"""Bulk-load and certify the isolated Phase 10 visual-review family.

The normal family write service deliberately runs regression assertions for the
real, frozen family.  A synthetic model cannot satisfy those name-specific
assertions, so this test-only loader writes canonical fact rows once and then
uses the production validator, kinship/path engine, and Mermaid audit before UI
capture starts.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict, deque
from pathlib import Path

from app.backend.domain.family import engine
from app.backend.domain.relationships import path_service
from app.backend.model import load_model, validate_model


REQUIRED_PARENT_KINDS = {
    "biological",
    "adopted",
    "step",
    "foster",
    "guardian",
    "unknown",
}


def _generation_count(model: dict) -> int:
    """Return the longest parent-to-child chain in the validated DAG."""
    children: dict[str, list[str]] = defaultdict(list)
    indegree = {person["id"]: 0 for person in model["people"]}
    for fact in model["parent_child"]:
        children[fact["parent"]].append(fact["child"])
        indegree[fact["child"]] += 1

    depth = {person_id: 1 for person_id in indegree}
    queue = deque(person_id for person_id, degree in indegree.items() if degree == 0)
    while queue:
        parent = queue.popleft()
        for child in children[parent]:
            depth[child] = max(depth[child], depth[parent] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return max(depth.values(), default=0)


def _insert_facts(db_path: Path, fixture: dict) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            """
            INSERT INTO parent_child(parent_id, child_id, role, kind)
            VALUES (:parent, :child, :role, :kind)
            """,
            fixture["parent_child"],
        )
        connection.executemany(
            """
            INSERT INTO marriages(
              spouse_a, spouse_b, status, year, children_status, display_order
            ) VALUES (:spouse_a, :spouse_b, :status, :year, :children_status, :display_order)
            """,
            fixture["marriages"],
        )
        for display_order, group in enumerate(fixture["sibling_groups"]):
            connection.execute(
                """
                INSERT INTO sibling_groups(
                  id, is_ordered, type, label_en, label_ur, display_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    group["id"],
                    int(group["ordered"]),
                    group.get("type"),
                    group.get("label_en"),
                    group.get("label_ur"),
                    display_order,
                ),
            )
            connection.executemany(
                """
                INSERT INTO sibling_group_members(group_id, person_id, member_order)
                VALUES (?, ?, ?)
                """,
                [
                    (group["id"], person_id, index if group["ordered"] else None)
                    for index, person_id in enumerate(group["members"], start=1)
                ],
            )


def main() -> None:
    db_path = Path(sys.argv[1]).resolve()
    fixture = json.load(sys.stdin)
    _insert_facts(db_path, fixture)

    model = load_model(db_path)
    validate_model(model)
    mermaid = engine.build_mermaid(model)
    engine.audit_render_mapping(model, mermaid)

    parent_kinds = {fact["kind"] for fact in model["parent_child"]}
    generations = _generation_count(model)
    paths = path_service.get_relationship_paths(
        fixture["multipath"]["from"],
        fixture["multipath"]["to"],
        max_depth=15,
        max_paths=50,
    )["paths"]
    path_sides = {path.get("side") for path in paths}

    assert 45 <= len(model["people"]) <= 70
    assert generations >= 5
    assert len(model["marriages"]) >= 12
    assert len(model["sibling_groups"]) >= 6
    assert REQUIRED_PARENT_KINDS <= parent_kinds
    assert len(paths) >= 2
    assert {"maternal", "paternal"} <= path_sides

    print(json.dumps({
        "people": len(model["people"]),
        "generations": generations,
        "parent_child": len(model["parent_child"]),
        "parent_kinds": sorted(parent_kinds),
        "marriages": len(model["marriages"]),
        "sibling_groups": len(model["sibling_groups"]),
        "multipath_paths": len(paths),
        "multipath_sides": sorted(side for side in path_sides if side),
        "mermaid_bytes": len(mermaid.encode("utf-8")),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
