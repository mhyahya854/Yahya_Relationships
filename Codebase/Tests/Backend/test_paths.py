"""Relationship-path extraction, graph-neighbour and Hermes path tests."""

import pytest

from app.backend.domain.relationships import graph as graph_service
from app.backend.domain.relationships import path_service
from app.backend.hermes import tools as hermes
from app.backend.services import errors, general, people, relationship


def labels_of(payload):
    return {(path["label_en"] or "").casefold() for path in payload["paths"]}


def test_aresha_two_paths_are_distinct():
    payload = path_service.get_relationship_paths(
        "mohammad_yahya_hussain", "aresha_zubair"
    )
    path_labels = labels_of(payload)
    assert "paternal first cousin" in path_labels
    assert "maternal second cousin" in path_labels
    paths = payload["paths"]
    assert len(paths) == 2
    assert paths[0]["side"] == "paternal"
    assert paths[1]["side"] == "maternal"
    node_sets = [tuple(node["id"] for node in path["nodes"]) for path in paths]
    assert node_sets[0] != node_sets[1]
    assert len({path["id"] for path in paths}) == 2


def test_ezan_paths_preserve_engine_semantics():
    payload = path_service.get_relationship_paths(
        "mohammad_yahya_hussain", "ezan_asif"
    )
    by_label = {path["label_en"].casefold(): path for path in payload["paths"]}
    assert "maternal first cousin" in by_label
    assert "paternal second cousin" in by_label
    maternal = by_label["maternal first cousin"]
    assert maternal["degree"] == 1
    assert maternal["removal"] == 0
    assert maternal["side"] == "maternal"
    assert [node["name"] for node in maternal["nodes"]] == [
        "Mohammad Yahya Hussain",
        "Irsa Naz",
        "Shahnaz Israr",
        "Sadia Asif",
        "Ezan Asif",
    ]


def test_direct_parent_child_and_spouse_paths():
    father = path_service.get_relationship_paths(
        "mohammad_yahya_hussain", "mansoor_hussain"
    )["paths"]
    assert father[0]["label_en"].casefold() == "father"
    assert father[0]["distance"] == 1
    assert father[0]["edges"][0]["type"] == "parent_child"
    assert father[0]["edges"][0]["role"] == "is child of"
    assert father[0]["derived"] is False

    son = path_service.get_relationship_paths(
        "mansoor_hussain", "mohammad_yahya_hussain"
    )["paths"]
    assert son[0]["label_en"].casefold() == "son"
    assert son[0]["edges"][0]["role"] == "is parent of"

    spouse = path_service.get_relationship_paths("irsa_naz", "mansoor_hussain")[
        "paths"
    ]
    assert spouse[0]["label_en"].casefold() == "husband"
    assert spouse[0]["edges"][0]["type"] == "marriage"


def test_sibling_path_uses_shared_parent():
    payload = path_service.get_relationship_paths(
        "mohammad_yahya_hussain", "maham_mansoor"
    )
    path = payload["paths"][0]
    assert path["label_en"].casefold() == "sister"
    assert path["distance"] == 2
    assert [node["id"] for node in path["nodes"]][1] in (
        "irsa_naz",
        "mansoor_hussain",
    )
    assert {ancestor["id"] for ancestor in path["common_ancestors"]} == {
        "irsa_naz",
        "mansoor_hussain",
    }


def test_reverse_perspective_directionality():
    a = path_service.get_relationship_paths("ezan_asif", "irsa_naz")["paths"]
    b = path_service.get_relationship_paths("irsa_naz", "ezan_asif")["paths"]
    assert any(path["label_en"].casefold() == "maternal aunt" for path in a)
    assert any(path["label_en"].casefold() == "nephew" for path in b)


def test_no_loops_and_unique_ids():
    for first, second in (
        ("mohammad_yahya_hussain", "aresha_zubair"),
        ("mohammad_yahya_hussain", "ezan_asif"),
        ("irsa_naz", "ezan_asif"),
    ):
        payload = path_service.get_relationship_paths(
            first, second, max_depth=20, max_paths=30
        )
        ids = []
        for path in payload["paths"]:
            node_ids = [node["id"] for node in path["nodes"]]
            assert len(node_ids) == len(set(node_ids))
            ids.append(path["id"])
        assert len(ids) == len(set(ids))


def test_limit_validation():
    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths(
            "mohammad_yahya_hussain", "aresha_zubair", max_depth=0
        )
    assert exc.value.code == "INVALID_MAX_DEPTH"
    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths(
            "mohammad_yahya_hussain", "aresha_zubair", max_paths=51
        )
    assert exc.value.code == "INVALID_MAX_PATHS"


def test_max_depth_and_max_paths_bounds():
    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths(
            "mohammad_yahya_hussain", "aresha_zubair", max_depth=3
        )
    assert exc.value.code == "NO_RELATIONSHIP_PATH"

    payload = path_service.get_relationship_paths(
        "mohammad_yahya_hussain", "aresha_zubair", max_paths=1
    )
    assert len(payload["paths"]) == 1
    assert payload["truncated"] is True


def test_unknown_person_errors():
    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths("missing_person", "irsa_naz")
    assert exc.value.code == "NOT_FOUND"


