from __future__ import annotations

from app.backend.domain.family import engine
from app.backend.model import load_model
from app.backend.services import relationship


def test_display_ranking_is_single_deterministic_and_lossless(isolated):
    first = relationship.get_relationship(
        "mohammad_yahya_hussain", "aresha_zubair"
    )
    second = relationship.get_relationship(
        "mohammad_yahya_hussain", "aresha_zubair"
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
        "mohammad_yahya_hussain", "sohaib_hussain"
    )

    assert result["primary"][0]["label_en"] == "Maternal uncle"
    assert any(
        entry["label_en"] == "paternal first cousin once removed"
        for entry in result["additional"]
    )


def test_list_and_pair_queries_use_the_same_display_ranking(isolated):
    listed = next(
        row
        for row in relationship.list_relationships_from("mohammad_yahya_hussain")
        if row["target"]["id"] == "sohaib_hussain"
    )
    pair = relationship.get_relationship(
        "mohammad_yahya_hussain", "sohaib_hussain"
    )

    assert listed["primary"][0]["semantic_id"] == pair["primary"][0]["semantic_id"]
    assert len(listed["primary"]) == 1
    assert len(pair["primary"]) == 1


def test_culturally_meaningful_affinal_roles_keep_real_proof_paths(isolated):
    result = relationship.get_relationship(
        "mohammad_yahya_hussain", "rubinna"
    )
    mami = next(
        entry
        for entry in result["primary"] + result["additional"]
        if entry["semantic_id"] == "mami"
    )

    assert mami["label_ur"] == "ممانی"
    assert mami["derived"] is True
    assert mami["side"] == "maternal"
    assert mami["path_ids"]


def test_family_union_routes_only_to_real_person_nodes(isolated):
    diagram = engine.build_mermaid(load_model())

    # The two spouses remain separate people inside one visual-only union.
    assert 'subgraph u_irsa_naz__mansoor_hussain[" "]' in diagram
    assert "p_irsa_naz ---|" in diagram
    assert "| p_mansoor_hussain" in diagram

    # Each spouse independently receives ancestry on their own person node.
    assert "j_israr_hussain__shahnaz_israr --> p_irsa_naz" in diagram
    assert "j_abrar_hussain__shaheen_abrar --> p_mansoor_hussain" in diagram

    # Shared children descend from a separate junction fed by both spouses.
    assert "p_irsa_naz -->|" in diagram
    assert "p_mansoor_hussain --> j_irsa_naz__mansoor_hussain" in diagram
    assert "j_irsa_naz__mansoor_hussain --> p_mohammad_yahya_hussain" in diagram

    # A union wrapper is never a semantic edge endpoint.
    edge_lines = [line for line in diagram.splitlines() if "-->" in line or "---" in line]
    assert all(" u_" not in line and not line.lstrip().startswith("u_") for line in edge_lines)
