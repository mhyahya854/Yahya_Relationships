"""End-to-end API tests against FastAPI's TestClient."""

from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")
SAMI = generate_canonical_person_id("Sami Calder")
RAFI = generate_canonical_person_id("Rafi Calder")
KAMAL = generate_canonical_person_id("Kamal Calder")
DARYA = generate_canonical_person_id("Darya Sol")
SALMA = generate_canonical_person_id("Salma Rahim")
AIKA = generate_canonical_person_id("Aika Calder-Rahim")


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["people"] == 15


def test_people_endpoints(client):
    response = client.get("/api/people")
    assert response.status_code == 200
    assert len(response.json()["people"]) == 15
    detail = client.get(f"/api/people/{MIRA}")
    assert detail.status_code == 200
    assert detail.json()["person"]["name"] == "Mira Rahim"


def test_relationship_endpoint_and_perspective(client):
    response = client.get(f"/api/relationships/{MIRA}/{SAMI}")
    assert response.status_code == 200
    labels = {
        item["label_en"]
        for item in response.json()["primary"]
    }
    assert "Full brother" in labels


def test_compare_endpoint(client):
    response = client.get(f"/api/compare/{KAMAL}/{RAFI}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["a_to_b"]["primary"][0]["label_en"] == "Son"
    assert payload["b_to_a"]["primary"][0]["label_en"] == "Father"


def test_fictional_maternal_and_paternal_cousin_paths(client):
    response = client.get(f"/api/relationships/{MIRA}/{AIKA}")
    assert response.status_code == 200
    labels = {item["label_en"] for item in response.json()["primary"] + response.json()["additional"]}
    assert {"maternal first cousin", "paternal first cousin"} <= labels


def test_state_perspective(client):
    state = client.get("/api/state").json()
    assert state["perspective_person_id"] == MIRA
    updated = client.put(
        "/api/state", json={"perspective_person_id": KAMAL}
    )
    assert updated.status_code == 200
    assert updated.json()["perspective_person_id"] == KAMAL
    reset = client.post("/api/state/reset")
    assert reset.json()["perspective_person_id"] == MIRA


def test_general_relationship_lifecycle(client):
    created = client.post(
        "/api/people",
        json={"name": "API Friend", "group_id": "friends"},
    ).json()["person"]
    added = client.post(
        "/api/relationships/general",
        json={
            "person_a": created["id"],
            "person_b": MIRA,
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
    journal = client.get(f"/api/people/{MIRA}/journal")
    assert journal.status_code == 200
    path = journal.json()["path"]
    from pathlib import Path

    Path(path).write_text(
        "# Mira Rahim\n\n## Test\n\n- Edited externally.\n",
        encoding="utf-8",
    )
    again = client.get(f"/api/people/{MIRA}/journal")
    assert "Edited externally." in again.json()["content"]


def test_search_api(client):
    response = client.get("/api/search", params={"q": "mira"})
    assert response.status_code == 200
    people_hits = [
        result
        for result in response.json()["results"]
        if result["category"] == "PERSON"
    ]
    assert people_hits

    family = client.get(
        "/api/search", params={"q": "father"}
    ).json()["results"]
    titles = {result["title"] for result in family}
    assert "Elias Calder" in titles


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
                "perspective": KAMAL,
                "target": RAFI,
            },
        },
    )
    assert run.status_code == 200
    assert run.json()["ok"] is True
    assert run.json()["primary"][0]["label_en"] == "Son"


def test_family_diagram_endpoint(client):
    response = client.get(
        "/api/family/diagram",
        params={"perspective_id": SALMA},
    )
    assert response.status_code == 200
    mermaid_text = response.json()["mermaid"]
    assert mermaid_text.startswith("flowchart TB")
    assert f"p_{SALMA.replace('--', '__')}" in mermaid_text