def test_label_coverage_across_family_pairs():
    sample = [
        "mohammad_yahya_hussain",
        "maham_mansoor",
        "irsa_naz",
        "mansoor_hussain",
        "ezan_asif",
        "aresha_zubair",
        "abdul_rafey",
        "muaaz",
        "sohaib_hussain",
        "shahnaz_israr",
    ]
    for first in sample:
        for second in sample:
            if first == second:
                continue
            result = relationship.get_relationship(first, second)
            expected = {
                (item["label_en"] or "").casefold()
                for item in result["primary"] + result["additional"]
            }
            if not expected:
                continue
            payload = path_service.get_relationship_paths(
                first, second, max_depth=30, max_paths=50
            )
            actual = {
                (item["label_en"] or "").casefold()
                for item in payload["paths"]
            }
            assert actual == expected, f"{first} -> {second}"


def test_general_relationship_paths_and_no_transitive_inference(isolated):
    a = people.create_person(name="Alex Friend")
    b = people.create_person(name="Bo Friend")
    c = people.create_person(name="Cy Friend")
    mentor = people.create_person(name="Mentor Lead")
    general.add_general_relationship(
        person_a=a["id"], person_b=b["id"], type="friend"
    )
    general.add_general_relationship(
        person_a=b["id"], person_b=c["id"], type="friend"
    )
    general.add_general_relationship(
        person_a=mentor["id"],
        person_b=b["id"],
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )

    friend_path = path_service.get_relationship_paths(a["id"], b["id"])
    assert friend_path["paths"][0]["domain"] == "general"
    assert friend_path["paths"][0]["label_en"] == "Friend"
    assert friend_path["paths"][0]["derived"] is False

    with pytest.raises(errors.AppError) as exc:
        path_service.get_relationship_paths(a["id"], c["id"])
    assert exc.value.code == "NO_RELATIONSHIP_PATH"

    mentor_path = path_service.get_relationship_paths(mentor["id"], b["id"])
    assert mentor_path["paths"][0]["label_en"] == "Mentor"
    mentee_path = path_service.get_relationship_paths(b["id"], mentor["id"])
    assert mentee_path["paths"][0]["label_en"] == "Mentee"


def test_graph_neighbors_filters():
    parents = graph_service.get_graph_neighbors(
        "mohammad_yahya_hussain", filters=["parents"]
    )
    parent_ids = {node["id"] for node in parents["nodes"]}
    assert parent_ids == {
        "mohammad_yahya_hussain",
        "irsa_naz",
        "mansoor_hussain",
    }
    assert {"irsa_naz", "mansoor_hussain"} <= {
        node["id"] for node in parents["nodes"]
    }
    edge_types = {edge["type"] for edge in parents["edges"]}
    assert edge_types == {"parent_child", "marriage"}

    siblings = graph_service.get_graph_neighbors(
        "mohammad_yahya_hussain", filters=["siblings"]
    )
    assert {"maham_mansoor"} <= {
        node["id"] for node in siblings["nodes"]
    }

    general_result = graph_service.get_graph_neighbors(
        "mohammad_yahya_hussain", filters=["general"]
    )
    assert len(general_result["nodes"]) == 1


def test_graph_neighbors_general_after_add(isolated):
    friend = people.create_person(name="Graph Friend")
    general.add_general_relationship(
        person_a="mohammad_yahya_hussain",
        person_b=friend["id"],
        type="close_friend",
    )
    result = graph_service.get_graph_neighbors(
        "mohammad_yahya_hussain",
        perspective_id="mohammad_yahya_hussain",
        filters=["general"],
    )
    assert friend["id"] in {node["id"] for node in result["nodes"]}
    general_edges = [
        edge for edge in result["edges"] if edge["type"] == "general"
    ]
    assert len(general_edges) == 1
    assert general_edges[0]["subtype"] == "close_friend"


def test_invalid_filter_error():
    with pytest.raises(errors.AppError) as exc:
        graph_service.get_graph_neighbors(
            "mohammad_yahya_hussain", filters=["parents", "ancestors"]
        )
    assert exc.value.code == "INVALID_FILTER"


def test_hermes_path_tool_structured():
    result = hermes.run_tool(
        "get_relationship_paths",
        {
            "perspective": "mohammad_yahya_hussain",
            "target": "aresha_zubair",
            "max_depth": 10,
            "max_paths": 10,
        },
    )
    assert result["ok"] is True
    assert len(result["paths"]) == 2
    assert result["paths"][0]["label_en"] == "paternal first cousin"
    assert "nodes" in result["paths"][0]
    assert "edges" in result["paths"][0]


def test_hermes_path_tool_errors():
    bounded = hermes.run_tool(
        "get_relationship_paths",
        {
            "perspective": "mohammad_yahya_hussain",
            "target": "aresha_zubair",
            "max_depth": 99,
        },
    )
    assert bounded["ok"] is False
    assert bounded["error"]["code"] == "INVALID_MAX_DEPTH"

    ambiguous = hermes.run_tool(
        "get_relationship_paths",
        {"perspective": "a", "target": "b"},
    )
    assert ambiguous["ok"] is False
    assert ambiguous["error"]["code"] in ("PERSON_AMBIGUOUS", "NOT_FOUND")


def test_hermes_neighbor_tool():
    result = hermes.run_tool(
        "get_neighbors",
        {"person": "mansoor_hussain", "filters": ["parents", "siblings"]},
    )
    assert result["ok"] is True
    ids = {node["id"] for node in result["nodes"]}
    assert {"abrar_hussain", "shaheen_abrar", "hina", "sana", "afshan"} <= ids
