"""Consequence Preview Engine for proposed relationship & family graph mutations.

Performs a deterministic, in-memory / transactional dry-run without committing
any changes to disk. Uses the canonical Python kinship engine to compute
derived relationship diffs and validate semantic constraints (e.g. cycles).
"""

from __future__ import annotations

import copy
import sqlite3
from typing import Any

from ..family import engine as build_family
from ..relationships import path_service

from ... import db
from ...kinship import labels
from ...model import _model_from_connection, people_index, run_family_audits, validate_model
from ...services import errors


def _get_all_derived_map(model: dict) -> dict[tuple[str, str], list[dict]]:
    """Map (person_a_id, person_b_id) -> list of derived family relationship path payloads."""
    idx = people_index(model)
    rel_map: dict[tuple[str, str], list[dict]] = {}
    pids = sorted(idx.keys())

    explicit_sibling_pairs = set()
    for g in model.get("sibling_groups", []):
        members = g.get("members", [])
        for i, m1 in enumerate(members):
            for m2 in members[i + 1:]:
                explicit_sibling_pairs.add((m1, m2))
                explicit_sibling_pairs.add((m2, m1))

    for pid_a in pids:
        for pid_b in pids:
            if pid_a == pid_b:
                continue
            is_explicit_sib = (pid_a, pid_b) in explicit_sibling_pairs
            pair_items: list[dict] = []

            # 1. Primary explicit facts from canonical engine (marriage, parent-child, explicit sibling)
            entries = build_family._pair_relationship_entries(model, pid_a, pid_b, idx)
            for item in entries:
                if item.get("group") == "primary":
                    pair_items.append(
                        {
                            "id": f"primary:{item.get('kind', 'fact')}:{pid_a}:{pid_b}:{item.get('role', '')}:{item.get('suffix', '')}:{item.get('stored_fact_kind', '')}",
                            "person_a_id": pid_a,
                            "person_b_id": pid_b,
                            "relationship_type": item.get("kind", "primary"),
                            "semantic_id": item.get("kind", "primary"),
                            "label_en": item["en"],
                            "label_ur": item.get("ur"),
                            "side": item.get("side", ""),
                            "degree": item.get("degree"),
                            "removal": item.get("removal"),
                            "distance": item.get("distance", 1),
                            "nodes": [pid_a, pid_b],
                            "derived": item.get("derived", False),
                        }
                    )

            # 2. All distinct derived structural kinship paths (ancestors, descendants, collateral, cousins)
            derived = path_service._derived_paths(
                model=model,
                people_index=idx,
                perspective_id=pid_a,
                target_id=pid_b,
                explicit_sibling=is_explicit_sib,
                max_depth=10,
            )
            for dp in derived:
                pair_items.append(
                    {
                        "id": dp["id"],
                        "person_a_id": pid_a,
                        "person_b_id": pid_b,
                        "relationship_type": dp.get("relationship_type", dp.get("type")),
                        "semantic_id": dp.get("semantic_id", dp.get("relationship_type", dp.get("type"))),
                        "label_en": dp["label_en"],
                        "label_ur": dp.get("label_ur"),
                        "side": dp.get("side", ""),
                        "degree": dp.get("degree"),
                        "removal": dp.get("removal"),
                        "distance": dp.get("distance"),
                        "nodes": [node["id"] if isinstance(node, dict) else str(node) for node in dp.get("nodes", [])],
                        "derived": True,
                    }
                )

            # 3. Inferred biological siblinghood when shared parents exist without explicit group
            if not is_explicit_sib:
                shared_parents = path_service._same_parents(model, idx, pid_a, pid_b)
                if shared_parents:
                    target_g = path_service._gender_of(idx, pid_b)
                    en = "Sister" if target_g == "female" else "Brother"
                    ur = "بہن" if target_g == "female" else "بھائی"
                    entry = labels.normalize_family_entry({
                        "en": en,
                        "ur": ur,
                        "kind": "sibling",
                        "target_gender": target_g,
                        "explicit_full": False,
                        "sibling_type": "biological",
                        "stored_fact_kind": None,
                        "derived": True,
                    })
                    parents_by_gender = sorted(
                        shared_parents,
                        key=lambda p_id: (
                            0 if path_service._gender_of(idx, p_id) == "female" else 1,
                            p_id,
                        ),
                    )
                    for parent_id in parents_by_gender[:1]:
                        sib_payload = path_service._path_payload(
                            domain="family",
                            entry=entry,
                            node_ids=[pid_a, parent_id, pid_b],
                            model=model,
                            people_index=idx,
                            common_ancestors=shared_parents,
                            derived=True,
                        )
                        pair_items.append(
                            {
                                "id": sib_payload["id"],
                                "person_a_id": pid_a,
                                "person_b_id": pid_b,
                                "relationship_type": "sibling",
                                "semantic_id": "sibling",
                                "label_en": sib_payload["label_en"],
                                "label_ur": sib_payload.get("label_ur"),
                                "side": "",
                                "degree": None,
                                "removal": None,
                                "distance": 2,
                                "nodes": [node["id"] if isinstance(node, dict) else str(node) for node in sib_payload.get("nodes", [])],
                                "derived": True,
                            }
                        )

            if pair_items:
                pair_items.sort(
                    key=lambda p: (
                        p.get("distance", 0),
                        p.get("degree") if p.get("degree") is not None else 99,
                        p.get("removal") if p.get("removal") is not None else 99,
                        p.get("relationship_type", ""),
                        p.get("id", ""),
                    )
                )
                rel_map[(pid_a, pid_b)] = pair_items
    return rel_map


