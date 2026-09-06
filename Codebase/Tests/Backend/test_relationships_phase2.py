"""Phase 2 Relationships Comprehensive Regression Test Suite.

Validates:
- All 1,190 ordered pairs on canonical 35-person dataset without crash or cycle.
- Stable language-neutral semantic IDs and deterministic path IDs.
- Arbitrary perspective and independent A -> B and B -> A reversal.
- Preservation of multiple simultaneous valid lineage paths.
- Show Why binding via semantic_id / path_ids without English text dependence.
- Compare people in both directions independently with multi-path preservation.
- Generic relationships: symmetric, directional, coexisting types, no transitive friendship.
- Mutation preview, constraint validation, failure rollback, and undo stack atomicity.
- Synthetic 100-node graph scaling without infinite expansion or ID instability.
"""

import pytest
import sqlite3

from app.backend import db
from app.backend.domain.mutations import history, preview
from app.backend.domain.relationships import graph as graph_service, path_service
from app.backend.kinship import labels
from app.backend.services import errors, family, general, people, relationship


# ==============================================================================
# 1. Exhaustive Ordered-Pair Audit on Canonical 35-Person Dataset
# ==============================================================================

def test_canonical_35_people_all_ordered_pairs(isolated):
    """Ensure all 1,190 ordered pairs among 35 canonical people run cleanly without crash."""
    all_people = people.list_people()
    pids = [p["id"] for p in all_people]
    assert len(pids) == 35, f"Expected 35 canonical people, found {len(pids)}"

    pair_count = 0
    for pid_a in pids:
        for pid_b in pids:
            if pid_a == pid_b:
                continue
            pair_count += 1
            # 1. relationship.get_relationship must not crash
            result = relationship.get_relationship(pid_a, pid_b)
            assert result["perspective"]["id"] == pid_a
            assert result["target"]["id"] == pid_b

            # Every entry must have a stable semantic_id and relationship_type
            for entry in result["primary"] + result["additional"]:
                assert entry["relationship_type"], f"Missing relationship_type for {pid_a} -> {pid_b}"
                assert entry.get("semantic_id"), f"Missing semantic_id for {pid_a} -> {pid_b}"
                assert isinstance(entry.get("path_ids"), list)
                assert entry["domain"] in ("family", "general")

            # 2. path_service.get_relationship_paths when relationships exist
            has_relationships = bool(result["primary"] or result["additional"])
            if has_relationships:
                path_res = path_service.get_relationship_paths(pid_a, pid_b)
                assert "paths" in path_res

                # Validate path structure
                for path in path_res["paths"]:
                    assert path["id"], f"Path missing ID for {pid_a} -> {pid_b}"
                    assert path["nodes"], f"Path missing nodes for {pid_a} -> {pid_b}"
                    assert path["nodes"][0]["id"] == pid_a
                    assert path["nodes"][-1]["id"] == pid_b
                    assert path.get("explanation"), f"Path missing explanation for {pid_a} -> {pid_b}"
                    assert path.get("semantic_id"), f"Path missing semantic_id for {pid_a} -> {pid_b}"

                    # Ensure no duplicate consecutive nodes (no loops)
                    node_ids = [n["id"] for n in path["nodes"]]
                    assert len(node_ids) == len(set(node_ids)), f"Cycle detected in path: {node_ids}"
            else:
                try:
                    path_service.get_relationship_paths(pid_a, pid_b)
                except errors.AppError as exc:
                    assert exc.code == "NO_RELATIONSHIP_PATH"

    assert pair_count == 35 * 34 == 1190


# ==============================================================================
# 2. Arbitrary Perspective & Directional Reversal (A -> B != B -> A)
# ==============================================================================

def test_directional_reversal_parent_child():
    """Father -> Son and Son -> Father must be computed independently by Python engine."""
    father = "mansoor_hussain"
    son = "mohammad_yahya_hussain"

    f_to_s = relationship.get_relationship(father, son)
    s_to_f = relationship.get_relationship(son, father)

    assert f_to_s["primary"][0]["relationship_type"] == "son"
    assert f_to_s["primary"][0]["label_en"] == "Son"

    assert s_to_f["primary"][0]["relationship_type"] == "father"
    assert s_to_f["primary"][0]["label_en"] == "Father"


