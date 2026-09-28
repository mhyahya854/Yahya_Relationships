"""API-level graph paths against the fictional synthetic Data Root."""

from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")
AIKA = generate_canonical_person_id("Aika Calder-Rahim")
ELIAS = generate_canonical_person_id("Elias Calder")
SALMA = generate_canonical_person_id("Salma Rahim")
SAMI = generate_canonical_person_id("Sami Calder")


def test_paths_endpoint(client):
    response = client.get(
        f"/api/relationships/{MIRA}/{AIKA}/paths"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    labels = {path["label_en"] for path in payload["paths"]}
    assert {"paternal first cousin", "maternal first cousin"} <= labels


def test_paths_endpoint_validation(client):
    response = client.get(
        f"/api/relationships/{MIRA}/{AIKA}/paths",
        params={"max_depth": 99},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MAX_DEPTH"

    shallow = client.get(
        f"/api/relationships/{MIRA}/{AIKA}/paths",
        params={"max_depth": 3},
    )
    assert shallow.json()["error"]["code"] == "NO_RELATIONSHIP_PATH"


def test_graph_neighbors_endpoint(client):
    response = client.get(
        f"/api/relationships/graph/neighbors/{MIRA}",
        params={
            "perspective_id": MIRA,
            "filters": "parents,siblings",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    ids = {node["id"] for node in payload["nodes"]}
    assert {ELIAS, SALMA, SAMI} <= ids
    assert all(node["is_perspective"] for node in payload["nodes"] if node["id"] == MIRA)


def test_relationships_from_route_not_shadowed(client):
    response = client.get(f"/api/relationships/from/{MIRA}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["perspective"]["id"] == MIRA
    assert isinstance(payload["relationships"], list)
