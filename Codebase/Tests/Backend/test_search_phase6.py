"""Phase 6 deterministic Search acceptance tests."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from app.backend import db
from app.backend.data_root.manager import DataRootManager
from app.backend.services import journals, search, state


def _results(query: str, perspective: str = "mohammad_yahya_hussain", limit: int = 100) -> list[dict]:
    return search.search(query, perspective_id=perspective, limit=limit)["results"]


def _insert_person(person_id: str, name: str, display_order: int = 900, aliases: tuple[str, ...] = ()) -> None:
    connection = db.get_connection()
    try:
        connection.execute(
            "INSERT INTO people (id, name, display_order) VALUES (?, ?, ?)",
            (person_id, name, display_order),
        )
        for order, alias in enumerate(aliases):
            connection.execute(
                "INSERT INTO aliases (person_id, alias, display_order) VALUES (?, ?, ?)",
                (person_id, alias, order),
            )
        connection.commit()
    finally:
        connection.close()


def _insert_general(
    first: str,
    second: str,
    *,
    type_: str = "phase6_type",
    directionality: str = "directional",
    label_a_to_b: str = "guides",
    label_b_to_a: str = "guided by",
    notes: str = "Phase 6 relationship note",
) -> int:
    person_a, person_b = sorted((first, second))
    connection = db.get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO general_relationships
              (person_a, person_b, type, directionality, direction_from,
               label_a_to_b, label_b_to_a, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_a,
                person_b,
                type_,
                directionality,
                person_a if directionality == "directional" else None,
                label_a_to_b,
                label_b_to_a,
                notes,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def test_empty_query_is_pure_and_preserves_original(isolated):
    payload = search.search("  \t ", perspective_id="mohammad_yahya_hussain")
    assert payload["query"] == "  \t "
    assert payload["normalized_query"] == ""
    assert payload["results"] == []


def test_outer_whitespace_is_trimmed_for_matching_but_preserved_for_display(isolated):
    payload = search.search("  Maaz  ", perspective_id="mohammad_yahya_hussain")
    assert payload["query"] == "  Maaz  "
    assert payload["normalized_query"] == "maaz"
    assert any(item["result_id"] == "person:muaaz" for item in payload["results"])


def test_response_identifies_explicit_perspective(isolated):
    payload = search.search("niece", perspective_id="mansoor_hussain")
    assert payload["perspective"] == {"id": "mansoor_hussain", "name": "Mansoor Hussain"}
    assert all(item.get("perspective_id") == "mansoor_hussain" for item in payload["results"])


def test_service_defaults_to_current_state_not_model_focus(isolated):
    state.set_perspective("mansoor_hussain")
    payload = search.search("niece")
    assert payload["perspective"]["id"] == "mansoor_hussain"
    assert any(item["title"] == "Aresha Zubair" for item in payload["results"])


def test_api_accepts_explicit_perspective(client):
    payload = client.get(
        "/api/search",
        params={"q": "niece", "perspective_id": "mansoor_hussain"},
    ).json()
    assert payload["ok"] is True
    assert payload["perspective"]["id"] == "mansoor_hussain"


def test_unknown_perspective_is_rejected(client):
    response = client.get("/api/search", params={"q": "father", "perspective_id": "missing_person"})
    assert response.status_code == 404


@pytest.mark.parametrize("query", ["mohammad yahya hussain", "MOHAMMAD YAHYA HUSSAIN"])
def test_exact_canonical_person_match(query, isolated):
    person = next(item for item in _results(query) if item["category"] == "PERSON")
    assert person["result_id"] == "person:mohammad_yahya_hussain"
    assert person["match_kind"] == "exact_name"
    assert person["matched_alias"] is None


def test_exact_alias_match_explains_alias(isolated):
    _insert_person("phase6_alias", "Canonical Person", aliases=("Secret Handle",))
    result = next(item for item in _results("secret handle") if item["person_id"] == "phase6_alias")
    assert result["match_kind"] == "exact_alias"
    assert result["match"] == "Alias: Secret Handle"


def test_person_ranking_contract_and_deduplication(isolated):
    fixtures = (
        ("rank_exact_name", "Zen", ()),
        ("rank_exact_alias", "Alpha", ("Zen",)),
        ("rank_name_prefix", "Zenith", ()),
        ("rank_alias_prefix", "Beta", ("Zeno",)),
        ("rank_name_substring", "A Zen Middle", ()),
        ("rank_alias_substring", "Gamma", ("My Zen Tag", "Second Zen Alias")),
    )
    for order, (person_id, name, aliases) in enumerate(fixtures, start=900):
        _insert_person(person_id, name, order, aliases)
    people = [item for item in _results("zen") if item["category"] == "PERSON"]
    ids = [item["person_id"] for item in people if str(item["person_id"]).startswith("rank_")]
    assert ids == [item[0] for item in fixtures]
    assert ids.count("rank_alias_substring") == 1


@pytest.mark.parametrize(
    ("name", "alias", "query", "expected_kind"),
    [
        ("Exact Canonical", None, "exact canonical", "exact_name"),
        ("Alias Owner", "Exact Alias", "exact alias", "exact_alias"),
        ("Prefix Canonical", None, "prefix can", "name_prefix"),
        ("Prefix Alias Owner", "Alias Prefix Value", "alias pre", "alias_prefix"),
        ("Inside Canonical Value", None, "canonical", "name_substring"),
        ("Final Alias Owner", "Value Inside Alias", "inside", "alias_substring"),
    ],
)
def test_each_person_match_classification(name, alias, query, expected_kind, isolated):
    person_id = f"match_{expected_kind}"
    _insert_person(person_id, name, aliases=(alias,) if alias else ())
    result = next(item for item in _results(query) if item.get("person_id") == person_id)
    assert result["match_kind"] == expected_kind


@pytest.mark.parametrize(
    ("name", "query"),
    [
        ("Café Person", "Cafe\u0301"),
        ("Ｆｕｌｌｗｉｄｔｈ Person", "fullwidth"),
        ("O'Brien_Test", "O'BRIEN_"),
        ("Percent % Person", "%"),
        ("Emoji 😀 Person", "😀"),
        ('Double " Quote Person', '"'),
        ("Angle <tag> Person", "<tag>"),
        ("Backslash \\ Person", "\\"),
        ("Bracket [safe] Person", "[safe]"),
        ("اردو شخص", "اردو"),
        ("Mixed شخص Person", "شخص Person"),
    ],
)
def test_unicode_and_literal_person_matching(name, query, isolated):
    person_id = f"literal_{hashlib.sha256(name.encode('utf-8')).hexdigest()[:12]}"
    _insert_person(person_id, name)
    matches = [item for item in _results(query) if item["category"] == "PERSON"]
    assert [item["person_id"] for item in matches] == [person_id]


def test_no_transliteration_or_fuzzy_matching(isolated):
    _insert_person("urdu_only", "یحییٰ")
    assert all(item.get("person_id") != "urdu_only" for item in _results("yahya"))
    assert all(item.get("person_id") != "urdu_only" for item in _results("یحیا"))


def test_urdu_alias_matches_and_explains_canonical_person(isolated):
    _insert_person("urdu_alias", "Canonical Urdu Alias Owner", aliases=("محفوظ عرف",))
    result = next(item for item in _results("محفوظ عرف") if item.get("person_id") == "urdu_alias")
    assert result["match_kind"] == "exact_alias"
    assert result["matched_alias"] == "محفوظ عرف"


def test_stable_result_ids_and_order_across_repeated_searches(isolated):
    first = _results("friend")
    second = _results("friend")
    assert [item["result_id"] for item in first] == [item["result_id"] for item in second]
    assert len({item["result_id"] for item in first}) == len(first)


def test_group_result_contains_canonical_members(isolated):
    result = next(item for item in _results("family") if item["category"] == "GROUP")
    assert result["result_id"] == "group:family"
    assert result["group_id"] == "family"
    assert result["member_count"] == len(result["member_ids"]) > 0
    assert len(result["member_ids"]) == len(set(result["member_ids"]))


def test_group_prefix_matching_is_literal_and_stable(isolated):
    first = [item["result_id"] for item in _results("close fri") if item["category"] == "GROUP"]
    second = [item["result_id"] for item in _results("CLOSE FRI") if item["category"] == "GROUP"]
    assert first == second == ["group:close_friends"]


@pytest.mark.parametrize(
    ("query", "matched_field"),
    [
        ("phase6_type", "type"),
        ("guides", "label_a_to_b"),
        ("guided by", "label_b_to_a"),
        ("relationship note", "notes"),
    ],
)
def test_general_relationship_searches_every_field(query, matched_field, isolated):
    _insert_person("general_a", "General A")
    _insert_person("general_b", "General B")
    relationship_id = _insert_general("general_a", "general_b")
    result = next(item for item in _results(query) if item.get("relationship_id") == relationship_id)
    assert matched_field in result["matched_fields"]
    assert result["result_id"] == f"general:{relationship_id}"


def test_directional_general_result_preserves_both_directions(isolated):
    _insert_person("direction_a", "Direction A")
    _insert_person("direction_b", "Direction B")
    relationship_id = _insert_general("direction_b", "direction_a", label_a_to_b="coaches", label_b_to_a="coached by")
    result = next(item for item in _results("coach") if item.get("relationship_id") == relationship_id)
    assert result["directionality"] == "directional"
    assert result["direction_from"] == "direction_a"
    assert result["person_a_id"] == "direction_a"
    assert result["person_b_id"] == "direction_b"
    assert result["label_a_to_b"] == "coaches"
    assert result["label_b_to_a"] == "coached by"


def test_directional_title_uses_canonical_direction_from(isolated):
    _insert_person("source_a", "Source A")
    _insert_person("source_b", "Source B")
    relationship_id = _insert_general("source_a", "source_b", label_a_to_b="receives", label_b_to_a="provides")
    connection = db.get_connection()
    try:
        connection.execute(
            "UPDATE general_relationships SET direction_from = ? WHERE id = ?",
            ("source_b", relationship_id),
        )
        connection.commit()
    finally:
        connection.close()
    result = next(item for item in _results("provides") if item.get("relationship_id") == relationship_id)
    assert result["title"] == "Source B → Source A"


def test_symmetric_general_result_preserves_orientation(isolated):
    _insert_person("symmetric_a", "Symmetric A")
    _insert_person("symmetric_b", "Symmetric B")
    relationship_id = _insert_general(
        "symmetric_a",
        "symmetric_b",
        type_="trusted_peer",
        directionality="symmetric",
        label_a_to_b="trusted peer",
        label_b_to_a="trusted peer",
    )
    result = next(item for item in _results("trusted peer") if item.get("relationship_id") == relationship_id)
    assert result["title"] == "Symmetric A ↔ Symmetric B"
    assert result["direction_from"] is None


@pytest.mark.parametrize("query", ["maternal uncle", "ماموں"])
def test_family_search_matches_english_and_urdu(query, isolated):
    family = [item for item in _results(query) if item.get("relationship_kind") == "family"]
    assert {item["title"] for item in family} >= {"Arsalan Israr", "Sohaib Hussain"}
    assert all(item["perspective_id"] == "mohammad_yahya_hussain" for item in family)


def test_family_search_changes_with_current_perspective(isolated):
    default = _results("niece", "mohammad_yahya_hussain")
    mansoor = _results("niece", "mansoor_hussain")
    assert [item["result_id"] for item in default] != [item["result_id"] for item in mansoor]
    assert any(item["title"] == "Aresha Zubair" for item in mansoor)


def test_multipath_family_results_keep_distinct_structural_path_ids(isolated):
    matches = [
        item
        for item in _results("cousin")
        if item.get("relationship_kind") == "family" and item.get("target_person_id") == "ezan_asif"
    ]
    assert len(matches) >= 2
    assert len({item["path_id"] for item in matches}) == len(matches)
    assert all(item["result_id"].endswith(item["path_id"]) for item in matches)


def test_journal_search_returns_deterministic_snippet(isolated):
    path = Path(journals.read_journal("maham_mansoor")["path"])
    content = "# Journal\n\nBefore words. Unique Phase6 memory اردو 😀. After words.\n"
    path.write_text(content, encoding="utf-8")
    first = next(item for item in _results("phase6 memory") if item["category"] == "JOURNAL")
    second = next(item for item in _results("PHASE6 MEMORY") if item["category"] == "JOURNAL")
    assert first["result_id"] == "journal:maham_mansoor"
    assert first["match"] == second["match"]
    assert "Unique Phase6 memory اردو 😀" in first["match"]


def test_journal_search_supports_unicode_and_literal_characters(isolated):
    path = Path(journals.read_journal("maham_mansoor")["path"])
    path.write_text("literal 100%_safe O'Brien اردو 😀", encoding="utf-8")
    for query in ("%_", "O'Brien", "اردو", "😀"):
        assert any(item["result_id"] == "journal:maham_mansoor" for item in _results(query))


def test_missing_journal_is_not_created_by_search(isolated):
    path = Path(journals.read_journal("maham_mansoor")["path"])
    path.unlink()
    _results("not present anywhere")
    assert not path.exists()


def test_invalid_utf8_journal_is_skipped_without_breaking_search(isolated):
    path = Path(journals.read_journal("maham_mansoor")["path"])
    path.write_bytes(b"\xff\xfephase6")
    assert isinstance(_results("phase6"), list)
    assert all(item["result_id"] != "journal:maham_mansoor" for item in _results("phase6"))


def test_search_does_not_mutate_database_or_journals(isolated):
    database = isolated / "Database" / "Main" / "family.db"
    journal = Path(journals.read_journal("mohammad_yahya_hussain")["path"])
    before = (hashlib.sha256(database.read_bytes()).digest(), hashlib.sha256(journal.read_bytes()).digest())
    _results("cousin")
    _results("yahya")
    after = (hashlib.sha256(database.read_bytes()).digest(), hashlib.sha256(journal.read_bytes()).digest())
    assert after == before


def test_search_works_when_data_root_reports_read_only(isolated, monkeypatch):
    monkeypatch.setattr(DataRootManager, "is_read_only", classmethod(lambda cls, root=None: True))
    assert any(item["result_id"] == "person:muaaz" for item in _results("Maaz"))
    assert isinstance(_results("cousin"), list)


def test_large_journal_search_finds_tail_without_mutation(isolated):
    path = Path(journals.read_journal("maham_mansoor")["path"])
    content = "prefix " + ("ordinary journal text\n" * 20_000) + "rare tail phrase اردو 😀"
    path.write_text(content, encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).digest()
    result = next(item for item in _results("rare tail phrase") if item["result_id"] == "journal:maham_mansoor")
    assert "rare tail phrase اردو 😀" in result["match"]
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_journal_prose_is_not_copied_into_sqlite(isolated):
    marker = "phase6 journal only marker 51b8d9"
    path = Path(journals.read_journal("maham_mansoor")["path"])
    path.write_text(marker, encoding="utf-8")
    assert any(item["result_id"] == "journal:maham_mansoor" for item in _results(marker))
    database = isolated / "Database" / "Main" / "family.db"
    assert marker.encode("utf-8") not in database.read_bytes()


def test_limit_is_deterministic_and_capped(isolated):
    limited = search.search("cousin", perspective_id="mohammad_yahya_hussain", limit=3)["results"]
    assert len(limited) == 3
    assert limited == _results("cousin")[:3]
    assert len(search.search("cousin", perspective_id="mohammad_yahya_hussain", limit=10_000)["results"]) <= 100


@pytest.mark.parametrize("invalid_limit", [-1, 0, 101])
def test_api_rejects_invalid_limits(client, invalid_limit):
    response = client.get("/api/search", params={"q": "cousin", "limit": invalid_limit})
    assert response.status_code == 422


def test_approximately_one_hundred_people_remains_interactive(isolated):
    for number in range(100):
        _insert_person(f"synthetic_{number:03d}", f"Synthetic Person {number:03d}", 1000 + number)
    started = time.perf_counter()
    results = _results("Synthetic Person 099")
    elapsed = time.perf_counter() - started
    assert results[0]["result_id"] == "person:synthetic_099"
    assert elapsed < 2.0


def test_result_contract_covers_all_categories(isolated):
    _insert_person("contract_a", "Contract Person", aliases=("Contract Alias",))
    _insert_person("contract_b", "Contract Other")
    _insert_general("contract_a", "contract_b", notes="contract marker")
    connection = db.get_connection()
    try:
        connection.execute(
            "INSERT INTO groups (id, name, slug, kind, display_order) VALUES ('contract_group', 'Contract Group', 'contract_group', 'custom', 900)"
        )
        connection.execute(
            "INSERT INTO person_groups (person_id, group_id, is_primary) VALUES ('contract_a', 'contract_group', 1)"
        )
        connection.commit()
    finally:
        connection.close()
    journal = Path(journals.read_journal("maham_mansoor")["path"])
    journal.write_text("contract marker", encoding="utf-8")
    categories = {item["category"] for item in _results("contract")}
    assert categories == {"PERSON", "RELATIONSHIP", "GROUP", "JOURNAL"}
    assert all(item["result_id"] for item in _results("contract"))
