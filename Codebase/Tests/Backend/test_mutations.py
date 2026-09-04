"""Backend test suite for human-editing mutation features, consequence preview engine, and undo system."""

import pytest


def test_duplicate_person_check(client):
    response = client.post(
        "/api/people/check-duplicate",
        json={"name": "Yahya", "aliases": ["Yahya Bhai"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["candidates"]) > 0
    candidate_names = [c["name"] for c in data["candidates"]]
    assert any("Yahya" in name for name in candidate_names)


def test_preview_mutation_add_parent_child_and_non_mutation(client):
    # Record baseline state
    facts_before = client.get("/api/family/facts").json()

    # Preview adding a parent-child fact (e.g. mansoor_hussain -> temporary child)
    # First create temporary test person
    created_res = client.post(
        "/api/people",
        json={"name": "Temp Test Child", "gender": "male", "birth_year": 2020},
    ).json()
    child_id = created_res["person"]["id"]

    preview_res = client.post(
        "/api/mutations/preview",
        json={
            "action": "add_parent_child",
            "params": {
                "parent_id": "mansoor_hussain",
                "child_id": child_id,
                "role": "father",
                "kind": "biological",
            },
        },
    ).json()

    assert preview_res["ok"] is True
    assert preview_res["valid"] is True
    assert len(preview_res["direct_changes"]) > 0
    assert any("Temp Test Child" in change for change in preview_res["direct_changes"])
    assert len(preview_res["derived_added"]) > 0

    # Ensure facts in database did NOT change from preview
    facts_after = client.get("/api/family/facts").json()
    # Excluding the created test person from people count check, parent_child count must be equal
    assert len(facts_after["parent_child"]) == len(facts_before["parent_child"])


def test_preview_invalid_self_parent(client):
    preview_res = client.post(
        "/api/mutations/preview",
        json={
            "action": "add_parent_child",
            "params": {"parent_id": "mansoor_hussain", "child_id": "mansoor_hussain"},
        },
    ).json()
    assert preview_res["ok"] is True
    assert preview_res["valid"] is False
    assert preview_res["code"] == "SELF_PARENT"


def test_preview_invalid_self_marriage(client):
    preview_res = client.post(
        "/api/mutations/preview",
        json={
            "action": "add_marriage",
            "params": {"person_a": "mansoor_hussain", "person_b": "mansoor_hussain"},
        },
    ).json()
    assert preview_res["ok"] is True
    assert preview_res["valid"] is False
    assert preview_res["code"] == "SELF_MARRIAGE"


def test_family_and_general_mutations_with_undo(client):
    # 1. Add temporary person A and person B
    p_a = client.post("/api/people", json={"name": "Mutation Person A"}).json()["person"]["id"]
    p_b = client.post("/api/people", json={"name": "Mutation Person B"}).json()["person"]["id"]

    # 2. Add general relationship
    gen_res = client.post(
        "/api/relationships/general",
        json={
            "person_a": p_a,
            "person_b": p_b,
            "type": "colleague",
            "directionality": "symmetric",
        },
    ).json()
    assert gen_res["ok"] is True
    rel_id = gen_res["relationship"]["id"]

    # Verify relationship exists
    gen_list = client.get(f"/api/relationships/general?person_id={p_a}").json()["relationships"]
    assert len(gen_list) == 1

    # 3. Update general relationship
    patch_res = client.patch(
        f"/api/relationships/general/{rel_id}",
        json={"notes": "Worked together on project"},
    ).json()
    assert patch_res["ok"] is True
    assert patch_res["relationship"]["notes"] == "Worked together on project"

    # 4. Undo last mutation (should revert the patch notes update)
    undo_res = client.post("/api/mutations/undo").json()
    assert undo_res["ok"] is True
    gen_restored = client.get(f"/api/relationships/general?person_id={p_a}").json()["relationships"]
    assert gen_restored[0]["notes"] is None or gen_restored[0]["notes"] == ""


def test_sibling_group_crud(client):
    # Create 2 temp people
    s1 = client.post("/api/people", json={"name": "Sibling One"}).json()["person"]["id"]
    s2 = client.post("/api/people", json={"name": "Sibling Two"}).json()["person"]["id"]

    # Add sibling group
    sg_res = client.post(
        "/api/family/sibling-group",
        json={"member_ids": [s1, s2], "type_": "full", "ordered": True},
    ).json()
    assert sg_res["ok"] is True
    group_id = sg_res["id"]

    # Verify in family facts
    facts = client.get("/api/family/facts").json()
    sg_ids = [sg["id"] for sg in facts["sibling_groups"]]
    assert group_id in sg_ids

    # Delete sibling group
    del_res = client.delete(f"/api/family/sibling-group/{group_id}").json()
    assert del_res["ok"] is True