def preview_mutation(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Calculate the exact consequence diff of a proposed mutation without saving.

    Returns:
    {
      "valid": bool,
      "code": str | None,
      "message": str | None,
      "direct_changes": list[str],
      "derived_added": list[dict],
      "derived_removed": list[dict],
      "warnings": list[str]
    }
    """
    connection = db.get_connection()
    try:
        # 1. Capture baseline model and relationship map
        baseline_model = _model_from_connection(connection)
        idx_before = people_index(baseline_model)
        map_before = _get_all_derived_map(baseline_model)

        # 2. Begin transaction for dry-run
        connection.execute("BEGIN")

        direct_changes: list[str] = []
        warnings: list[str] = []

        try:
            if action == "add_parent_child":
                parent_id = params["parent_id"]
                child_id = params["child_id"]
                role = params.get("role", "parent")
                kind = params.get("kind", "biological")
                if kind not in {"biological", "unspecified", "adopted", "foster", "guardian", "step", "unknown"}:
                    raise errors.ValidationError(f"Unsupported parent-child kind: {kind!r}.")
                if role not in {"mother", "father", "parent", "unknown"}:
                    raise errors.ValidationError(f"Unsupported parent role: {role!r}.")
                if parent_id not in idx_before:
                    raise errors.NotFoundError(f"Unknown parent ID: {parent_id}")
                if child_id not in idx_before:
                    raise errors.NotFoundError(f"Unknown child ID: {child_id}")
                if parent_id == child_id:
                    raise errors.ValidationError(
                        "A person cannot be their own parent.", code="SELF_PARENT"
                    )
                existing = connection.execute(
                    "SELECT 1 FROM parent_child WHERE parent_id = ? AND child_id = ?",
                    (parent_id, child_id),
                ).fetchone()
                if existing:
                    raise errors.ValidationError(
                        "That parent-child fact already exists.", code="DUPLICATE_FACT"
                    )
                connection.execute(
                    """
                    INSERT INTO parent_child (parent_id, child_id, role, kind)
                    VALUES (?, ?, ?, ?)
                    """,
                    (parent_id, child_id, role, kind),
                )
                parent_name = idx_before[parent_id]["name"]
                child_name = idx_before[child_id]["name"]
                direct_changes.append(
                    f"{child_name} becomes {parent_name}'s {kind} child."
                )

            elif action == "delete_parent_child":
                parent_id = params["parent_id"]
                child_id = params["child_id"]
                cursor = connection.execute(
                    "DELETE FROM parent_child WHERE parent_id = ? AND child_id = ?",
                    (parent_id, child_id),
                )
                if cursor.rowcount == 0:
                    raise errors.NotFoundError("Parent-child fact not found.")
                parent_name = idx_before.get(parent_id, {}).get("name", parent_id)
                child_name = idx_before.get(child_id, {}).get("name", child_id)
                direct_changes.append(
                    f"Remove parent-child relationship between {parent_name} and {child_name}."
                )

            elif action == "update_parent_child":
                parent_id = params["parent_id"]
                child_id = params["child_id"]
                role = params.get("role")
                kind = params.get("kind")
                row = connection.execute(
                    "SELECT role, kind FROM parent_child WHERE parent_id = ? AND child_id = ?",
                    (parent_id, child_id),
                ).fetchone()
                if not row:
                    raise errors.NotFoundError("Parent-child fact not found.")
                new_role = role if role is not None else row["role"]
                new_kind = kind if kind is not None else row["kind"]
                connection.execute(
                    "UPDATE parent_child SET role = ?, kind = ? WHERE parent_id = ? AND child_id = ?",
                    (new_role, new_kind, parent_id, child_id),
                )
                parent_name = idx_before.get(parent_id, {}).get("name", parent_id)
                child_name = idx_before.get(child_id, {}).get("name", child_id)
                direct_changes.append(
                    f"Update parent-child between {parent_name} and {child_name} to {new_kind} ({new_role})."
                )

            elif action == "add_marriage":
                person_a = params.get("person_a") or params.get("spouse_a")
                person_b = params.get("person_b") or params.get("spouse_b")
                status = params.get("status", "married")
                year = params.get("year")
                children_status = params.get("children_status") or None
                if status not in {"married", "divorced", "widowed", "unknown"}:
                    raise errors.ValidationError(f"Unsupported marriage status: {status!r}.")
                if not person_a or not person_b:
                    raise errors.ValidationError("Both spouses must be specified.")
                if person_a not in idx_before or person_b not in idx_before:
                    raise errors.NotFoundError("Unknown spouse ID.")
                if person_a == person_b:
                    raise errors.ValidationError(
                        "A person cannot marry themselves.", code="SELF_MARRIAGE"
                    )
                spouse_a, spouse_b = sorted((person_a, person_b))
                existing = connection.execute(
                    "SELECT 1 FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
                    (spouse_a, spouse_b),
                ).fetchone()
                if existing:
                    raise errors.ValidationError(
                        "That marriage fact already exists.", code="DUPLICATE_FACT"
                    )
                for sp in (spouse_a, spouse_b):
                    sp_row = connection.execute("SELECT marital_status FROM people WHERE id = ?", (sp,)).fetchone()
                    if sp_row and sp_row["marital_status"] == "single":
                        raise errors.ValidationError(
                            f"Person {sp} is marked single and cannot have a marriage fact.",
                            code="FAMILY_VALIDATION",
                        )
                max_order = connection.execute(
                    "SELECT COALESCE(MAX(display_order), -1) AS m FROM marriages"
                ).fetchone()["m"]
                connection.execute(
                    """
                    INSERT INTO marriages (spouse_a, spouse_b, status, year, children_status, display_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (spouse_a, spouse_b, status, year, children_status, int(max_order) + 1),
                )
                name_a = idx_before[spouse_a]["name"]
                name_b = idx_before[spouse_b]["name"]
                direct_changes.append(f"Add marriage between {name_a} and {name_b}.")

            elif action == "delete_marriage":
                person_a = params.get("person_a") or params.get("spouse_a")
                person_b = params.get("person_b") or params.get("spouse_b")
                if not person_a or not person_b:
                    raise errors.ValidationError("Both spouses must be specified.")
                spouse_a, spouse_b = sorted((person_a, person_b))
                cursor = connection.execute(
                    "DELETE FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
                    (spouse_a, spouse_b),
                )
                if cursor.rowcount == 0:
                    raise errors.NotFoundError("Marriage fact not found.")
                name_a = idx_before.get(spouse_a, {}).get("name", spouse_a)
                name_b = idx_before.get(spouse_b, {}).get("name", spouse_b)
                direct_changes.append(f"Remove marriage between {name_a} and {name_b}.")

            elif action == "update_marriage":
                person_a = params.get("person_a") or params.get("spouse_a")
                person_b = params.get("person_b") or params.get("spouse_b")
                if not person_a or not person_b:
                    raise errors.ValidationError("Both spouses must be specified.")
                spouse_a, spouse_b = sorted((person_a, person_b))
                row = connection.execute(
                    "SELECT * FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
                    (spouse_a, spouse_b),
                ).fetchone()
                if not row:
                    raise errors.NotFoundError("Marriage fact not found.")
                new_status = params["status"] if "status" in params and params["status"] is not None else row["status"]
                new_year = params["year"] if "year" in params else row["year"]
                new_children_status = (params["children_status"] or None) if "children_status" in params else row["children_status"]
                connection.execute(
                    """
                    UPDATE marriages
                    SET status = ?, year = ?, children_status = ?
                    WHERE spouse_a = ? AND spouse_b = ?
                    """,
                    (new_status, new_year, new_children_status, spouse_a, spouse_b),
                )
                name_a = idx_before.get(spouse_a, {}).get("name", spouse_a)
                name_b = idx_before.get(spouse_b, {}).get("name", spouse_b)
                direct_changes.append(
                    f"Update marriage between {name_a} and {name_b}: status={new_status}, year={new_year}."
                )

            elif action == "add_sibling_group":
                member_ids = [m for m in (params.get("member_ids") or params.get("members") or []) if m]
                type_ = params.get("type_") or params.get("type") or None
                if type_ == "":
                    type_ = None
                ordered = bool(params.get("ordered", False))
                if len(member_ids) < 2:
                    raise errors.ValidationError(
                        "A sibling group needs at least two members.", code="SIBLING_GROUP_SIZE"
                    )
                if len(set(member_ids)) != len(member_ids):
                    raise errors.ValidationError(
                        "A sibling group cannot repeat a person.", code="SIBLING_GROUP_REPEAT"
                    )
                if type_ not in (None, "full"):
                    raise errors.ValidationError(
                        f"Unsupported sibling-group type: {type_!r}."
                    )
                if type_ == "full" and len(member_ids) != 2:
                    raise errors.ValidationError(
                        "Full-sibling facts need exactly two members.",
                        code="FULL_SIBLING_SIZE",
                    )
                for member in member_ids:
                    if member not in idx_before:
                        raise errors.NotFoundError(f"Unknown sibling group member: {member}")
                for group in connection.execute("SELECT id FROM sibling_groups").fetchall():
                    stored = [
                        row["person_id"]
                        for row in connection.execute(
                            "SELECT person_id FROM sibling_group_members WHERE group_id = ? ORDER BY member_order, person_id",
                            (group["id"],),
                        )
                    ]
                    if sorted(stored) == sorted(member_ids):
                        raise errors.ValidationError(
                            "That sibling group already exists.", code="DUPLICATE_FACT"
                        )
                max_order = connection.execute(
                    "SELECT COALESCE(MAX(display_order), -1) AS m FROM sibling_groups"
                ).fetchone()["m"]
                group_id = f"sib_{'_'.join(member_ids)}"
                connection.execute(
                    """
                    INSERT INTO sibling_groups (id, is_ordered, type, display_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (group_id, 1 if ordered else 0, type_, int(max_order) + 1),
                )
                for idx, mid in enumerate(member_ids, start=1):
                    connection.execute(
                        """
                        INSERT INTO sibling_group_members (group_id, person_id, member_order)
                        VALUES (?, ?, ?)
                        """,
                        (group_id, mid, idx if ordered else None),
                    )
                member_names = [idx_before[m]["name"] for m in member_ids if m in idx_before]
                direct_changes.append(f"Create sibling fact between: {', '.join(member_names)}.")

            elif action == "delete_sibling_group":
                group_id = params["group_id"]
                connection.execute("DELETE FROM sibling_group_members WHERE group_id = ?", (group_id,))
                cursor = connection.execute("DELETE FROM sibling_groups WHERE id = ?", (group_id,))
                if cursor.rowcount == 0:
                    raise errors.NotFoundError("Sibling group not found.")
                direct_changes.append(f"Remove sibling group fact ({group_id}).")

            elif action == "update_sibling_group":
                group_id = params["group_id"]
                type_ = params.get("type_")
                if type_ is None and "type" in params:
                    type_ = params["type"]
                ordered = params.get("ordered")
                row = connection.execute("SELECT * FROM sibling_groups WHERE id = ?", (group_id,)).fetchone()
                if not row:
                    raise errors.NotFoundError("Sibling group not found.")
                members = [
                    r["person_id"]
                    for r in connection.execute(
                        "SELECT person_id FROM sibling_group_members WHERE group_id = ? ORDER BY member_order, person_id",
                        (group_id,),
                    ).fetchall()
                ]
                new_type = (type_ or None) if type_ is not None else row["type"]
                if new_type == "full" and len(members) != 2:
                    raise errors.ValidationError("Full-sibling facts need exactly two members.", code="FULL_SIBLING_SIZE")
                new_ordered = ordered if ordered is not None else bool(row["is_ordered"])
                connection.execute(
                    "UPDATE sibling_groups SET type = ?, is_ordered = ? WHERE id = ?",
                    (new_type, 1 if new_ordered else 0, group_id),
                )
                if new_ordered:
                    for idx, mid in enumerate(members, start=1):
                        connection.execute(
                            "UPDATE sibling_group_members SET member_order = ? WHERE group_id = ? AND person_id = ?",
                            (idx, group_id, mid),
                        )
                else:
                    connection.execute(
                        "UPDATE sibling_group_members SET member_order = NULL WHERE group_id = ?",
                        (group_id,),
                    )
                direct_changes.append(f"Update sibling group fact ({group_id}): type={new_type or 'default'}, ordered={bool(new_ordered)}.")

            elif action == "delete_person":
                person_id = params["person_id"]
                p_name = idx_before.get(person_id, {}).get("name", person_id)
                # Check references
                pc_count = connection.execute(
                    "SELECT COUNT(*) FROM parent_child WHERE parent_id = ? OR child_id = ?",
                    (person_id, person_id),
                ).fetchone()[0]
                m_count = connection.execute(
                    "SELECT COUNT(*) FROM marriages WHERE spouse_a = ? OR spouse_b = ?",
                    (person_id, person_id),
                ).fetchone()[0]
                sib_count = connection.execute(
                    "SELECT COUNT(*) FROM sibling_group_members WHERE person_id = ?",
                    (person_id,),
                ).fetchone()[0]
                gen_count = connection.execute(
                    "SELECT COUNT(*) FROM general_relationships WHERE person_a = ? OR person_b = ?",
                    (person_id, person_id),
                ).fetchone()[0]

                if pc_count + m_count + sib_count > 0:
                    warnings.append(
                        f"{p_name} is referenced by {pc_count} parent-child, {m_count} marriage, and {sib_count} sibling facts. Remove those family facts before deleting."
                    )
                if gen_count > 0:
                    warnings.append(
                        f"Deleting {p_name} will also remove {gen_count} general relationships."
                    )
                direct_changes.append(f"Delete canonical person: {p_name}.")
                if pc_count > 0:
                    direct_changes.append(f"Remove {pc_count} parent-child facts.")
                if m_count > 0:
                    direct_changes.append(f"Remove {m_count} marriage facts.")
                if sib_count > 0:
                    direct_changes.append(f"Remove from {sib_count} sibling groups.")
                if gen_count > 0:
                    direct_changes.append(f"Remove {gen_count} general relationships.")
                direct_changes.append("Safely archive person folder and journal to Database/People/_archived/.")
                connection.execute("DELETE FROM general_relationships WHERE person_a = ? OR person_b = ?", (person_id, person_id))
                connection.execute("DELETE FROM parent_child WHERE parent_id = ? OR child_id = ?", (person_id, person_id))
                connection.execute("DELETE FROM marriages WHERE spouse_a = ? OR spouse_b = ?", (person_id, person_id))
                connection.execute("DELETE FROM sibling_group_members WHERE person_id = ?", (person_id,))
                connection.execute("DELETE FROM aliases WHERE person_id = ?", (person_id,))
                connection.execute("DELETE FROM person_groups WHERE person_id = ?", (person_id,))
                connection.execute("DELETE FROM people WHERE id = ?", (person_id,))

            elif action == "add_general":
                person_a = params["person_a"]
                person_b = params["person_b"]
                rel_type = params["type"]
                label_a = params.get("label_a_to_b") or rel_type
                name_a = idx_before.get(person_a, {}).get("name", person_a)
                name_b = idx_before.get(person_b, {}).get("name", person_b)
                direct_changes.append(f"Add general relationship '{label_a}' between {name_a} and {name_b}.")

            elif action == "delete_general":
                rel_id = params["relationship_id"]
                direct_changes.append(f"Remove general relationship ID #{rel_id}.")

            elif action == "update_general":
                rel_id = params["relationship_id"]
                row = connection.execute("SELECT * FROM general_relationships WHERE id = ?", (rel_id,)).fetchone()
                if not row:
                    raise errors.NotFoundError(f"General relationship #{rel_id} not found.")
                new_type = params["type"] if "type" in params and params["type"] is not None else row["type"]
                new_directionality = params["directionality"] if "directionality" in params and params["directionality"] is not None else row["directionality"]
                if new_directionality == "symmetric":
                    new_direction_from = None
                    if new_type != "custom":
                        from ...services.general import _default_label
                        canonical = _default_label(new_type)
                        new_label_a = canonical
                        new_label_b = canonical
                    else:
                        mutual = params.get("label_a_to_b") or params.get("label_b_to_a") or row["label_a_to_b"]
                        new_label_a = mutual
                        new_label_b = mutual
                else:
                    new_direction_from = params["direction_from"] if "direction_from" in params else (row["direction_from"] or row["person_a"])
                    new_label_a = params["label_a_to_b"] if "label_a_to_b" in params else row["label_a_to_b"]
                    new_label_b = params["label_b_to_a"] if "label_b_to_a" in params else row["label_b_to_a"]

                new_notes = params["notes"] if "notes" in params else row["notes"]
                connection.execute(
                    """
                    UPDATE general_relationships
                    SET type = ?, directionality = ?, direction_from = ?,
                        label_a_to_b = ?, label_b_to_a = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_type, new_directionality, new_direction_from, new_label_a, new_label_b, new_notes, db.utc_now(), rel_id),
                )
                name_a = idx_before.get(row["person_a"], {}).get("name", row["person_a"])
                name_b = idx_before.get(row["person_b"], {}).get("name", row["person_b"])
                direct_changes.append(f"Update general relationship between {name_a} and {name_b}: type={new_type}.")

            else:
                raise errors.ValidationError(f"Unknown action for preview: {action!r}")

            # 3. Validate updated model in dry-run
            updated_model = _model_from_connection(connection)
            validate_model(updated_model)
            run_family_audits(updated_model)

            # 4. Compare relationship snapshot before & after
            map_after = _get_all_derived_map(updated_model)
            idx_after = people_index(updated_model)

            derived_added = []
            derived_removed = []

            # Added relationships
            for pair, items in map_after.items():
                pid_a, pid_b = pair
                before_items = map_before.get(pair, [])
                before_keys = {item["id"] for item in before_items}
                for item in items:
                    if item["id"] not in before_keys:
                        derived_added.append(
                            {
                                "path_id": item["id"],
                                "person_a_id": pid_a,
                                "person_a_name": idx_after.get(pid_a, {}).get("name", pid_a),
                                "person_b_id": pid_b,
                                "person_b_name": idx_after.get(pid_b, {}).get("name", pid_b),
                                "relationship_type": item.get("relationship_type", item.get("type")),
                                "semantic_id": item.get("semantic_id", item.get("relationship_type", item.get("type"))),
                                "label_en": item["label_en"],
                                "label_ur": item.get("label_ur"),
                                "side": item.get("side", ""),
                                "degree": item.get("degree"),
                                "removal": item.get("removal"),
                                "distance": item.get("distance"),
                                "nodes": [node["id"] if isinstance(node, dict) else str(node) for node in item.get("nodes", [])],
                                "derived": True,
                            }
                        )

            # Removed relationships
            for pair, items in map_before.items():
                pid_a, pid_b = pair
                after_items = map_after.get(pair, [])
                after_keys = {item["id"] for item in after_items}
                for item in items:
                    if item["id"] not in after_keys:
                        derived_removed.append(
                            {
                                "path_id": item["id"],
                                "person_a_id": pid_a,
                                "person_a_name": idx_before.get(pid_a, {}).get("name", pid_a),
                                "person_b_id": pid_b,
                                "person_b_name": idx_before.get(pid_b, {}).get("name", pid_b),
                                "relationship_type": item.get("relationship_type", item.get("type")),
                                "semantic_id": item.get("semantic_id", item.get("relationship_type", item.get("type"))),
                                "label_en": item["label_en"],
                                "label_ur": item.get("label_ur"),
                                "side": item.get("side", ""),
                                "degree": item.get("degree"),
                                "removal": item.get("removal"),
                                "distance": item.get("distance"),
                                "nodes": [node["id"] if isinstance(node, dict) else str(node) for node in item.get("nodes", [])],
                                "derived": True,
                            }
                        )

            derived_added.sort(
                key=lambda x: (
                    x["person_a_id"],
                    x["person_b_id"],
                    x.get("distance", 0),
                    x.get("relationship_type", ""),
                    x.get("path_id", ""),
                )
            )
            derived_removed.sort(
                key=lambda x: (
                    x["person_a_id"],
                    x["person_b_id"],
                    x.get("distance", 0),
                    x.get("relationship_type", ""),
                    x.get("path_id", ""),
                )
            )

            return {
                "valid": True,
                "code": None,
                "message": None,
                "direct_changes": direct_changes,
                "derived_added": derived_added,
                "derived_removed": derived_removed,
                "warnings": warnings,
            }

        except errors.ValidationError as exc:
            return {
                "valid": False,
                "code": exc.code or "INVALID_MUTATION",
                "message": str(exc),
                "direct_changes": direct_changes,
                "derived_added": [],
                "derived_removed": [],
                "warnings": warnings,
            }
        except ValueError as exc:
            msg = str(exc)
            code = "ANCESTRY_CYCLE" if "cycle" in msg.lower() else "INVALID_FAMILY_GRAPH"
            return {
                "valid": False,
                "code": code,
                "message": msg,
                "direct_changes": direct_changes,
                "derived_added": [],
                "derived_removed": [],
                "warnings": warnings,
            }
        except Exception as exc:
            return {
                "valid": False,
                "code": "PREVIEW_ERROR",
                "message": str(exc),
                "direct_changes": direct_changes,
                "derived_added": [],
                "derived_removed": [],
                "warnings": warnings,
            }
        finally:
            connection.rollback()
    finally:
        connection.close()
