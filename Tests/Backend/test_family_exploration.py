"""Phase 3 — Family exploration and diagram backend tests.

Covers all 28 required Family Phase criteria against isolated data roots:
1. Default focus family view succeeds
2. Arbitrary valid focus succeeds
3. Invalid focus rejected cleanly
4. Focus relationship labels are Python-derived
5. Maternal branch metadata correct
6. Paternal branch metadata correct
7. Relationship with both sides preserves both
8. Multiple paths preserved
9. Direct parent relationship
10. Direct child relationship
11. Marriage relationship
12. Sibling relationship
13. Grandparent relationship
14. Uncle/aunt relationship
15. Cousin degree/removal
16. Adopted parent displayed accurately
17. Step parent displayed accurately
18. Foster/guardian kind preserved
19. Marriage status preserved
20. Birth-order metadata preserved
21. Special characters escaped safely
22. Canonical person IDs used for Mermaid node identity
23. Repeated generation deterministic
24. 75–100-person synthetic family generates successfully
25. Family view is read-only against family fact tables
26. No production-path assumptions
27. Missing DataRoot handled correctly
28. Empty/partial family handled cleanly
"""

import copy
import pytest
from app.backend.api.main import api_family_diagram, api_family_view
from app.backend.domain.family import engine as build_family
from app.backend.model import load_model
from app.backend.services import errors, family, people, relationship
from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")
AIKA = generate_canonical_person_id("Aika Calder-Rahim")
ELIAS = generate_canonical_person_id("Elias Calder")
SALMA = generate_canonical_person_id("Salma Rahim")
SAMI = generate_canonical_person_id("Sami Calder")
QADIR = generate_canonical_person_id("Qadir Rahim")
MAHIRA = generate_canonical_person_id("Mahira Rahim")
ADNAN = generate_canonical_person_id("Adnan Calder")
SORAYA = generate_canonical_person_id("Soraya Calder")
LAYLA = generate_canonical_person_id("Layla Rahim")


# 1. default focus family view succeeds
def test_default_focus_family_view_succeeds(client):
    res = client.get("/api/family/view")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["focus"]["id"] == MIRA
    assert data["default_focus_id"] == MIRA
    assert "flowchart TB" in data["diagram"]
    assert len(data["people"]) == 15
    assert len(data["legend"]) >= 5


# 2. arbitrary valid focus succeeds
def test_arbitrary_valid_focus_succeeds(client):
    res = client.get(f"/api/family/view?focus_person_id={AIKA}")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["focus"]["id"] == AIKA
    assert f"class {build_family._person_node_id(AIKA)} focus;" in data["diagram"]


# 3. invalid focus rejected cleanly
def test_invalid_focus_rejected_cleanly(client):
    res = client.get("/api/family/view?focus_person_id=nonexistent_invalid_id")
    assert res.status_code == 404
    data = res.json()
    assert data.get("error", {}).get("code") == "NOT_FOUND"


# 4. focus relationship labels are Python-derived
def test_focus_relationship_labels_are_python_derived(client):
    res = client.get(f"/api/family/view?focus_person_id={AIKA}")
    assert res.status_code == 200
    diagram = res.json()["diagram"]
    assert build_family._person_node_id(MIRA) in diagram
    assert "maternal first cousin" in diagram
    assert "paternal first cousin" in diagram


# 5. maternal branch metadata correct
def test_maternal_branch_metadata_correct(isolated):
    model = load_model()
    grandmother = next(p for p in model["people"] if p["id"] == MAHIRA)
    assert grandmother["branch"] == "maternal"
    diagram = build_family.build_mermaid(model)
    assert build_family._person_node_id(QADIR) in diagram and build_family._person_node_id(MAHIRA) in diagram


# 6. paternal branch metadata correct
def test_paternal_branch_metadata_correct(isolated):
    model = load_model()
    grandmother = next(p for p in model["people"] if p["id"] == SORAYA)
    assert grandmother["branch"] == "paternal"
    diagram = build_family.build_mermaid(model)
    assert build_family._person_node_id(ADNAN) in diagram and build_family._person_node_id(SORAYA) in diagram


# 7. relationship with both sides preserves both
def test_relationship_with_both_sides_preserves_both(isolated):
    rel = relationship.get_relationship(MIRA, AIKA)
    sides = {item.get("side") for item in rel["primary"] + rel["additional"]}
    assert "paternal" in sides
    assert "maternal" in sides


