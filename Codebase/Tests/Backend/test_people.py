"""Comprehensive backend tests for People and Person Profile services.

Covers:
- Listing people & canonical uniqueness
- Person creation with single and multiple groups
- Person editing & group updates without duplication
- Alias handling (including Urdu aliases)
- Duplicate detection warning logic vs legitimate same-name people
- Person profile aggregate data (family facts, general relationships, perspective summary, journal)
- Perspective-aware relationship interpretation & multiple paths preservation
- Journal safety across metadata/group edits
- Removal consequence preview
- Removal and filesystem-aware Undo restoring database & journal.md
- Path traversal prevention & invalid IDs
- Unicode names and spaces
"""

from pathlib import Path
import pytest

from app.backend import config, db
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.mutations import history as mutation_history, preview as mutation_preview
from app.backend.services import errors, general, journals, people, relationship


def test_list_people_and_canonical_uniqueness(isolated):
    all_people = people.list_people()
    assert len(all_people) == 35

    # Canonical uniqueness: every ID is unique
    ids = [p["id"] for p in all_people]
    assert len(ids) == len(set(ids))

    # Every person has required canonical fields
    for p in all_people:
        assert p["id"]
        assert p["name"]
        assert isinstance(p["aliases"], list)
        assert isinstance(p["groups"], list)
        assert len(p["groups"]) >= 1


def test_create_person_with_multiple_groups(isolated):
    p = people.create_person(
        name="Tariq Ahmad",
        aliases=["Uncle Tariq", "طارق احمد"],
        birth_year=1975,
        gender="male",
        group_ids=["family", "friends"],
        primary_group_id="family",
    )
    assert p["name"] == "Tariq Ahmad"
    assert "Uncle Tariq" in p["aliases"]
    assert "طارق احمد" in p["aliases"]
    assert p["birth_year"] == 1975
    assert p["gender"] == "male"

    group_ids = [g["id"] for g in p["groups"]]
    assert "family" in group_ids
    assert "friends" in group_ids

    primary_group = next(g for g in p["groups"] if g["is_primary"])
    assert primary_group["id"] == "family"

    # Canonical folder should be created under primary group
    folder = Path(p["folder"])
    assert folder.exists()
    assert (folder / "journal.md").exists()


def test_update_person_groups_and_metadata_without_duplication(isolated):
    p = people.create_person(
        name="Kareem Khan",
        group_ids=["friends"],
        primary_group_id="friends",
    )
    pid = p["id"]

    # Write some journal content
    journals.save_journal(pid, "# Kareem's Journal\n\nInitial thoughts.")

    # Update metadata and add another group
    updated = people.update_person(
        pid,
        name="Kareem Ahmad Khan",
        aliases=["KK"],
        birth_year=1990,
        gender="male",
        group_ids=["friends", "colleagues"],
        primary_group_id="friends",
        note_en="Great friend and colleague",
    )

    assert updated["id"] == pid
    assert updated["name"] == "Kareem Ahmad Khan"
    assert updated["aliases"] == ["KK"]
    assert updated["birth_year"] == 1990
    assert updated["note_en"] == "Great friend and colleague"

    group_ids = [g["id"] for g in updated["groups"]]
    assert "friends" in group_ids
    assert "colleagues" in group_ids

    # Canonical uniqueness check: only one record exists in people table
    connection = db.get_connection()
    try:
        count = connection.execute("SELECT COUNT(*) FROM people WHERE id = ?", (pid,)).fetchone()[0]
        assert count == 1
    finally:
        connection.close()

    # Verify journal content is completely intact
    j = journals.read_journal(pid)
    assert "# Kareem's Journal" in j["content"]


def test_journal_safety_when_primary_group_changes(isolated):
    p = people.create_person(
        name="Salma Begum",
        group_ids=["colleagues"],
        primary_group_id="colleagues",
    )
    pid = p["id"]
    journals.save_journal(pid, "Memories of project Alpha with Salma.")

    # Relocate primary group from colleagues to close_friends
    updated = people.update_person(
        pid,
        group_ids=["close_friends", "colleagues"],
        primary_group_id="close_friends",
    )
    assert updated["id"] == pid

    # Verify folder moved and journal remains intact
    j = journals.read_journal(pid)
    assert "Memories of project Alpha with Salma." in j["content"]
    assert "close_friends" in j["path"].lower() or "close friends" in j["path"].lower()


def test_duplicate_detection_and_legitimate_same_name_people(isolated):
    # Candidate checking
    existing = people.create_person(name="Hamza Tariq", aliases=["Hamzi"])
    
    # Exact match check
    dupes = people.check_duplicate_person("Hamza Tariq")
    assert any(d["id"] == existing["id"] and d["reason"] == "exact name match" for d in dupes)

    # Substring / token overlap match
    dupes_partial = people.check_duplicate_person("Hamza")
    assert any(d["id"] == existing["id"] for d in dupes_partial)

    # Alias match
    dupes_alias = people.check_duplicate_person("Hamzi")
    assert any(d["id"] == existing["id"] for d in dupes_alias)

    # Legitimate same-name person creation:
    # A user can legitimately have a cousin or son with the exact same name
    junior = people.create_person(name="Hamza Tariq", birth_year=2015)
    assert junior["id"] != existing["id"]
    assert junior["name"] == "Hamza Tariq"
    assert junior["birth_year"] == 2015

    # Both records are canonical and distinct
    assert people.get_person(existing["id"])["id"] == existing["id"]
    assert people.get_person(junior["id"])["id"] == junior["id"]


def test_get_person_profile_comprehensive(isolated):
    # Test on a real known production baseline person: mansoor_hussain
    profile = people.get_person_profile("mansoor_hussain", perspective_id="mohammad_yahya_hussain")
    
    # Person brief
    p = profile["person"]
    assert p["id"] == "mansoor_hussain"
    assert p["name"] == "Mansoor Hussain"

    # Family facts
    family_facts = profile["family"]
    assert "parents" in family_facts
    assert "spouses" in family_facts
    assert "children" in family_facts
    assert "siblings" in family_facts

    # Mansoor Hussain has child Mohammad Yahya Hussain
    child_ids = [c["id"] for c in family_facts["children"]]
    assert "mohammad_yahya_hussain" in child_ids

    # Perspective relationship: From Yahya to Mansoor = Father
    perspective = profile["perspective"]
    assert perspective is not None
    primary_labels = [x["label_en"] for x in perspective["primary"]]
    assert "Father" in primary_labels

    # Journal
    assert "journal" in profile
    assert profile["journal"]["path"] is not None


def test_profile_perspective_multiple_paths(isolated):
    # Aresha Zubair has two valid derived kinship paths from Mohammad Yahya Hussain:
    # 1. Paternal first cousin
    # 2. Maternal second cousin
    profile = people.get_person_profile("aresha_zubair", perspective_id="mohammad_yahya_hussain")
    perspective = profile["perspective"]
    assert perspective is not None

    primary = {x["label_en"].lower() for x in perspective["primary"]}
    additional = {x["label_en"].lower() for x in perspective["additional"]}
    assert "paternal first cousin" in primary
    assert "maternal second cousin" in additional


def test_profile_with_general_relationships(isolated):
    p1 = people.create_person(name="Farhan Saeed")
    p2 = people.create_person(name="Danish Taimoor")

    general.add_general_relationship(
        person_a=p1["id"],
        person_b=p2["id"],
        type="colleague",
        directionality="symmetric",
        label_a_to_b="Colleague",
        label_b_to_a="Colleague",
        notes="Worked together on frontend",
    )

    profile1 = people.get_person_profile(p1["id"])
    assert len(profile1["general"]) == 1
    gen_entry = profile1["general"][0]
    assert gen_entry["other_person"]["id"] == p2["id"]
    assert gen_entry["label"] == "Colleague"
    assert gen_entry["notes"] == "Worked together on frontend"


def test_person_removal_preview_and_safety_checks(isolated):
    # Preview deleting Mansoor Hussain (who is central to the family tree)
    preview = mutation_preview.preview_mutation("delete_person", {"person_id": "mansoor_hussain"})
    assert preview["valid"] is False
    assert preview["code"] == "INVALID_FAMILY_GRAPH"
    assert len(preview["warnings"]) > 0
    assert "Remove those family facts before deleting" in preview["warnings"][0]

    # Attempting to delete Mansoor Hussain without removing family facts must be blocked
    with pytest.raises(errors.InvalidOperationError) as exc_info:
        people.delete_person("mansoor_hussain", force=True)
    assert exc_info.value.code == "PERSON_IN_FAMILY_GRAPH"

    # Preview deleting a standalone person without family facts should be valid
    temp = people.create_person(name="Standalone Person", group_ids=["other"])
    temp_preview = mutation_preview.preview_mutation("delete_person", {"person_id": temp["id"]})
    assert temp_preview["valid"] is True
    assert any("Delete canonical person: Standalone Person" in c for c in temp_preview["direct_changes"])


def test_person_removal_and_filesystem_aware_undo(isolated):
    # Create a synthetic standalone person
    p = people.create_person(name="Zainab Noor", group_ids=["friends"], primary_group_id="friends")
    pid = p["id"]
    journals.save_journal(pid, "Memories of college days with Zainab.")

    people_dir = DataRootManager.get_people_dir(isolated)
    active_folder = people_dir / "Friends" / pid
    assert active_folder.exists()
    assert (active_folder / "journal.md").exists()

    # Preview removal
    preview = mutation_preview.preview_mutation("delete_person", {"person_id": pid})
    assert preview["valid"] is True
    assert any("Delete canonical person: Zainab Noor" in c for c in preview["direct_changes"])

    # Remove person
    del_res = people.delete_person(pid, force=True)
    assert del_res["deleted"] == pid
    assert not active_folder.exists()

    archived_folder = Path(del_res["folder_archived"])
    assert archived_folder.exists()
    assert (archived_folder / "journal.md").exists()

    # Undo removal
    undo_res = mutation_history.undo_last_mutation()
    assert undo_res["ok"] is True

    # Folder and journal restored to original location
    assert active_folder.exists()
    assert (active_folder / "journal.md").exists()
    assert not archived_folder.exists()

    # DB record restored
    restored = people.get_person(pid)
    assert restored["name"] == "Zainab Noor"

    # Journal read verifies content preserved
    j = journals.read_journal(pid)
    assert "Memories of college days with Zainab." in j["content"]


def test_invalid_ids_and_path_traversal_prevention(isolated):
    with pytest.raises(errors.ValidationError):
        people.create_person(name="")

    with pytest.raises(errors.ValidationError):
        people.create_person(name="   ")

    with pytest.raises(errors.ValidationError):
        journals.read_journal("../../../etc/passwd")

    with pytest.raises(errors.ValidationError):
        journals.read_journal("..\\..\\windows\\system32")


def test_unicode_names_and_spaces(isolated):
    unicode_person = people.create_person(
        name="محمد علی خان",
        aliases=["Muhammad Ali Khan", "علی بھائی"],
        note_en="Special uncle",
        note_ur="بہترین انسان",
        group_ids=["family"],
    )
    assert unicode_person["name"] == "محمد علی خان"
    assert "علی بھائی" in unicode_person["aliases"]

    # Journal save & read
    journals.save_journal(unicode_person["id"], "خاندانی یادداشتیں\n\nبہت اچھے انسان ہیں۔")
    j = journals.read_journal(unicode_person["id"])
    assert "خاندانی یادداشتیں" in j["content"]
