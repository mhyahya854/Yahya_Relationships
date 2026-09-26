"""Relationship engine tests: perspective, multiple paths, reversal,
generic relationships and no transitive inference."""

from app.backend.services import general, people, relationship
from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")
AIKA = generate_canonical_person_id("Aika Calder-Rahim")
ELIAS = generate_canonical_person_id("Elias Calder")
SALMA = generate_canonical_person_id("Salma Rahim")
SAMI = generate_canonical_person_id("Sami Calder")
LAYLA = generate_canonical_person_id("Layla Rahim")
NOOR = generate_canonical_person_id("Noor Rahim")


def test_reversal_is_directional():
    a = relationship.get_relationship(SALMA, NOOR)
    b = relationship.get_relationship(NOOR, SALMA)
    assert [x["label_en"] for x in a["primary"]] == ["Niece"]
    assert [x["label_en"] for x in b["primary"]] == ["Maternal aunt"]


def test_multiple_simultaneous_paths_are_preserved():
    result = relationship.get_relationship(
        MIRA, AIKA
    )
    primary = {x["label_en"] for x in result["primary"]}
    additional = {x["label_en"] for x in result["additional"]}
    assert "maternal first cousin" in primary
    assert "paternal first cousin" in additional

    result = relationship.get_relationship(
        AIKA, MIRA
    )
    primary = {x["label_en"] for x in result["primary"]}
    additional = {x["label_en"] for x in result["additional"]}
    assert {"paternal first cousin", "maternal first cousin"} == primary | additional
    assert primary and additional


def test_direct_and_cousin_paths_on_compare():
    comparison = relationship.compare_people(MIRA, AIKA)
    for direction in ("a_to_b", "b_to_a"):
        paths = comparison[direction]["primary"] + comparison[direction]["additional"]
        assert {"paternal first cousin", "maternal first cousin"} <= {p["label_en"] for p in paths}


def test_self_relationship():
    result = relationship.get_relationship(
        MIRA, MIRA
    )
    assert result["primary"][0]["relationship_type"] == "self"


def test_compare_arbitrary_people_without_owner():
    comparison = relationship.compare_people(SALMA, ELIAS)
    assert [x["label_en"] for x in comparison["a_to_b"]["primary"]] == ["Husband"]
    assert [x["label_en"] for x in comparison["b_to_a"]["primary"]] == ["Wife"]


def test_symmetric_general_relationship(isolated):
    a = people.create_person(name="Ali Test")
    b = people.create_person(name="Bilal Test")
    row = general.add_general_relationship(
        person_a=a["id"],
        person_b=b["id"],
        type="close_friend",
    )
    assert row["label_a_to_b"] == "Close friend"
    result_a = relationship.get_relationship(a["id"], b["id"])
    result_b = relationship.get_relationship(b["id"], a["id"])
    assert result_a["primary"][0]["label_en"] == "Close friend"
    assert result_b["primary"][0]["label_en"] == "Close friend"


def test_directional_general_relationship(isolated):
    mentor = people.create_person(name="Senior Test")
    mentee = people.create_person(name="Junior Test")
    general.add_general_relationship(
        person_a=mentor["id"],
        person_b=mentee["id"],
        type="mentor",
        directionality="directional",
        label_a_to_b="Mentor",
        label_b_to_a="Mentee",
    )
    result = relationship.get_relationship(mentor["id"], mentee["id"])
    assert result["primary"][0]["label_en"] == "Mentor"
    reverse = relationship.get_relationship(mentee["id"], mentor["id"])
    assert reverse["primary"][0]["label_en"] == "Mentee"


def test_no_transitive_friend_inference(isolated):
    a = people.create_person(name="Alice Test")
    b = people.create_person(name="Bob Test")
    c = people.create_person(name="Carol Test")
    general.add_general_relationship(person_a=a["id"], person_b=b["id"], type="friend")
    general.add_general_relationship(person_a=b["id"], person_b=c["id"], type="friend")
    direct = relationship.get_relationship(a["id"], c["id"])
    assert direct["primary"] == []
    assert direct["additional"] == []


def test_list_relationships_from(isolated):
    rows = relationship.list_relationships_from(MIRA)
    by_id = {row["target"]["id"]: row for row in rows}
    assert SAMI in by_id
    assert any(
        x["label_en"] == "Full brother" for x in by_id[SAMI]["primary"]
    )
    assert any(
        x["label_en"] == "Maternal aunt" for x in by_id[LAYLA]["primary"]
    )
