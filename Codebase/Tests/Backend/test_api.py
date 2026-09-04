"""End-to-end API tests against FastAPI's TestClient."""


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["people"] == 35


def test_people_endpoints(client):
    response = client.get("/api/people")
    assert response.status_code == 200
    assert len(response.json()["people"]) == 35
    detail = client.get("/api/people/mohammad_yahya_hussain")
    assert detail.status_code == 200
    assert detail.json()["person"]["name"] == "Mohammad Yahya Hussain"


def test_relationship_endpoint_and_perspective(client):
    response = client.get(
        "/api/relationships/mohammad_yahya_hussain/ezan_asif"
    )
    assert response.status_code == 200
    labels = {
        item["label_en"]
        for item in response.json()["primary"]
    }
    assert "maternal first cousin" in labels
    additional = {
        item["label_en"]
        for item in response.json()["additional"]
    }
    assert "paternal second cousin" in additional


def test_compare_endpoint(client):
    response = client.get("/api/compare/mansoor_hussain/aresha_zubair")
    assert response.status_code == 200
    payload = response.json()
    assert payload["a_to_b"]["primary"][0]["label_en"] == "Niece"
    assert payload["b_to_a"]["primary"][0]["label_en"] == "Maternal uncle"


def test_state_perspective(client):
    state = client.get("/api/state").json()
    assert state["perspective_person_id"] == "mohammad_yahya_hussain"
    updated = client.put(
        "/api/state", json={"perspective_person_id": "mansoor_hussain"}
    )
    assert updated.status_code == 200
    assert updated.json()["perspective_person_id"] == "mansoor_hussain"
    reset = client.post("/api/state/reset")
    assert reset.json()["perspective_person_id"] == "mohammad_yahya_hussain"


def test_general_relationship_lifecycle(client):
    created = client.post(
        "/api/people",
        json={"name": "API Friend", "group_id": "friends"},
    ).json()["person"]
    added = client.post(
        "/api/relationships/general",
        json={
            "person_a": created["id"],
            "person_b": "mohammad_yahya_hussain",
            "type": "close_friend",
        },
    )
    assert added.status_code == 200
    relationship_id = added.json()["relationship"]["id"]
    listed = client.get(f"/api/relationships/general?person_id={created['id']}")
    assert len(listed.json()["relationships"]) == 1
    deleted = client.delete(f"/api/relationships/general/{relationship_id}")
    assert deleted.status_code == 200


def test_journal_api_and_external_edit(client, isolated):
    journal = client.get("/api/people/maham_mansoor/journal")
    assert journal.status_code == 200
    path = journal.json()["path"]
    from pathlib import Path

    Path(path).write_text(
        "# Maham Mansoor\n\n## Test\n\n- Edited externally.\n",
        encoding="utf-8",
    )
    again = client.get("/api/people/maham_mansoor/journal")
    assert "Edited externally." in again.json()["content"]


def test_search_api(client):
    response = client.get("/api/search", params={"q": "yahya"})
    assert response.status_code == 200
    people_hits = [
        result
        for result in response.json()["results"]
        if result["category"] == "PERSON"
    ]
    assert people_hits

    family = client.get(
        "/api/search", params={"q": "maternal uncle"}
    ).json()["results"]
    titles = {result["title"] for result in family}
    assert "Sohaib Hussain" in titles
    assert "Arsalan Israr" in titles


def test_backup_api(client):
    created = client.post("/api/backups", json={"label": "api-backup"})
    assert created.status_code == 200
    name = created.json()["backup"]["name"]
    verified = client.get(f"/api/backups/{name}/verify")
    assert verified.json()["ok"] is True


def test_hermes_endpoints(client):
    catalog = client.get("/api/hermes/tools")
    assert catalog.status_code == 200
    assert len(catalog.json()["tools"]) >= 15
    run = client.post(
        "/api/hermes/run",
        json={
            "tool": "get_relationship",
            "arguments": {
                "perspective": "mansoor_hussain",
                "target": "aresha_zubair",
            },
        },
    )
    assert run.status_code == 200
    assert run.json()["ok"] is True
    assert run.json()["primary"][0]["label_en"] == "Niece"


def test_family_diagram_endpoint(client):
    response = client.get(
        "/api/family/diagram",
        params={"perspective_id": "irsa_naz"},
    )
    assert response.status_code == 200
    mermaid_text = response.json()["mermaid"]
    assert mermaid_text.startswith("flowchart TB")
    assert "p_irsa_naz" in mermaid_text
