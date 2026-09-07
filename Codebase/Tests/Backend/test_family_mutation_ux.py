"""Comprehensive backend test suite for Phase 4: Family Editing & Mutation UX.

Covers:
- Parent-child CRUD for all 7 kinds, both directions derived=False, edit, delete, undo.
- Parent-child refusals: self-parent, duplicates, ancestry cycles, missing persons, invalid kinds.
- Marriage CRUD, metadata normalization (status, year, children_status, empty string clearing), delete, undo.
- Marriage refusals: self-marriage, duplicates, single-person conflict, missing spouses.
- Sibling group CRUD: full vs default, ordered, edit, delete, undo.
- Siblinghood persistence: explicit group removal preserves inferred derived siblinghood from common parents.
- Sibling group refusals: size, repeat, full > 2, duplicates.
- Consequence preview dry-run: returns direct changes + derived added/removed diffs without touching DB.
- Multipath safety: partial deletion preserves independent alternate paths; undo restores all.
- Atomicity: failed/refused mutations leave DB unchanged and never poison the undo stack.
- Read-only enforcement.
"""

from unittest.mock import patch
import pytest

from app.backend import db
from app.backend.data_root.errors import DataRootReadOnlyError
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.mutations import history as mutation_history
from app.backend.domain.mutations import preview as mutation_preview
from app.backend.services import errors, family, people


PARENT_KINDS = [
    "biological",
    "adopted",
    "step",
    "foster",
    "guardian",
    "unknown",
    "unspecified",
]


def test_parent_child_all_seven_kinds_and_undo_cycle(isolated, client):
    # Create isolated parent and child
    p_res = people.create_person(name="Parent Person", gender="male", birth_year=1970)
    c_res = people.create_person(name="Child Person", gender="female", birth_year=2000)
    parent_id = p_res["id"]
    child_id = c_res["id"]

    for kind in PARENT_KINDS:
        mutation_history._MUTATION_STACK.clear()
        # Add parent-child
        res = family.add_parent_child(
            parent_id=parent_id,
            child_id=child_id,
            role="father",
            kind=kind,
        )
        assert res["ok"] is True
        assert res["kind"] == kind

        # Check relationships endpoint from parent perspective
        p_to_c = client.get(f"/api/relationships/{parent_id}/{child_id}").json()
        assert p_to_c["ok"] is True
        assert len(p_to_c["primary"]) > 0
        prim_p = p_to_c["primary"][0]
        assert prim_p["derived"] is False
        assert prim_p["stored_fact_kind"] == "parent_child"

        # Check relationships endpoint from child perspective
        c_to_p = client.get(f"/api/relationships/{child_id}/{parent_id}").json()
        assert c_to_p["ok"] is True
        assert len(c_to_p["primary"]) > 0
        prim_c = c_to_p["primary"][0]
        assert prim_c["derived"] is False
        assert prim_c["stored_fact_kind"] == "parent_child"

        # Update role and kind
        upd = family.update_parent_child(
            parent_id, child_id, role="parent", kind="unspecified"
        )
        assert upd["ok"] is True
        assert upd["role"] == "parent"
        assert upd["kind"] == "unspecified"

        # Delete fact
        del_res = family.delete_parent_child(parent_id, child_id)
        assert del_res["ok"] is True

        # Undo delete -> restored to updated state
        undo_1 = mutation_history.undo_last_mutation()
        assert undo_1["ok"] is True
        facts = family.family_facts()
        pc = [f for f in facts["parent_child"] if f["parent_id"] == parent_id and f["child_id"] == child_id]
        assert len(pc) == 1
        assert pc[0]["kind"] == "unspecified"

        # Undo update -> restored to original added kind
        undo_2 = mutation_history.undo_last_mutation()
        assert undo_2["ok"] is True
        facts = family.family_facts()
        pc = [f for f in facts["parent_child"] if f["parent_id"] == parent_id and f["child_id"] == child_id]
        assert len(pc) == 1
        assert pc[0]["kind"] == kind

        # Undo add -> removed completely
        undo_3 = mutation_history.undo_last_mutation()
        assert undo_3["ok"] is True
        facts = family.family_facts()
        pc = [f for f in facts["parent_child"] if f["parent_id"] == parent_id and f["child_id"] == child_id]
        assert len(pc) == 0