# 8. multiple paths preserved
def test_multiple_paths_preserved(isolated):
    rel = relationship.get_relationship(MIRA, AIKA)
    assert len(rel["primary"]) >= 1
    assert len(rel["additional"]) >= 1
    # Both paths have distinct path_ids
    primary_path = rel["primary"][0]["path_ids"]
    additional_path = rel["additional"][0]["path_ids"]
    assert primary_path != additional_path


# 9. direct parent relationship
def test_direct_parent_relationship(isolated):
    rel = relationship.get_relationship(MIRA, ELIAS)
    entry = rel["primary"][0]
    assert entry["label_en"] == "Father"
    assert entry["derived"] is False
    assert entry["stored_fact_kind"] == "parent_child"


# 10. direct child relationship
def test_direct_child_relationship(isolated):
    rel = relationship.get_relationship(ELIAS, MIRA)
    entry = rel["primary"][0]
    assert entry["label_en"] in ("Daughter", "Child")
    assert entry["derived"] is False
    assert entry["stored_fact_kind"] == "parent_child"


# 11. marriage relationship
def test_marriage_relationship(isolated):
    rel = relationship.get_relationship(ELIAS, SALMA)
    entry = rel["primary"][0]
    assert entry["label_en"] == "Wife"
    assert entry["derived"] is False
    assert entry["stored_fact_kind"] == "marriage"
    assert entry["status"] == "married"


# 12. sibling relationship
def test_sibling_relationship(isolated):
    rel = relationship.get_relationship(MIRA, SAMI)
    entry = rel["primary"][0]
    assert entry["label_en"] == "Full brother"
    assert entry["label_ur"]
    assert entry["derived"] is False
    assert entry["stored_fact_kind"] == "sibling_group"


# 13. grandparent relationship
def test_grandparent_relationship(isolated):
    rel = relationship.get_relationship(MIRA, QADIR)
    entry = rel["primary"][0]
    assert entry["label_en"] == "Maternal Grandfather"
    assert entry["label_ur"] == "نانا"
    assert entry["derived"] is True
    assert entry["side"] == "maternal"


# 14. uncle/aunt relationship
def test_uncle_aunt_relationship(isolated):
    rel = relationship.get_relationship(MIRA, LAYLA)
    entry = rel["primary"][0]
    assert entry["label_en"].lower() == "maternal aunt"
    assert entry["label_ur"]
    assert entry["derived"] is True
    assert entry["side"] == "maternal"


# 15. cousin degree/removal
def test_cousin_degree_and_removal(isolated):
    rel = relationship.get_relationship(MIRA, AIKA)
    primary = rel["primary"][0]
    assert primary["degree"] == 1
    assert primary["removal"] == 0
    additional = rel["additional"][0]
    assert additional["degree"] == 1
    assert additional["removal"] == 0


# 16. adopted parent displayed accurately
def test_adopted_parent_displayed_accurately(isolated):
    child = people.create_person(name="Adopted Child")
    parent = people.create_person(name="Adoptive Parent")
    family.add_parent_child(
        parent_id=parent["id"], child_id=child["id"], role="mother", kind="adopted"
    )
    rel = relationship.get_relationship(child["id"], parent["id"])
    entry = rel["primary"][0]
    assert entry["derived"] is False
    assert entry["stored_fact_kind"] == "parent_child"
    assert entry["kind"] == "adopted"


# 17. step parent displayed accurately
def test_step_parent_displayed_accurately(isolated):
    child = people.create_person(name="Step Child")
    parent = people.create_person(name="Step Parent")
    family.add_parent_child(
        parent_id=parent["id"], child_id=child["id"], role="father", kind="step"
    )
    rel = relationship.get_relationship(child["id"], parent["id"])
    entry = rel["primary"][0]
    assert entry["derived"] is False
    assert entry["stored_fact_kind"] == "parent_child"
    assert entry["kind"] == "step"


# 18. foster/guardian kind preserved
def test_foster_guardian_kind_preserved(isolated):
    foster_child = people.create_person(name="Foster Child")
    foster_parent = people.create_person(name="Foster Parent")
    family.add_parent_child(
        parent_id=foster_parent["id"], child_id=foster_child["id"], role="parent", kind="foster"
    )
    rel = relationship.get_relationship(foster_child["id"], foster_parent["id"])
    assert rel["primary"][0]["kind"] == "foster"

    guardian_child = people.create_person(name="Guardian Child")
    guardian_parent = people.create_person(name="Guardian Parent")
    family.add_parent_child(
        parent_id=guardian_parent["id"], child_id=guardian_child["id"], role="parent", kind="guardian"
    )
    rel2 = relationship.get_relationship(guardian_child["id"], guardian_parent["id"])
    assert rel2["primary"][0]["kind"] == "guardian"


