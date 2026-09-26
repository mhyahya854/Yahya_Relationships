from __future__ import annotations

from app.backend.domain.family import engine
from app.backend.model import load_model
from app.backend.services import relationship
from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")
AIKA = generate_canonical_person_id("Aika Calder-Rahim")
LAYLA = generate_canonical_person_id("Layla Rahim")
KAMAL = generate_canonical_person_id("Kamal Calder")
ELIAS = generate_canonical_person_id("Elias Calder")
SALMA = generate_canonical_person_id("Salma Rahim")
QADIR = generate_canonical_person_id("Qadir Rahim")
MAHIRA = generate_canonical_person_id("Mahira Rahim")
ADNAN = generate_canonical_person_id("Adnan Calder")
SORAYA = generate_canonical_person_id("Soraya Calder")


def test_display_ranking_is_single_deterministic_and_lossless(isolated):
    first = relationship.get_relationship(
        MIRA, AIKA
    )
    second = relationship.get_relationship(
        MIRA, AIKA
    )

    assert len(first["primary"]) == 1
    assert first == second
    assert len(first["additional"]) >= 1
    assert {entry.get("side") for entry in first["primary"] + first["additional"]} >= {
        "maternal",
        "paternal",
    }


def test_family_role_ranks_ahead_of_more_indirect_family_path(isolated):
    result = relationship.get_relationship(
        MIRA, LAYLA
    )

    assert result["primary"][0]["label_en"] == "Maternal aunt"
    assert any(
        entry["label_en"] == "Paternal uncle's wife"
        for entry in result["additional"]
    )


def test_list_and_pair_queries_use_the_same_display_ranking(isolated):
    listed = next(
        row
        for row in relationship.list_relationships_from(MIRA)
        if row["target"]["id"] == LAYLA
    )
    pair = relationship.get_relationship(
        MIRA, LAYLA
    )

    assert listed["primary"][0]["semantic_id"] == pair["primary"][0]["semantic_id"]
    assert len(listed["primary"]) == 1
    assert len(pair["primary"]) == 1


def test_culturally_meaningful_affinal_roles_keep_real_proof_paths(isolated):
    result = relationship.get_relationship(
        MIRA, KAMAL
    )
    affinal = next(
        entry
        for entry in result["primary"] + result["additional"]
        if entry["semantic_id"] == "khalu"
    )

    assert affinal["label_ur"]
    assert affinal["derived"] is True
    assert affinal["side"] == "maternal"
    assert affinal["path_ids"]


def test_family_union_routes_only_to_real_person_nodes(isolated):
    diagram = engine.build_mermaid(load_model())

    couple = tuple(sorted((ELIAS, SALMA)))
    union = engine._cluster_id(couple)
    junction = engine._junction_id(couple)
    father = engine._person_node_id(ELIAS)
    mother = engine._person_node_id(SALMA)
    child = engine._person_node_id(MIRA)
    assert f'subgraph {union}[" "]' in diagram
    assert f"{father} ---|" in diagram
    assert f"| {mother}" in diagram

    # Each spouse independently receives ancestry on their own person node.
    assert f"{engine._junction_id(tuple(sorted((QADIR, MAHIRA))))} --> {mother}" in diagram
    assert f"{engine._junction_id(tuple(sorted((ADNAN, SORAYA))))} --> {father}" in diagram

    # Shared children descend from a separate junction fed by both spouses.
    assert f"{father} -->|" in diagram
    assert f"{mother} --> {junction}" in diagram
    assert f"{junction} --> {child}" in diagram

    # A union wrapper is never a semantic edge endpoint.
    edge_lines = [line for line in diagram.splitlines() if "-->" in line or "---" in line]
    assert all(" u_" not in line and not line.lstrip().startswith("u_") for line in edge_lines)