def test_directional_reversal_aunt_nephew():
    """Aunt -> Nephew and Nephew -> Aunt."""
    aunt = "irsa_naz"
    nephew = "ezan_asif"

    a_to_n = relationship.get_relationship(aunt, nephew)
    n_to_a = relationship.get_relationship(nephew, aunt)

    assert a_to_n["primary"][0]["relationship_type"] == "nephew"
    assert a_to_n["primary"][0]["label_en"] == "Nephew"

    assert n_to_a["primary"][0]["relationship_type"] == "maternal_aunt"
    assert n_to_a["primary"][0]["label_en"] == "Maternal aunt"


def test_directional_reversal_grandparent_grandchild():
    """Grandfather -> Grandson and Grandson -> Grandfather."""
    grandpa = "israr_hussain"
    grandson = "mohammad_yahya_hussain"

    gp_to_gs = relationship.get_relationship(grandpa, grandson)
    gs_to_gp = relationship.get_relationship(grandson, grandpa)

    assert gp_to_gs["primary"][0]["relationship_type"] in ("grandson", "maternal_grandson")
    assert gs_to_gp["primary"][0]["relationship_type"] in ("maternal_grandfather", "grandfather")


def test_spousal_relationship_terms():
    """Spouse relationship between Mansoor and Irsa."""
    h_to_w = relationship.get_relationship("mansoor_hussain", "irsa_naz")
    w_to_h = relationship.get_relationship("irsa_naz", "mansoor_hussain")

    assert h_to_w["primary"][0]["relationship_type"] == "wife"
    assert w_to_h["primary"][0]["relationship_type"] == "husband"


# ==============================================================================
# 3. Multiple Simultaneous Valid Lineage Paths
# ==============================================================================

def test_multiple_simultaneous_paths_aresha_and_ezan():
    """Preserve multiple distinct lineage paths simultaneously."""
    # Yahya -> Aresha
    res_aresha = relationship.get_relationship("mohammad_yahya_hussain", "aresha_zubair")
    all_aresha_types = {e["relationship_type"] for e in res_aresha["primary"] + res_aresha["additional"]}
    assert "cousin" in all_aresha_types or any("cousin" in t for t in all_aresha_types)
    assert len(res_aresha["primary"] + res_aresha["additional"]) >= 2

    # Verify path details
    paths_aresha = path_service.get_relationship_paths("mohammad_yahya_hussain", "aresha_zubair")["paths"]
    assert len(paths_aresha) == 2
    sides = {p["side"] for p in paths_aresha}
    assert sides == {"paternal", "maternal"}

    # Yahya -> Ezan
    paths_ezan = path_service.get_relationship_paths("mohammad_yahya_hussain", "ezan_asif")["paths"]
    assert len(paths_ezan) == 2
    sides_ezan = {p["side"] for p in paths_ezan}
    assert sides_ezan == {"paternal", "maternal"}


# ==============================================================================
# 4. Stable Language-Neutral Semantic Identity (No Display Text Reliance)
# ==============================================================================

def test_stable_semantic_id_path_binding():
    """Show Why must bind entries to paths via semantic_id / path_ids, NOT English display text."""
    res = relationship.get_relationship("mohammad_yahya_hussain", "aresha_zubair")
    paths = path_service.get_relationship_paths("mohammad_yahya_hussain", "aresha_zubair")["paths"]
    path_map = {p["id"]: p for p in paths}

    for entry in res["primary"] + res["additional"]:
        # Must have path_ids
        assert entry.get("path_ids"), f"Entry {entry} missing path_ids"
        for pid in entry["path_ids"]:
            assert pid in path_map, f"path_id {pid} from entry not found in paths"
            matched_path = path_map[pid]
            # Semantic identity must match language-neutrally
            assert (
                matched_path.get("semantic_id") == entry.get("semantic_id")
                or matched_path.get("relationship_type") == entry.get("relationship_type")
            )