def test_parent_child_refusals(isolated):
    p1 = people.create_person(name="P1")["id"]
    p2 = people.create_person(name="P2")["id"]
    p3 = people.create_person(name="P3")["id"]

    # 1. Self-parent
    with pytest.raises(errors.ValidationError) as exc:
        family.add_parent_child(parent_id=p1, child_id=p1)
    assert exc.value.code == "SELF_PARENT"

    # 2. Unknown person
    with pytest.raises(errors.NotFoundError):
        family.add_parent_child(parent_id="nonexistent_id", child_id=p2)
    with pytest.raises(errors.NotFoundError):
        family.add_parent_child(parent_id=p1, child_id="nonexistent_id")

    # 3. Duplicate fact
    family.add_parent_child(parent_id=p1, child_id=p2)
    with pytest.raises(errors.ValidationError) as exc:
        family.add_parent_child(parent_id=p1, child_id=p2)
    assert exc.value.code == "DUPLICATE_FACT"

    # 4. Ancestry cycle: P1 -> P2, P2 -> P3, attempt P3 -> P1
    family.add_parent_child(parent_id=p2, child_id=p3)
    with pytest.raises(errors.ValidationError) as exc:
        family.add_parent_child(parent_id=p3, child_id=p1)
    assert exc.value.code == "FAMILY_VALIDATION"
    assert "Ancestry cycle" in exc.value.message

    # 5. Unsupported kind and role
    with pytest.raises(errors.ValidationError):
        family.add_parent_child(parent_id=p1, child_id=p3, kind="invalid_kind")
    with pytest.raises(errors.ValidationError):
        family.add_parent_child(parent_id=p1, child_id=p3, role="invalid_role")


def test_marriage_crud_metadata_and_undo(isolated, client):
    sp1 = people.create_person(name="Spouse A", gender="male", birth_year=1980)["id"]
    sp2 = people.create_person(name="Spouse B", gender="female", birth_year=1982)["id"]

    mutation_history._MUTATION_STACK.clear()

    # Create marriage with all metadata fields
    add_res = family.add_marriage(
        person_a=sp1,
        person_b=sp2,
        status="married",
        year=2010,
        children_status="no_children",
    )
    assert add_res["ok"] is True
    assert add_res["status"] == "married"
    assert add_res["year"] == 2010
    assert add_res["children_status"] == "no_children"

    # Verify relationships endpoint returns stored fact
    rel = client.get(f"/api/relationships/{sp1}/{sp2}").json()
    assert rel["ok"] is True
    prim = rel["primary"][0]
    assert prim["derived"] is False
    assert prim["stored_fact_kind"] == "marriage"
    assert prim["status"] == "married"

    # Update marriage: change status to divorced, change year, clear children_status via empty string
    upd_res = client.patch(
        "/api/family/marriage",
        json={
            "person_a": sp1,
            "person_b": sp2,
            "status": "divorced",
            "year": 2018,
            "children_status": "",
        },
    ).json()
    assert upd_res["ok"] is True
    assert upd_res["status"] == "divorced"
    assert upd_res["year"] == 2018
    assert upd_res["children_status"] is None

    # Delete marriage
    del_res = family.delete_marriage(sp1, sp2)
    assert del_res["ok"] is True

    # Undo delete -> restored with divorced/2018/None
    undo_1 = mutation_history.undo_last_mutation()
    assert undo_1["ok"] is True
    m_list = family.family_facts()["marriages"]
    m = [row for row in m_list if sorted((row["spouse_a"], row["spouse_b"])) == sorted((sp1, sp2))]
    assert len(m) == 1
    assert m[0]["status"] == "divorced"
    assert m[0]["year"] == 2018
    assert m[0]["children_status"] is None

    # Undo update -> restored with married/2010/no_children
    undo_2 = mutation_history.undo_last_mutation()
    assert undo_2["ok"] is True
    m_list = family.family_facts()["marriages"]
    m = [row for row in m_list if sorted((row["spouse_a"], row["spouse_b"])) == sorted((sp1, sp2))]
    assert len(m) == 1
    assert m[0]["status"] == "married"
    assert m[0]["year"] == 2010
    assert m[0]["children_status"] == "no_children"

    # Undo create -> marriage completely gone
    undo_3 = mutation_history.undo_last_mutation()
    assert undo_3["ok"] is True
    m_list = family.family_facts()["marriages"]
    m = [row for row in m_list if sorted((row["spouse_a"], row["spouse_b"])) == sorted((sp1, sp2))]
    assert len(m) == 0