# 19. marriage status preserved
def test_marriage_status_preserved(isolated):
    p1 = people.create_person(name="Divorced Spouse A")
    p2 = people.create_person(name="Divorced Spouse B")
    res = family.add_marriage(person_a=p1["id"], person_b=p2["id"], status="divorced", year=2015)
    assert res["status"] == "divorced"

    model = load_model()
    mermaid_text = build_family.build_mermaid(model)
    assert "divorced 2015 / طلاق شدہ 2015" in mermaid_text


# 20. birth-order metadata preserved
def test_birth_order_metadata_preserved(isolated):
    model = load_model()
    markers = build_family._order_markers(model)
    assert markers.get(MIRA) == 1
    diagram = build_family.build_mermaid(model)
    assert f'{build_family._person_node_id(MIRA)}["[1] Mira Rahim' in diagram


# 21. special characters escaped safely
def test_special_characters_escaped_safely(isolated):
    special_names = [
        "A [Test]",
        '"B"',
        "Person (III)",
        "Ali & Sara",
        "Name <script>alert(1)</script>",
    ]
    model = load_model()
    created = []
    for index, name in enumerate(special_names):
        person = copy.deepcopy(model["people"][0])
        person.update(id=f"synthetic_hostile_{index}", name=name)
        model["people"].append(person)
        created.append(person)
    mermaid_text = build_family.build_mermaid(model)

    # Verify no raw script tags are output
    assert "<script>" not in mermaid_text
    assert "&lt;script&gt;" in mermaid_text or "Name alert" in mermaid_text

    # Verify quotes escaped
    assert "&quot;B&quot;" in mermaid_text

    # Verify ampersands escaped
    assert "Ali &amp; Sara" in mermaid_text

    # Verify node identity uses slugs, not display names
    for p in created:
        assert build_family._person_node_id(p["id"]) in mermaid_text


# 22. canonical person IDs used for Mermaid node identity
def test_canonical_person_ids_used_for_node_identity(isolated):
    model = load_model()
    for person in model["people"]:
        node_id = build_family._person_node_id(person["id"])
        assert node_id == f"p_{person['id'].replace('-', '_')}"
        assert " " not in node_id


# 23. repeated generation deterministic
def test_repeated_generation_deterministic(isolated):
    model = load_model()
    runs = [build_family.build_mermaid(model) for _ in range(5)]
    assert all(r == runs[0] for r in runs)