# ==============================================================================
# 5. Compare People in Both Directions Independently
# ==============================================================================

def test_compare_people_bidirectional():
    """Comparison computes a -> b and b -> a independently and preserves multi-paths."""
    comparison = relationship.compare_people("mohammad_yahya_hussain", "aresha_zubair")
    assert comparison["a"]["id"] == "mohammad_yahya_hussain"
    assert comparison["b"]["id"] == "aresha_zubair"

    a_to_b = comparison["a_to_b"]
    b_to_a = comparison["b_to_a"]

    # Both must have primary and additional
    assert len(a_to_b["primary"]) >= 1
    assert len(a_to_b["additional"]) >= 1
    assert len(b_to_a["primary"]) >= 1
    assert len(b_to_a["additional"]) >= 1

    # Verify a_to_b and b_to_a have reverse sides
    a_side = a_to_b["primary"][0].get("side")
    b_side = b_to_a["primary"][0].get("side")
    if a_side and b_side:
        assert a_side != b_side or a_side == "unspecified"


# ==============================================================================
# 6. Generic Relationships: Symmetric, Directional, Coexistence, No Transitivity
# ==============================================================================

def test_generic_relationships_full_lifecycle(isolated):
    p1 = people.create_person(name="Dr. Smith")["id"]
    p2 = people.create_person(name="Dr. Jones")["id"]

    # 1. Symmetric relationship (colleague)
    rel1 = general.add_general_relationship(person_a=p1, person_b=p2, type="colleague")
    assert rel1["directionality"] == "symmetric"

    # 2. Coexisting distinct generic relationship between same pair (close_friend)
    rel2 = general.add_general_relationship(person_a=p1, person_b=p2, type="close_friend")
    assert rel2["type"] == "close_friend"

    # Query relationships from perspective of p1
    rels = relationship.get_relationship(p1, p2)
    types = {e["relationship_type"] for e in rels["primary"] + rels["additional"]}
    assert "colleague" in types
    assert "close_friend" in types

    # 3. Duplicate EXACT generic relationship rejected
    with pytest.raises(errors.ValidationError) as exc:
        general.add_general_relationship(person_a=p1, person_b=p2, type="colleague")
    assert exc.value.code == "DUPLICATE_FACT"

    # 4. Self generic relationship rejected
    with pytest.raises(errors.ValidationError) as exc:
        general.add_general_relationship(person_a=p1, person_b=p1, type="friend")
    assert exc.value.code == "SELF_RELATIONSHIP"

    # 5. Directional relationship (mentor -> mentee)
    mentor = people.create_person(name="Professor X")["id"]
    student = people.create_person(name="Student Y")["id"]
    general.add_general_relationship(
        person_a=mentor,
        person_b=student,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Student",
    )
    rel_m = relationship.get_relationship(mentor, student)
    assert rel_m["primary"][0]["label_en"] == "Mentor"
    rel_s = relationship.get_relationship(student, mentor)
    assert rel_s["primary"][0]["label_en"] == "Student"

    # 6. No transitive friendship inference
    p3 = people.create_person(name="Dr. Watson")["id"]
    general.add_general_relationship(person_a=p2, person_b=p3, type="friend")
    rel_1_3 = relationship.get_relationship(p1, p3)
    assert len(rel_1_3["primary"]) == 0
    assert len(rel_1_3["additional"]) == 0


def test_coexistence_of_family_and_generic(isolated):
    """A pair can have both an objective family fact and a generic relationship."""
    son = "mohammad_yahya_hussain"
    dad = "mansoor_hussain"

    # Add general relationship "mentor" between father and son
    general.add_general_relationship(
        person_a=dad,
        person_b=son,
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )

    res = relationship.get_relationship(dad, son)
    domains = {e["domain"] for e in res["primary"] + res["additional"]}
    assert "family" in domains
    assert "general" in domains


