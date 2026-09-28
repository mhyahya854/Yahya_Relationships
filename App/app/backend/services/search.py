"""Deterministic global search over canonical local data sources."""

from __future__ import annotations

import re
import unicodedata

from .. import db
from ..model import load_model, people_index
from . import errors, journals, relationship, state


def _normalize(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold().strip()


def _contains(value: object, query: str) -> bool:
    return bool(query and query in _normalize(value))


def _text_rank(value: object, query: str) -> int | None:
    normalized = _normalize(value)
    if normalized == query:
        return 0
    if normalized.startswith(query):
        return 1
    if query in normalized:
        return 2
    return None


def _person_rank(name: str, aliases: list[str], query: str) -> tuple[int, str | None] | None:
    canonical = _normalize(name)
    normalized_aliases = [(_normalize(alias), alias) for alias in aliases]
    if canonical == query:
        return 0, None
    exact_alias = next((alias for normalized, alias in normalized_aliases if normalized == query), None)
    if exact_alias is not None:
        return 1, exact_alias
    if canonical.startswith(query):
        return 2, None
    prefix_alias = next((alias for normalized, alias in normalized_aliases if normalized.startswith(query)), None)
    if prefix_alias is not None:
        return 3, prefix_alias
    if query in canonical:
        return 4, None
    substring_alias = next((alias for normalized, alias in normalized_aliases if query in normalized), None)
    if substring_alias is not None:
        return 5, substring_alias
    return None


def _snippet(content: str, normalized_query: str, radius: int = 90) -> str:
    display = re.sub(r"\s+", " ", content).strip()
    normalized = _normalize(display)
    index = normalized.find(normalized_query)
    if index < 0:
        return display[: radius * 2] + ("…" if len(display) > radius * 2 else "")
    start = max(0, index - radius)
    end = min(len(display), index + len(normalized_query) + radius)
    return ("…" if start else "") + display[start:end] + ("…" if end < len(display) else "")


def _family_results(normalized_query: str, perspective_id: str) -> list[dict]:
    if len(normalized_query) < 2:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    for summary in relationship.list_relationships_from(perspective_id, domain="family"):
        entries = summary["primary"] + summary["additional"]
        if not any(
            _contains(entry.get("label_en"), normalized_query)
            or _contains(entry.get("label_ur"), normalized_query)
            for entry in entries
        ):
            continue
        target_id = summary["target"]["id"]
        detailed = relationship.get_relationship(perspective_id, target_id)
        for entry in detailed["primary"] + detailed["additional"]:
            if entry.get("domain") != "family":
                continue
            if not (
                _contains(entry.get("label_en"), normalized_query)
                or _contains(entry.get("label_ur"), normalized_query)
            ):
                continue
            path_ids = entry.get("path_ids") or [
                entry.get("id") or entry.get("semantic_id") or entry["relationship_type"]
            ]
            for path_id in path_ids:
                result_id = f"family:{perspective_id}:{target_id}:{path_id}"
                if result_id in seen:
                    continue
                seen.add(result_id)
                label_en = entry.get("label_en") or ""
                label_ur = entry.get("label_ur")
                match_rank = min(
                    rank
                    for rank in (
                        _text_rank(label_en, normalized_query),
                        _text_rank(label_ur, normalized_query),
                    )
                    if rank is not None
                )
                results.append(
                    {
                        "result_id": result_id,
                        "category": "RELATIONSHIP",
                        "relationship_kind": "family",
                        "person_id": target_id,
                        "target_person_id": target_id,
                        "perspective_id": perspective_id,
                        "path_id": str(path_id),
                        "title": detailed["target"]["name"],
                        "subtitle": f"Family relationship from {detailed['perspective']['name']}",
                        "match": label_en + (f" / {label_ur}" if label_ur else ""),
                        "label_en": label_en,
                        "label_ur": label_ur,
                        "derived": bool(entry.get("derived")),
                        "semantic_id": entry.get("semantic_id"),
                        "_match_rank": match_rank,
                    }
                )
    return results


def search(
    query: str,
    *,
    perspective_id: str | None = None,
    limit: int = 40,
) -> dict:
    original_query = str(query or "")
    normalized_query = _normalize(original_query)
    if perspective_id is None:
        perspective_id = state.get_state()["perspective_person_id"]

    model = load_model()
    index = people_index(model)
    perspective = index.get(perspective_id)
    if perspective is None:
        raise errors.NotFoundError(f"Unknown person id: {perspective_id}")

    response = {
        "query": original_query,
        "normalized_query": normalized_query,
        "perspective": {"id": perspective_id, "name": perspective["name"]},
        "results": [],
    }
    if not normalized_query:
        return response

    connection = db.get_connection()
    try:
        people_rows = connection.execute(
            "SELECT id, name, display_order FROM people ORDER BY display_order, name, id"
        ).fetchall()
        aliases_by_person: dict[str, list[str]] = {row["id"]: [] for row in people_rows}
        for row in connection.execute(
            "SELECT person_id, alias FROM aliases ORDER BY person_id, display_order, alias"
        ):
            aliases_by_person.setdefault(row["person_id"], []).append(row["alias"])

        results: list[dict] = []
        for row in people_rows:
            rank = _person_rank(row["name"], aliases_by_person.get(row["id"], []), normalized_query)
            if rank is None:
                continue
            match_rank, matched_alias = rank
            results.append(
                {
                    "result_id": f"person:{row['id']}",
                    "category": "PERSON",
                    "person_id": row["id"],
                    "title": row["name"],
                    "subtitle": "Person",
                    "match": f"Alias: {matched_alias}" if matched_alias else "Canonical name",
                    "matched_alias": matched_alias,
                    "match_kind": (
                        "exact_name",
                        "exact_alias",
                        "name_prefix",
                        "alias_prefix",
                        "name_substring",
                        "alias_substring",
                    )[match_rank],
                    "_sort": (0, match_rank, _normalize(row["name"]), row["id"]),
                }
            )

        for row in connection.execute(
            "SELECT id, name, slug, kind, display_order FROM groups ORDER BY display_order, name, id"
        ):
            name = _normalize(row["name"])
            slug = _normalize(row["slug"])
            if normalized_query not in name and normalized_query not in slug:
                continue
            members = [
                member["person_id"]
                for member in connection.execute(
                    """
                    SELECT pg.person_id
                    FROM person_groups pg JOIN people p ON p.id = pg.person_id
                    WHERE pg.group_id = ?
                    ORDER BY p.display_order, p.name, p.id
                    """,
                    (row["id"],),
                )
            ]
            rank = min(
                item
                for item in (
                    _text_rank(row["name"], normalized_query),
                    _text_rank(row["slug"], normalized_query),
                )
                if item is not None
            )
            results.append(
                {
                    "result_id": f"group:{row['id']}",
                    "category": "GROUP",
                    "person_id": None,
                    "group_id": row["id"],
                    "member_ids": members,
                    "member_count": len(members),
                    "title": row["name"],
                    "subtitle": f"Group · {len(members)} member{'s' if len(members) != 1 else ''}",
                    "match": row["name"],
                    "_sort": (1, rank, 2, name, row["id"]),
                }
            )

        names = {row["id"]: row["name"] for row in people_rows}
        for row in connection.execute("SELECT * FROM general_relationships ORDER BY id"):
            fields = (
                ("type", row["type"]),
                ("label_a_to_b", row["label_a_to_b"]),
                ("label_b_to_a", row["label_b_to_a"]),
                ("notes", row["notes"]),
            )
            matched_fields = [field for field, value in fields if _contains(value, normalized_query)]
            if not matched_fields:
                continue
            match_rank = min(
                rank
                for _, value in fields
                if (rank := _text_rank(value, normalized_query)) is not None
            )
            a_id, b_id = row["person_a"], row["person_b"]
            a_name, b_name = names.get(a_id, a_id), names.get(b_id, b_id)
            if row["directionality"] == "directional":
                source_is_b = row["direction_from"] == b_id
                source_name, target_name = (b_name, a_name) if source_is_b else (a_name, b_name)
                title = f"{source_name} → {target_name}"
            else:
                title = f"{a_name} ↔ {b_name}"
            results.append(
                {
                    "result_id": f"general:{row['id']}",
                    "category": "RELATIONSHIP",
                    "relationship_kind": "general",
                    "relationship_id": row["id"],
                    "person_id": None,
                    "person_a_id": a_id,
                    "person_a_name": a_name,
                    "person_b_id": b_id,
                    "person_b_name": b_name,
                    "directionality": row["directionality"],
                    "direction_from": row["direction_from"],
                    "label_a_to_b": row["label_a_to_b"] or row["type"],
                    "label_b_to_a": row["label_b_to_a"] or row["type"],
                    "notes": row["notes"],
                    "title": title,
                    "subtitle": f"General relationship · {row['type']}",
                    "match": " · ".join(
                        str(value) for field, value in fields if field in matched_fields and value
                    ),
                    "matched_fields": matched_fields,
                    "_sort": (1, match_rank, 0, _normalize(title), f"general:{row['id']}"),
                }
            )
    finally:
        connection.close()

    for item in _family_results(normalized_query, perspective_id):
        item["_sort"] = (1, item.pop("_match_rank"), 1, _normalize(item["title"]), item["result_id"])
        results.append(item)

    for summary in journals.journal_summaries():
        if not _contains(summary["content"], normalized_query):
            continue
        results.append(
            {
                "result_id": f"journal:{summary['person_id']}",
                "category": "JOURNAL",
                "person_id": summary["person_id"],
                "title": summary["name"],
                "subtitle": "Journal",
                "match": _snippet(summary["content"], normalized_query),
                "matched_field": "content",
                "_sort": (2, _normalize(summary["name"]), summary["person_id"]),
            }
        )

    results.sort(key=lambda item: item["_sort"])
    maximum = max(1, min(int(limit), 100))
    for item in results:
        item.pop("_sort", None)
    response["results"] = results[:maximum]
    return response
