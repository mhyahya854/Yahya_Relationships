"""Family write validation mirrors the legacy builder guarantees."""

import pytest

from app.backend.services import errors, family
from app.backend.domain.canonical.ids import generate_canonical_person_id

MIRA = generate_canonical_person_id("Mira Rahim")
SALMA = generate_canonical_person_id("Salma Rahim")
QADIR = generate_canonical_person_id("Qadir Rahim")
DARYA = generate_canonical_person_id("Darya Sol")
QUINN = generate_canonical_person_id("Quinn Aster")


def test_self_parent_rejected(isolated):
    with pytest.raises(errors.AppError) as exc:
        family.add_parent_child(
            parent_id=MIRA,
            child_id=MIRA,
        )
    assert exc.value.code == "SELF_PARENT"


def test_duplicate_parent_edge_rejected(isolated):
    with pytest.raises(errors.AppError) as exc:
        family.add_parent_child(
            parent_id=SALMA, child_id=MIRA
        )
    assert exc.value.code == "DUPLICATE_FACT"


def test_ancestry_cycle_rejected(isolated):
    with pytest.raises(errors.AppError) as exc:
        family.add_parent_child(
            parent_id=MIRA,
            child_id=QADIR,
            role="parent",
        )
    assert exc.value.code == "FAMILY_VALIDATION"
    assert "Ancestry cycle" in exc.value.message


def test_unknown_person_rejected(isolated):
    with pytest.raises(errors.AppError) as exc:
        family.add_parent_child(parent_id="missing_person", child_id=MIRA)
    assert exc.value.code == "NOT_FOUND"


def test_self_marriage_rejected(isolated):
    with pytest.raises(errors.AppError) as exc:
        family.add_marriage(
            person_a=MIRA,
            person_b=MIRA,
        )
    assert exc.value.code == "SELF_MARRIAGE"


def test_valid_family_write_and_audits(isolated):
    from app.backend.services import people

    child = people.create_person(name="New Child Person")
    parent = people.create_person(name="New Parent Person")
    result = family.add_parent_child(
        parent_id=parent["id"], child_id=child["id"], role="parent"
    )
    assert result["ok"] is True
    marriage = family.add_marriage(
        person_a=DARYA,
        person_b=parent["id"],
    )
    assert marriage["ok"] is True
    sibling = family.add_sibling_group(member_ids=[parent["id"], QUINN])
    assert sibling["ok"] is True


def test_single_person_marriage_conflict_rejected(isolated):
    from app.backend.services import people

    single = people.create_person(name="Single New Person", marital_status="single")
    with pytest.raises(errors.AppError) as exc:
        family.add_marriage(person_a=single["id"], person_b=QUINN)
    assert exc.value.code == "FAMILY_VALIDATION"
