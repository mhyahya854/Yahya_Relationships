"""Hermes deterministic tool tests."""

import pytest

from app.backend.hermes import tools as hermes


def test_tool_catalog_is_stable():
    catalog = hermes.list_tools()
    names = [tool["name"] for tool in catalog]
    assert "get_relationship" in names
    assert "add_general_relationship" in names
    assert "append_journal" in names
    assert "create_backup" in names
    for tool in catalog:
        assert tool["name"] in hermes.HANDLERS
        assert "description" in tool
        assert "parameters" in tool


def test_get_relationship_tool_json():
    result = hermes.run_tool(
        "get_relationship",
        {
            "perspective": "mohammad_yahya_hussain",
            "target": "ezan_asif",
        },
    )
    assert result["ok"] is True
    labels = [
        item["label_en"] for item in result["primary"] + result["additional"]
    ]
    assert "maternal first cousin" in labels
    assert "paternal second cousin" in labels


def test_ambiguous_person_error():
    result = hermes.run_tool(
        "get_relationship",
        {"perspective": "a", "target": "b"},
    )
    assert result["ok"] is False
    assert result["error"]["code"] in ("PERSON_AMBIGUOUS", "NOT_FOUND")


def test_family_write_tool_validation_error():
    result = hermes.run_tool(
        "add_family_fact",
        {
            "fact_type": "parent_child",
            "parent": "mohammad_yahya_hussain",
            "child": "mohammad_yahya_hussain",
        },
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "SELF_PARENT"


def test_add_friend_and_journal_flow(isolated):
    created = hermes.run_tool("add_person", {"name": "Hermes Friend"})
    assert created["ok"] is True
    friend_id = created["person"]["id"]
    hermes.run_tool(
        "add_general_relationship",
        {
            "person_a": "mohammad_yahya_hussain",
            "person_b": friend_id,
            "type": "close_friend",
        },
    )
    appended = hermes.run_tool(
        "append_journal",
        {"person": friend_id, "text": "- Likes tea."},
    )
    assert appended["ok"] is True
    read = hermes.run_tool("read_journal", {"person": friend_id})
    assert read["ok"] is True
    assert "- Likes tea." in read["content"]
    relation = hermes.run_tool(
        "get_relationship",
        {"perspective": "mohammad_yahya_hussain", "target": friend_id},
    )
    assert relation["primary"][0]["label_en"] == "Close friend"


def test_hermes_structured_write_provenance(isolated):
    created = hermes.run_tool("add_person", {"name": "Provenance Person"})
    hermes.run_tool(
        "add_general_relationship",
        {
            "person_a": "mohammad_yahya_hussain",
            "person_b": created["person"]["id"],
            "type": "colleague",
        },
    )
    from app.backend import db

    connection = db.get_connection()
    try:
        row = connection.execute(
            """
            SELECT fs.note FROM fact_sources fs
            JOIN sources s ON s.id = fs.source_id
            WHERE fs.entity_type = 'people'
              AND fs.entity_key = ?
            ORDER BY fs.id DESC LIMIT 1
            """,
            (created["person"]["id"],),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    assert "user_via_hermes" in row["note"]