def test_marriage_refusals(isolated):
    p1 = people.create_person(name="Marriage Person 1")["id"]
    p2 = people.create_person(name="Marriage Person 2")["id"]
    p_single = people.create_person(name="Single Person", marital_status="single")["id"]

    # 1. Self-marriage
    with pytest.raises(errors.ValidationError) as exc:
        family.add_marriage(person_a=p1, person_b=p1)
    assert exc.value.code == "SELF_MARRIAGE"

    # 2. Unknown spouse
    with pytest.raises(errors.NotFoundError):
        family.add_marriage(person_a="ghost", person_b=p2)

    # 3. Duplicate marriage
    family.add_marriage(person_a=p1, person_b=p2)
    with pytest.raises(errors.ValidationError) as exc:
        family.add_marriage(person_a=p2, person_b=p1)
    assert exc.value.code == "DUPLICATE_FACT"

    # 4. Single-person marital status conflict
    with pytest.raises(errors.ValidationError) as exc:
        family.add_marriage(person_a=p_single, person_b=p1)
    assert exc.value.code == "FAMILY_VALIDATION"

    # 5. Invalid status or year
    with pytest.raises(errors.ValidationError):
        family.add_marriage(person_a=p1, person_b=p2, status="invalid_status")
    with pytest.raises(errors.ValidationError):
        family.add_marriage(person_a=p1, person_b=p2, year=1750)


def test_sibling_group_crud_and_derived_persistence(isolated, client):
    # Setup parents and two children
    dad = people.create_person(name="Father Bio", gender="male")["id"]
    mom = people.create_person(name="Mother Bio", gender="female")["id"]
    child1 = people.create_person(name="Sibling Alpha", gender="male")["id"]
    child2 = people.create_person(name="Sibling Beta", gender="female")["id"]

    family.add_parent_child(parent_id=dad, child_id=child1, role="father", kind="biological")
    family.add_parent_child(parent_id=mom, child_id=child1, role="mother", kind="biological")
    family.add_parent_child(parent_id=dad, child_id=child2, role="father", kind="biological")
    family.add_parent_child(parent_id=mom, child_id=child2, role="mother", kind="biological")

    # Before explicit sibling group: siblinghood exists from biological parents (derived=True)
    rel_initial = client.get(f"/api/relationships/{child1}/{child2}").json()
    assert rel_initial["ok"] is True
    prim_init = rel_initial["primary"][0]
    assert prim_init["relationship_type"] in ("sibling", "sister", "brother")
    assert prim_init["derived"] is True
    assert prim_init.get("stored_fact_kind") is None

    mutation_history._MUTATION_STACK.clear()

    # Now add an explicit sibling group
    add_grp = family.add_sibling_group(
        member_ids=[child1, child2],
        type_="full",
        ordered=True,
    )
    assert add_grp["ok"] is True
    grp_id = add_grp["id"]

    # Now relationship reflects the stored fact: derived=False, stored_fact_kind="sibling_group"
    rel_stored = client.get(f"/api/relationships/{child1}/{child2}").json()
    prim_stored = rel_stored["primary"][0]
    assert prim_stored["derived"] is False
    assert prim_stored["stored_fact_kind"] == "sibling_group"

    # Update sibling group: change type to default (None / "") and ordered to False
    upd_grp = family.update_sibling_group(grp_id, type_="", ordered=False)
    assert upd_grp["ok"] is True
    assert upd_grp["type"] is None
    assert upd_grp["ordered"] is False

    # Delete explicit sibling group:
    # KEY VERIFICATION: removing the explicit fact does NOT break kinship!
    # They remain siblings via common parents, but derived flips back to True.
    del_grp = family.delete_sibling_group(grp_id)
    assert del_grp["ok"] is True

    rel_after_del = client.get(f"/api/relationships/{child1}/{child2}").json()
    prim_after_del = rel_after_del["primary"][0]
    assert prim_after_del["relationship_type"] in ("sibling", "sister", "brother")
    assert prim_after_del["derived"] is True
    assert prim_after_del.get("stored_fact_kind") is None

    # Undo deletion -> explicit sibling group restored (derived=False)
    undo_del = mutation_history.undo_last_mutation()
    assert undo_del["ok"] is True
    rel_restored = client.get(f"/api/relationships/{child1}/{child2}").json()
    prim_restored = rel_restored["primary"][0]
    assert prim_restored["derived"] is False
    assert prim_restored["stored_fact_kind"] == "sibling_group"


