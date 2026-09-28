"""Relationship paths and graph behavior against the fictional Mosaic family."""

import pytest

from app.backend.domain.canonical.ids import generate_canonical_person_id as person_id
from app.backend.domain.relationships import graph as graph_service
from app.backend.domain.relationships import path_service
from app.backend.hermes import tools as hermes
from app.backend.services import errors, general, people, relationship


pytestmark = pytest.mark.usefixtures("isolated")
MIRA = person_id("Mira Rahim")
AIKA = person_id("Aika Calder-Rahim")
ELIAS = person_id("Elias Calder")
SALMA = person_id("Salma Rahim")
SAMI = person_id("Sami Calder")
DARYA = person_id("Darya Sol")
LAYLA = person_id("Layla Rahim")


def _labels(payload):
    return {(path["label_en"] or "").casefold() for path in payload["paths"]}


def test_double_cousin_paths_are_distinct():
    payload = path_service.get_relationship_paths(MIRA, AIKA)
    assert _labels(payload) == {"maternal first cousin", "paternal first cousin"}
    paths = payload["paths"]
    assert [p["side"] for p in paths] == ["maternal", "paternal"]
    assert len({p["id"] for p in paths}) == 2
    assert len({tuple(n["id"] for n in p["nodes"]) for p in paths}) == 2
    for path in paths:
        assert path["degree"] == 1
        assert path["removal"] == 0
        assert path["distance"] == 4


def test_maternal_and_paternal_routes_use_fictional_ancestors():
    paths = path_service.get_relationship_paths(MIRA, AIKA)["paths"]
    by_side = {path["side"]: [n["name"] for n in path["nodes"]] for path in paths}
    assert by_side["maternal"] == [
        "Mira Rahim", "Salma Rahim", "Qadir Rahim", "Layla Rahim", "Aika Calder-Rahim"
    ]
    assert by_side["paternal"] == [
        "Mira Rahim", "Elias Calder", "Adnan Calder", "Kamal Calder", "Aika Calder-Rahim"
    ]


def test_parent_child_spouse_and_sibling_paths():
    father = path_service.get_relationship_paths(MIRA, ELIAS)["paths"][0]
    assert father["label_en"].casefold() == "father"
    assert father["distance"] == 1
    assert father["edges"][0]["type"] == "parent_child"
    assert father["derived"] is False

    daughter = path_service.get_relationship_paths(ELIAS, MIRA)["paths"][0]
    assert daughter["label_en"].casefold() == "daughter"
    assert daughter["edges"][0]["role"] == "is parent of"

    spouse = path_service.get_relationship_paths(SALMA, ELIAS)["paths"][0]
    assert spouse["label_en"].casefold() == "husband"
    assert spouse["edges"][0]["type"] == "marriage"

    sibling = path_service.get_relationship_paths(MIRA, SAMI)["paths"][0]
    assert sibling["label_en"].casefold() == "full brother"
    assert sibling["distance"] == 2
    assert {a["id"] for a in sibling["common_ancestors"]} == {ELIAS, SALMA}


def test_reverse_perspective_changes_direction():
    toward_aunt = path_service.get_relationship_paths(MIRA, LAYLA)
    toward_niece = path_service.get_relationship_paths(LAYLA, MIRA)
    assert any("aunt" in label for label in _labels(toward_aunt))
    assert any("niece" in label for label in _labels(toward_niece))


def test_no_loops_and_stable_unique_path_ids():
    for first, second in ((MIRA, AIKA), (MIRA, SAMI), (SALMA, AIKA)):
        payload = path_service.get_relationship_paths(first, second, max_depth=20, max_paths=30)
        ids = [path["id"] for path in payload["paths"]]
        assert len(ids) == len(set(ids))
        for path in payload["paths"]:
            node_ids = [node["id"] for node in path["nodes"]]
            assert len(node_ids) == len(set(node_ids))
        assert ids == [path["id"] for path in path_service.get_relationship_paths(
            first, second, max_depth=20, max_paths=30
        )["paths"]]


def test_limits_and_missing_people():
    for kwargs, code in (({"max_depth": 0}, "INVALID_MAX_DEPTH"),
                         ({"max_paths": 51}, "INVALID_MAX_PATHS")):
        with pytest.raises(errors.AppError) as exc:
            path_service.get_relationship_paths(MIRA, AIKA, **kwargs)
        assert exc.value.code == code
    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths(MIRA, AIKA, max_depth=3)
    assert exc.value.code == "NO_RELATIONSHIP_PATH"
    one = path_service.get_relationship_paths(MIRA, AIKA, max_paths=1)
    assert len(one["paths"]) == 1 and one["truncated"] is True
    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths("missing_person", MIRA)
    assert exc.value.code == "NOT_FOUND"