# 24. 75–100-person synthetic family generates successfully
def test_large_synthetic_family_generates_successfully(isolated):
    """Constructs a deterministic ~80 person synthetic family hierarchy and verifies diagram build."""
    data = {
        "metadata": {
            "title": "Large Synthetic Family",
            "focus_person": "gen1_male_0",
            "revision": 1,
        },
        "people": [],
        "parent_child": [],
        "marriages": [],
        "sibling_groups": [],
    }

    # Generate 4 generations:
    # Gen 1: 4 couples = 8 people
    # Gen 2: each couple has 3 children = 12 people (6 marry = 6 outside spouses) = 18 people
    # Gen 3: 6 couples have 4 children each = 24 people (8 marry = 8 spouses) = 32 people
    # Gen 4: 8 couples have 3 children each = 24 people
    # Total = 8 + 18 + 32 + 24 = 82 people!

    person_counter = 0

    def add_p(name, gender, branch=None):
        nonlocal person_counter
        p_id = f"p_{person_counter}_{name.lower().replace(' ', '_')}"
        person_counter += 1
        data["people"].append({
            "id": p_id,
            "name": name,
            "gender": gender,
            "branch": branch,
            "birth_year": 1920 + (person_counter // 2),
        })
        return p_id

    # Gen 1
    g1_couples = []
    for i in range(4):
        branch = "maternal" if i < 2 else "paternal"
        h = add_p(f"G1 Father {i}", "male", branch)
        w = add_p(f"G1 Mother {i}", "female", branch)
        data["marriages"].append({"person1": h, "person2": w, "status": "married"})
        g1_couples.append((h, w, branch))

    # Gen 2
    g2_couples = []
    for idx, (h, w, branch) in enumerate(g1_couples):
        children = []
        for c in range(3):
            child_gender = "male" if c % 2 == 0 else "female"
            child = add_p(f"G2 Child {idx}_{c}", child_gender, branch)
            children.append(child)
            data["parent_child"].append({"parent": h, "child": child, "role": "father", "kind": "biological"})
            data["parent_child"].append({"parent": w, "child": child, "role": "mother", "kind": "biological"})
            if c < 2:  # marry 2 children
                spouse = add_p(f"G2 Spouse {idx}_{c}", "female" if child_gender == "male" else "male", branch)
                data["marriages"].append({"person1": child, "person2": spouse, "status": "married"})
                g2_couples.append((child, spouse, branch))
        data["sibling_groups"].append({"id": f"g2_sib_{idx}", "members": children, "ordered": True})

    # Gen 3
    g3_couples = []
    for idx, (h, w, branch) in enumerate(g2_couples):
        children = []
        for c in range(4):
            child_gender = "male" if c % 2 == 0 else "female"
            child = add_p(f"G3 Child {idx}_{c}", child_gender, branch)
            children.append(child)
            data["parent_child"].append({"parent": h, "child": child, "role": "father", "kind": "biological"})
            data["parent_child"].append({"parent": w, "child": child, "role": "mother", "kind": "biological"})
            if idx < 4 and c < 2:
                spouse = add_p(f"G3 Spouse {idx}_{c}", "female" if child_gender == "male" else "male", branch)
                data["marriages"].append({"person1": child, "person2": spouse, "status": "married"})
                g3_couples.append((child, spouse, branch))
        data["sibling_groups"].append({"id": f"g3_sib_{idx}", "members": children, "ordered": True})

    # Gen 4
    for idx, (h, w, branch) in enumerate(g3_couples):
        children = []
        for c in range(3):
            child = add_p(f"G4 Child {idx}_{c}", "male" if c % 2 == 0 else "female", branch)
            children.append(child)
            data["parent_child"].append({"parent": h, "child": child, "role": "father", "kind": "biological"})
            data["parent_child"].append({"parent": w, "child": child, "role": "mother", "kind": "biological"})
        data["sibling_groups"].append({"id": f"g4_sib_{idx}", "members": children, "ordered": True})

    assert len(data["people"]) >= 75
    data["metadata"]["focus_person"] = data["people"][0]["id"]

    # Build Mermaid diagram for the synthetic 75-100 person family
    mermaid_text = build_family.build_mermaid(data)
    assert "flowchart TB" in mermaid_text
    assert f"p_{data['people'][0]['id']}" in mermaid_text
    assert f"class p_{data['people'][0]['id']} focus;" in mermaid_text
    # Verify deterministic output
    mermaid_repeat = build_family.build_mermaid(data)
    assert mermaid_text == mermaid_repeat


# 25. Family view is read-only against family fact tables
def test_family_view_is_read_only(isolated, client):
    from app.backend import db
    conn = db.get_connection()
    try:
        pc_before = conn.execute("SELECT COUNT(*) FROM parent_child").fetchone()[0]
        m_before = conn.execute("SELECT COUNT(*) FROM marriages").fetchone()[0]
        sg_before = conn.execute("SELECT COUNT(*) FROM sibling_groups").fetchone()[0]
        p_before = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    finally:
        conn.close()

    # Call view multiple times with arbitrary focus
    client.get(f"/api/family/view?focus_person_id={MIRA}")
    client.get(f"/api/family/view?focus_person_id={AIKA}")
    client.get(f"/api/family/view?focus_person_id={QADIR}")

    conn2 = db.get_connection()
    try:
        pc_after = conn2.execute("SELECT COUNT(*) FROM parent_child").fetchone()[0]
        m_after = conn2.execute("SELECT COUNT(*) FROM marriages").fetchone()[0]
        sg_after = conn2.execute("SELECT COUNT(*) FROM sibling_groups").fetchone()[0]
        p_after = conn2.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    finally:
        conn2.close()

    assert pc_before == pc_after
    assert m_before == m_after
    assert sg_before == sg_after
    assert p_before == p_after


# 26. no production-path assumptions
def test_no_production_path_assumptions(isolated):
    from app.backend.data_root import DataRootManager
    current_root = DataRootManager.get_bootstrap_root()
    assert current_root == isolated.resolve()


# 27. missing DataRoot handled correctly
def test_missing_data_root_handled_correctly(tmp_path, monkeypatch):
    from app.backend.data_root import DataRootManager
    nonexistent = tmp_path / "nonexistent_root_path"
    DataRootManager.set_override_root(nonexistent)
    try:
        with pytest.raises(Exception):
            load_model()
    finally:
        DataRootManager.set_override_root(None)


# 28. empty/partial family handled cleanly
def test_empty_partial_family_handled_cleanly(isolated):
    p = people.create_person(name="Solo Person")
    data = {
        "metadata": {
            "title": "Solo Family",
            "focus_person": p["id"],
            "revision": 1,
        },
        "people": [p],
        "parent_child": [],
        "marriages": [],
        "sibling_groups": [],
    }
    mermaid_text = build_family.build_mermaid(data)
    assert "flowchart TB" in mermaid_text
    assert build_family._person_node_id(p["id"]) in mermaid_text


# 29. alias-aware people search used by Family resolves alias to canonical person ID
def test_alias_aware_people_search_for_family_focus(client, isolated):
    p = people.create_person(
        name="Alexandra Example",
        aliases=["Alex", "Lexi"],
    )
    canon_id = p["id"]

    # Search by canonical name
    res_name = client.get("/api/people?query=Alexandra")
    assert res_name.status_code == 200
    people_name = res_name.json()["people"]
    assert any(x["id"] == canon_id and x["name"] == "Alexandra Example" for x in people_name)

    # Search by alias "Alex"
    res_alias1 = client.get("/api/people?query=Alex")
    assert res_alias1.status_code == 200
    people_alias1 = res_alias1.json()["people"]
    assert any(x["id"] == canon_id for x in people_alias1)

    # Search by alias "Lexi"
    res_alias2 = client.get("/api/people?query=Lexi")
    assert res_alias2.status_code == 200
    people_alias2 = res_alias2.json()["people"]
    assert any(x["id"] == canon_id for x in people_alias2)

    # In-memory search helper check
    direct_alex = people.list_people(query="Alex")
    assert any(x["id"] == canon_id for x in direct_alex)
    direct_lexi = people.list_people(query="Lexi")
    assert any(x["id"] == canon_id for x in direct_lexi)


# 30. hostile Mermaid label text is escaped safely in rendered diagram source
def test_hostile_mermaid_labels_escaped(isolated):
    hostile_payloads = [
        "Name <script>alert(1)</script>",
        '<img src=x onerror="window.__familyPwned=1">',
        '<svg onload="window.__familyPwned=1">',
        '"><iframe srcdoc="<script>window.parent.__familyPwned=1</script>">',
        "A [Test]",
        '"B"',
        "Ali & Sara",
    ]
    created = [
        {"id": f"synthetic_hostile_{idx}", "name": name, "gender": "unknown", "birth_year": None, "branch": None}
        for idx, name in enumerate(hostile_payloads)
    ]

    data = {
        "metadata": {
            "title": "Security Family",
            "focus_person": created[0]["id"],
            "revision": 1,
        },
        "people": created,
        "parent_child": [],
        "marriages": [],
        "sibling_groups": [],
    }
    diagram = build_family.build_mermaid(data)

    # Unescaped executable script tags must NOT appear
    assert "<script>" not in diagram
    assert "</script>" not in diagram
    assert 'onerror="window.__familyPwned=1"' not in diagram
    assert 'onload="window.__familyPwned=1"' not in diagram
    assert "<iframe" not in diagram

    # Escaped safe entities must be present
    assert "&lt;script&gt;" in diagram
    assert "&lt;img" in diagram
    assert "&lt;svg" in diagram
    assert "&lt;iframe" in diagram
    assert "&amp;" in diagram
    assert "&quot;" in diagram


# 31. canonical node ID independent of display name
def test_canonical_node_id_independent_of_display_name(isolated):
    p = people.create_person(name="Original Name")
    canon_id = p["id"]

    data1 = {
        "metadata": {"title": "Fam", "focus_person": canon_id, "revision": 1},
        "people": [p],
        "parent_child": [],
        "marriages": [],
        "sibling_groups": [],
    }
    d1 = build_family.build_mermaid(data1)
    assert build_family._person_node_id(canon_id) in d1

    # Update person's display name to something completely different
    people.update_person(canon_id, name="Completely Altered Name <script>")
    p_updated = people.get_person(canon_id)

    data2 = {
        "metadata": {"title": "Fam", "focus_person": canon_id, "revision": 1},
        "people": [p_updated],
        "parent_child": [],
        "marriages": [],
        "sibling_groups": [],
    }
    d2 = build_family.build_mermaid(data2)
    # The canonical ID still determines the node identity after a display-name edit.
    assert build_family._person_node_id(canon_id) in d2
    assert "p_Original" not in d2
    assert "p_Completely" not in d2