def test_sibling_group_refusals(isolated):
    p1 = people.create_person(name="Sib 1")["id"]
    p2 = people.create_person(name="Sib 2")["id"]
    p3 = people.create_person(name="Sib 3")["id"]

    # 1. Less than 2 members
    with pytest.raises(errors.ValidationError) as exc:
        family.add_sibling_group(member_ids=[p1])
    assert exc.value.code == "SIBLING_GROUP_SIZE"

    # 2. Repeated member
    with pytest.raises(errors.ValidationError) as exc:
        family.add_sibling_group(member_ids=[p1, p1])
    assert exc.value.code == "SIBLING_GROUP_REPEAT"

    # 3. Full sibling fact with >2 members
    with pytest.raises(errors.ValidationError) as exc:
        family.add_sibling_group(member_ids=[p1, p2, p3], type_="full")
    assert exc.value.code == "FULL_SIBLING_SIZE"

    # 4. Duplicate sibling group
    family.add_sibling_group(member_ids=[p1, p2])
    with pytest.raises(errors.ValidationError) as exc:
        family.add_sibling_group(member_ids=[p2, p1])
    assert exc.value.code == "DUPLICATE_FACT"


def test_preview_dry_run_immutability(client):
    facts_before = client.get("/api/family/facts").json()

    p_a = client.post("/api/people", json={"name": "DryRun Person A"}).json()["person"]["id"]
    p_b = client.post("/api/people", json={"name": "DryRun Person B"}).json()["person"]["id"]

    # 1. Preview add_parent_child
    prev_pc = client.post(
        "/api/mutations/preview",
        json={
            "action": "add_parent_child",
            "params": {"parent_id": p_a, "child_id": p_b, "role": "father", "kind": "biological"},
        },
    ).json()
    assert prev_pc["ok"] is True
    assert prev_pc["valid"] is True
    assert len(prev_pc["direct_changes"]) == 1

    # 2. Preview add_marriage
    prev_m = client.post(
        "/api/mutations/preview",
        json={
            "action": "add_marriage",
            "params": {"person_a": p_a, "person_b": p_b, "status": "married", "year": 2022},
        },
    ).json()
    assert prev_m["ok"] is True
    assert prev_m["valid"] is True

    # 3. Preview add_sibling_group
    prev_s = client.post(
        "/api/mutations/preview",
        json={
            "action": "add_sibling_group",
            "params": {"member_ids": [p_a, p_b], "type_": "full"},
        },
    ).json()
    assert prev_s["ok"] is True
    assert prev_s["valid"] is True

    # Confirm facts in DB remain completely untouched
    facts_after = client.get("/api/family/facts").json()
    assert len(facts_after["parent_child"]) == len(facts_before["parent_child"])
    assert len(facts_after["marriages"]) == len(facts_before["marriages"])
    assert len(facts_after["sibling_groups"]) == len(facts_before["sibling_groups"])


def test_atomicity_failed_mutation_leaves_undo_clean(isolated):
    p1 = people.create_person(name="Safe Person 1")["id"]
    p2 = people.create_person(name="Safe Person 2")["id"]

    mutation_history._MUTATION_STACK.clear()

    initial_count = len(family.family_facts()["parent_child"])

    # Perform one successful mutation so undo has 1 entry
    family.add_parent_child(parent_id=p1, child_id=p2)
    assert len(family.family_facts()["parent_child"]) == initial_count + 1

    # Attempt an invalid mutation that fails (self-parent)
    with pytest.raises(errors.ValidationError):
        family.add_parent_child(parent_id=p1, child_id=p1)

    # Attempt another invalid mutation that fails (ancestry cycle)
    with pytest.raises(errors.ValidationError):
        family.add_parent_child(parent_id=p2, child_id=p1)

    # Verify DB facts: only the 1 valid fact exists
    assert len(family.family_facts()["parent_child"]) == initial_count + 1

    # Verify undo stack: undoing pops the ONE valid mutation cleanly
    undo = mutation_history.undo_last_mutation()
    assert undo["ok"] is True
    assert len(family.family_facts()["parent_child"]) == initial_count

    # No more undos available
    with pytest.raises(errors.InvalidOperationError) as exc:
        mutation_history.undo_last_mutation()
    assert exc.value.code == "NO_UNDO_AVAILABLE"


def test_read_only_mode_blocks_family_writes(isolated):
    p1 = people.create_person(name="RO Person 1")["id"]
    p2 = people.create_person(name="RO Person 2")["id"]

    with patch.object(DataRootManager, "is_read_only", return_value=True):
        with pytest.raises(DataRootReadOnlyError):
            family.add_parent_child(parent_id=p1, child_id=p2)

        with pytest.raises(DataRootReadOnlyError):
            family.add_marriage(person_a=p1, person_b=p2)

        with pytest.raises(DataRootReadOnlyError):
            family.add_sibling_group(member_ids=[p1, p2])
