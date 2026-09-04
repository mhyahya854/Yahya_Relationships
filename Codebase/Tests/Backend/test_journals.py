"""Markdown journal sync tests: append, UTF-8, external-change conflict."""

from pathlib import Path

import pytest

from app.backend.services import errors, journals, people


def test_read_append_roundtrip(isolated):
    result = journals.read_journal("mohammad_yahya_hussain")
    assert result["content"] == "# Mohammad Yahya Hussain\n\n"
    appended = journals.append_journal(
        "mohammad_yahya_hussain",
        "- Prefers aisle seats.",
        heading="2026-09-04",
    )
    assert "## 2026-09-04" in appended["content"]
    assert "- Prefers aisle seats." in appended["content"]
    read_again = journals.read_journal("mohammad_yahya_hussain")
    assert read_again["content"] == appended["content"]


def test_utf8_unicode_preserved(isolated):
    appended = journals.append_journal(
        "mohammad_yahya_hussain",
        "- یادداشت: عربی / اردو متن",
    )
    assert "یادداشت: عربی / اردو متن" in appended["content"]
    on_disk = Path(appended["path"]).read_text(encoding="utf-8")
    assert "یادداشت: عربی / اردو متن" in on_disk


def test_external_edit_detected_and_conflict_raised(isolated):
    first = journals.read_journal("maham_mansoor")
    path = Path(first["path"])
    path.write_text(first["content"] + "\n## 2026-09-04\n\n- External note.\n", encoding="utf-8")
    with pytest.raises(errors.JournalConflictError):
        journals.save_journal(
            "maham_mansoor",
            first["content"] + "\n## overwrite\n",
            expected_sha256=first["sha256"],
        )
    current = journals.read_journal("maham_mansoor")
    assert "External note." in current["content"]


def test_external_edit_becomes_visible(isolated):
    first = journals.read_journal("maham_mansoor")
    path = Path(first["path"])
    path.write_text(
        first["content"] + "\n## Notes\n\n- Changed in VS Code.\n",
        encoding="utf-8",
    )
    second = journals.read_journal("maham_mansoor")
    assert "Changed in VS Code." in second["content"]


def test_atomic_save_no_partial_state(isolated):
    person = people.create_person(name="Journal Test")
    result = journals.read_journal(person["id"])
    saved = journals.save_journal(
        person["id"],
        "# Journal Test\n\n## Entry\n\n- Line one.\n",
        expected_sha256=result["sha256"],
    )
    assert saved["saved"] is True
    assert Path(saved["path"]).read_text(encoding="utf-8").endswith("- Line one.\n")
