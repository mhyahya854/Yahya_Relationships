"""API-level tests for paths and graph-neighbour endpoints."""


def test_paths_endpoint(client):
    response = client.get(
        "/api/relationships/mohammad_yahya_hussain/aresha_zubair/paths"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["paths"]) == 2
    labels = {path["label_en"] for path in payload["paths"]}
    assert labels == {"paternal first cousin", "maternal second cousin"}


def test_paths_endpoint_validation(client):
    response = client.get(
        "/api/relationships/mohammad_yahya_hussain/aresha_zubair/paths",
        params={"max_depth": 99},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MAX_DEPTH"

    shallow = client.get(
        "/api/relationships/mohammad_yahya_hussain/aresha_zubair/paths",
        params={"max_depth": 3},
    )
    assert shallow.json()["error"]["code"] == "NO_RELATIONSHIP_PATH"


def test_graph_neighbors_endpoint(client):
    response = client.get(
        "/api/relationships/graph/neighbors/mohammad_yahya_hussain",
        params={
            "perspective_id": "mohammad_yahya_hussain",
            "filters": "parents,siblings",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    ids = {node["id"] for node in payload["nodes"]}
    assert {"irsa_naz", "mansoor_hussain", "maham_mansoor"} <= ids
    assert all(node["is_perspective"] for node in payload["nodes"] if node["id"] == "mohammad_yahya_hussain")


def test_relationships_from_route_not_shadowed(client):
    response = client.get("/api/relationships/from/mohammad_yahya_hussain")
    assert response.status_code == 200
    payload = response.json()
    assert payload["perspective"]["id"] == "mohammad_yahya_hussain"
    assert isinstance(payload["relationships"], list)