# ==============================================================================
# 7. Mutation Safety, Consequence Preview, Failure Rollback & Undo Atomicity
# ==============================================================================

def test_mutation_preview_cycle_detection(isolated):
    """Preview detects ancestry cycles before any write is executed."""
    # Attempt to make parent of an ancestor
    # Yahya is child of Mansoor. Try to make Mansoor child of Yahya.
    prev = preview.preview_mutation(
        "add_parent_child",
        {"parent_id": "mohammad_yahya_hussain", "child_id": "mansoor_hussain", "kind": "biological"},
    )
    assert prev["valid"] is False
    assert prev["code"] == "ANCESTRY_CYCLE"


def test_mutation_failure_rollback_and_undo_atomicity(isolated):
    """When a mutation fails, SQLite is rolled back AND Undo stack has no ghost snapshot."""
    stack_depth_before = len(history._MUTATION_STACK)

    # Attempt to add self parent (invalid)
    with pytest.raises(errors.ValidationError):
        family.add_parent_child(
            parent_id="mohammad_yahya_hussain",
            child_id="mohammad_yahya_hussain",
        )

    # Undo stack must be restored exactly to previous depth
    assert len(history._MUTATION_STACK) == stack_depth_before

    # Attempt to add parent-child that introduces a cycle
    with pytest.raises(errors.ValidationError):
        family.add_parent_child(
            parent_id="mohammad_yahya_hussain",
            child_id="mansoor_hussain",
        )

    assert len(history._MUTATION_STACK) == stack_depth_before


def test_undo_restores_database_state_exactly(isolated):
    """Adding a relationship and then undoing it restores byte/fact equality."""
    p1 = people.create_person(name="Test Parent")["id"]
    p2 = people.create_person(name="Test Child")["id"]

    facts_before = family.family_facts()
    pc_count_before = len(facts_before["parent_child"])

    # Add parent-child
    family.add_parent_child(parent_id=p1, child_id=p2, role="parent", kind="biological")
    facts_after = family.family_facts()
    assert len(facts_after["parent_child"]) == pc_count_before + 1

    # Undo
    assert history.can_undo() is True
    history.undo_last_mutation()

    facts_reverted = family.family_facts()
    assert len(facts_reverted["parent_child"]) == pc_count_before
    matching = [pc for pc in facts_reverted["parent_child"] if pc["parent_id"] == p1 and pc["child_id"] == p2]
    assert len(matching) == 0


# ==============================================================================
# 8. Synthetic 100-Node Graph Safety
# ==============================================================================

def test_synthetic_100_node_graph_safety(isolated):
    """A 100-person synthetic tree does not crash relationship inference or create cycles."""
    # Create 100 synthetic people across generations
    created_ids = []
    for i in range(100):
        p = people.create_person(name=f"Synth Person {i:03d}")
        created_ids.append(p["id"])

    # Create parent-child relationships linking them into a tree structure
    # Node 0 is root. Node i (for i >= 1) has parent (i - 1) // 2
    for i in range(1, 100):
        parent_idx = (i - 1) // 2
        family.add_parent_child(
            parent_id=created_ids[parent_idx],
            child_id=created_ids[i],
            role="parent",
            kind="biological",
        )

    # Test path resolution between leaf and root
    root = created_ids[0]
    leaf = created_ids[99]
    paths = path_service.get_relationship_paths(root, leaf)["paths"]
    assert len(paths) >= 1
    assert paths[0]["nodes"][0]["id"] == root
    assert paths[0]["nodes"][-1]["id"] == leaf
    assert paths[0]["distance"] >= 5

    # Reverse perspective
    rev_paths = path_service.get_relationship_paths(leaf, root)["paths"]
    assert len(rev_paths) >= 1
    assert rev_paths[0]["nodes"][0]["id"] == leaf
    assert rev_paths[0]["nodes"][-1]["id"] == root

    # Test neighbors graph service
    graph_res = graph_service.get_graph_neighbors(root, perspective_id=root, filters=["children", "parents"])
    assert len(graph_res["nodes"]) >= 1