def test_path_labels_match_relationship_service():
    sample = [MIRA, AIKA, ELIAS, SALMA, SAMI, LAYLA]
    for first in sample:
        for second in sample:
            if first == second:
                continue
            result = relationship.get_relationship(first, second)
            expected = {
                (item["label_en"] or "").casefold()
                for item in result["primary"] + result["additional"]
            }
            if expected:
                assert _labels(path_service.get_relationship_paths(
                    first, second, max_depth=30, max_paths=50
                )) == expected


def test_general_connection_is_display_only():
    a = people.create_person(name="Alex Friend")
    b = people.create_person(name="Bo Friend")
    c = people.create_person(name="Cy Friend")
    general.add_general_relationship(person_a=a["id"], person_b=b["id"], type="friend")
    general.add_general_relationship(person_a=b["id"], person_b=c["id"], type="friend")
    direct = path_service.get_relationship_paths(a["id"], b["id"])["paths"][0]
    assert direct["domain"] == "general" and direct["derived"] is False
    route = path_service.get_relationship_paths(a["id"], c["id"])["paths"][0]
    assert route["domain"] == "connection"
    assert [edge["type"] for edge in route["edges"]] == ["general", "general"]
    endpoint = relationship.get_relationship(a["id"], c["id"])
    assert endpoint["primary"] == endpoint["additional"] == []


def test_mixed_general_and_family_route_is_display_only():
    outsider = people.create_person(name="Synthetic Route Outsider")
    general.add_general_relationship(person_a=outsider["id"], person_b=MIRA, type="friend")
    payload = path_service.get_relationship_paths(outsider["id"], ELIAS)
    mixed = next(path for path in payload["paths"] if path["domain"] == "connection")
    assert [edge["type"] for edge in mixed["edges"]] == ["general", "parent_child"]
    endpoint = relationship.get_relationship(outsider["id"], ELIAS)
    assert endpoint["primary"] == endpoint["additional"] == []


def test_graph_neighbor_filters_and_added_general_edge():
    parents = graph_service.get_graph_neighbors(MIRA, filters=["parents"])
    assert {node["id"] for node in parents["nodes"]} == {MIRA, ELIAS, SALMA}
    assert {edge["type"] for edge in parents["edges"]} == {"parent_child", "marriage"}
    siblings = graph_service.get_graph_neighbors(MIRA, filters=["siblings"])
    assert SAMI in {node["id"] for node in siblings["nodes"]}
    general_nodes = graph_service.get_graph_neighbors(MIRA, filters=["general"])["nodes"]
    assert DARYA in {node["id"] for node in general_nodes}
    friend = people.create_person(name="Graph Friend")
    general.add_general_relationship(person_a=MIRA, person_b=friend["id"], type="close_friend")
    result = graph_service.get_graph_neighbors(MIRA, perspective_id=MIRA, filters=["general"])
    assert friend["id"] in {node["id"] for node in result["nodes"]}
    assert any(edge["subtype"] == "close_friend" for edge in result["edges"] if edge["type"] == "general")
    with pytest.raises(errors.AppError) as exc:
        graph_service.get_graph_neighbors(MIRA, filters=["parents", "ancestors"])
    assert exc.value.code == "INVALID_FILTER"


def test_hermes_path_and_neighbor_tools():
    result = hermes.run_tool("get_relationship_paths", {
        "perspective": MIRA, "target": AIKA, "max_depth": 10, "max_paths": 10
    })
    assert result["ok"] is True
    assert _labels(result) == {"maternal first cousin", "paternal first cousin"}
    assert all("nodes" in path and "edges" in path for path in result["paths"])
    bounded = hermes.run_tool("get_relationship_paths", {
        "perspective": MIRA, "target": AIKA, "max_depth": 99
    })
    assert bounded["ok"] is False
    assert bounded["error"]["code"] == "INVALID_MAX_DEPTH"
    neighbors = hermes.run_tool("get_neighbors", {"person": MIRA, "filters": ["parents", "siblings"]})
    assert neighbors["ok"] is True
    assert {ELIAS, SALMA, SAMI} <= {node["id"] for node in neighbors["nodes"]}
