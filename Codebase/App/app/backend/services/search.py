"""Deterministic global search over people, aliases, groups, relationship
labels and journal prose. No AI is used anywhere in search."""

import re

from .. import db
from . import journals, relationship


def _escape_like(value: str) -> str:
    return value.replace("%", "\\%").replace("_", "\\_")


def search(query: str, *, limit: int = 40) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": query, "results": []}
    lowered = query.lower()
    like = f"%{_escape_like(query)}%"
    connection = db.get_connection()
    results = []
    try:
        people_rows = connection.execute(
            """
            SELECT p.id, p.name,
                   COALESCE(p.name LIKE ?, 0) AS name_boost
            FROM people p
            WHERE p.name LIKE ? ESCAPE '\\'
               OR p.id IN (
                 SELECT person_id FROM aliases
                 WHERE alias LIKE ? ESCAPE '\\'
               )
            ORDER BY name_boost DESC, p.display_order
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        for row in people_rows:
            results.append(
                {
                    "category": "PERSON",
                    "person_id": row["id"],
                    "title": row["name"],
                    "subtitle": "Person",
                    "match": row["name"],
                }
            )

        group_rows = connection.execute(
            """
            SELECT id, name FROM groups
            WHERE name LIKE ? ESCAPE '\\' OR slug LIKE ? ESCAPE '\\'
            ORDER BY display_order LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        for row in group_rows:
            results.append(
                {
                    "category": "GROUP",
                    "person_id": None,
                    "title": row["name"],
                    "subtitle": "Group",
                    "match": row["name"],
                }
            )

        relationship_rows = connection.execute(
            """
            SELECT id, person_a, person_b, type, label_a_to_b, label_b_to_a
            FROM general_relationships
            WHERE type LIKE ? ESCAPE '\\'
               OR COALESCE(label_a_to_b, '') LIKE ? ESCAPE '\\'
               OR COALESCE(label_b_to_a, '') LIKE ? ESCAPE '\\'
               OR COALESCE(notes, '') LIKE ? ESCAPE '\\'
            ORDER BY id LIMIT ?
            """,
            (like, like, like, like, limit),
        ).fetchall()
        name_by_id = {
            row["id"]: row["name"]
            for row in connection.execute("SELECT id, name FROM people")
        }
        for row in relationship_rows:
            a_name = name_by_id.get(row["person_a"], row["person_a"])
            b_name = name_by_id.get(row["person_b"], row["person_b"])
            label = row["label_a_to_b"] or row["type"]
            results.append(
                {
                    "category": "RELATIONSHIP",
                    "person_id": None,
                    "relationship_id": row["id"],
                    "title": f"{a_name} ↔ {b_name}",
                    "subtitle": "Relationship",
                    "match": label,
                    "target_person_id": row["person_b"],
                }
            )
    finally:
        connection.close()

    for summary in journals.journal_summaries():
        if lowered in summary["content"].lower():
            results.append(
                {
                    "category": "JOURNAL",
                    "person_id": summary["person_id"],
                    "title": summary["name"],
                    "subtitle": "Journal",
                    "match": _snippet(summary["content"], query),
                }
            )

    # Family relationship labels are computed by the canonical engine from
    # the default perspective and matched in English and Urdu.
    family_matches = _family_relationship_matches(lowered)
    results.extend(family_matches)

    # Deterministic ordering: PERSON exact-name matches first, then categories
    # in a stable order, then title.
    order = {"PERSON": 0, "RELATIONSHIP": 1, "GROUP": 2, "JOURNAL": 3}
    results.sort(
        key=lambda item: (
            not (item["category"] == "PERSON" and item["title"].lower() == lowered),
            order.get(item["category"], 9),
            item["title"].lower(),
            item.get("match", "").lower(),
        )
    )
    return {"query": query, "results": results[: int(limit)]}


def _family_relationship_matches(lowered: str) -> list[dict]:
    if not lowered or len(lowered) < 2:
        return []
    matches = []
    try:
        model = None
        from ..model import load_model

        model = load_model()
        focus_id = model["metadata"].get("focus_person")
        rows = relationship.list_relationships_from(focus_id, domain="family")
    except Exception:
        return matches
    for row in rows:
        for entry in row["primary"] + row["additional"]:
            haystack = " ".join(
                part
                for part in (entry.get("label_en") or "", entry.get("label_ur") or "")
                if part
            ).lower()
            if lowered in haystack:
                matches.append(
                    {
                        "category": "RELATIONSHIP",
                        "person_id": row["target"]["id"],
                        "title": row["target"]["name"],
                        "subtitle": "Family relationship",
                        "match": entry.get("label_en", "")
                        + (
                            f" / {entry['label_ur']}"
                            if entry.get("label_ur")
                            else ""
                        ),
                    }
                )
                break
    return matches


def _snippet(content: str, query: str, radius: int = 80) -> str:
    lowered = content.lower()
    index = lowered.find(query.lower())
    if index < 0:
        return content[: radius * 2].replace("\n", " ")
    start = max(0, index - radius)
    end = min(len(content), index + len(query) + radius)
    snippet = content[start:end].replace("\n", " ")
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet
