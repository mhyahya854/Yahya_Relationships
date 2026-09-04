"""Deterministic JSON tools for Hermes.

The AI only decides intent; application code performs the operation. Every
tool returns stable output or a machine-readable error with an explicit
code. No tool exposes SQL, repository paths, or genealogy internals.
"""

from __future__ import annotations

import sqlite3

from ..services import (
    backups,
    errors,
    family,
    general,
    journals,
    people,
    relationship,
    search,
    state,
)
from ..domain.relationships import graph as graph_service
from ..domain.relationships import path_service


def _resolve_people_by_query(query: str, limit: int = 8) -> list[dict]:
    rows = people.list_people(query=query)
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "aliases": row["aliases"],
            "groups": [group["name"] for group in row["groups"]],
        }
        for row in rows[:limit]
    ]


def resolve_person(query: str) -> dict:
    """Resolve a person id or a unique name/alias to one canonical person."""
    query = (query or "").strip()
    if not query:
        raise errors.ValidationError("A person name or id is required.")
    exact = None
    for row in people.list_people(query=""):
        if row["id"].lower() == query.lower() or row["name"].lower() == query.lower():
            exact = row
            break
        if any(alias.lower() == query.lower() for alias in row["aliases"]):
            exact = row
            break
    if exact is not None:
        return {"id": exact["id"], "name": exact["name"], "exact": True}
    matches = _resolve_people_by_query(query, limit=8)
    if not matches:
        raise errors.NotFoundError(f"No person matches {query!r}.")
    if len(matches) == 1:
        match = matches[0]
        return {"id": match["id"], "name": match["name"], "exact": False}
    raise errors.AmbiguousPersonError(
        f"Multiple people match {query!r}.",
        details={"matches": matches},
    )


def _person_id(query: str) -> str:
    return resolve_person(query)["id"]


def _wrap(func):
    def wrapper(*args, **kwargs):
        try:
            return {"ok": True, **func(*args, **kwargs)}
        except errors.AppError as exc:
            return exc.as_dict()
        except Exception as exc:  # pragma: no cover - safety net
            return {
                "ok": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                },
            }

    return wrapper


def _person_brief(person_id: str) -> dict:
    row = people.get_person(person_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "aliases": row["aliases"],
        "groups": [group["name"] for group in row["groups"]],
    }


def _serialize_relationship(result: dict) -> dict:
    return {
        "perspective": result["perspective"],
        "target": result["target"],
        "primary": result["primary"],
        "additional": result["additional"],
    }


@_wrap
def tool_search_people(query: str, limit: int = 8):
    matches = _resolve_people_by_query(query, limit=limit)
    return {"query": query, "matches": matches}


@_wrap
def tool_list_people(limit: int = 1000):
    return {
        "people": [
            _person_brief(row["id"]) for row in people.list_people()[: int(limit)]
        ]
    }


@_wrap
def tool_get_person(person: str):
    person_id = _person_id(person)
    return {"person": _person_brief(person_id)}


@_wrap
def tool_get_relationship(perspective: str, target: str):
    perspective_id = _person_id(perspective)
    target_id = _person_id(target)
    result = relationship.get_relationship(perspective_id, target_id)
    return _serialize_relationship(result)


@_wrap
def tool_compare_people(person_a: str, person_b: str):
    a = _person_id(person_a)
    b = _person_id(person_b)
    result = relationship.compare_people(a, b)
    return {
        "person_a": result["a"],
        "person_b": result["b"],
        "a_to_b": _serialize_relationship(result["a_to_b"]),
        "b_to_a": _serialize_relationship(result["b_to_a"]),
    }


@_wrap
def tool_get_relationship_paths(
    perspective: str,
    target: str,
    max_depth: int | None = None,
    max_paths: int | None = None,
):
    perspective_id = _person_id(perspective)
    target_id = _person_id(target)
    try:
        depth = int(max_depth) if max_depth is not None else None
        count = int(max_paths) if max_paths is not None else None
    except (TypeError, ValueError):
        raise errors.ValidationError(
            "max_depth and max_paths must be integers."
        ) from None
    result = path_service.get_relationship_paths(
        perspective_id,
        target_id,
        max_depth=depth if depth is not None else 10,
        max_paths=count if count is not None else 10,
    )
    return {
        "perspective": result["perspective"],
        "target": result["target"],
        "paths": result["paths"],
        "truncated": result["truncated"],
    }


@_wrap
def tool_get_neighbors(person: str, filters: list[str] | None = None):
    person_id = _person_id(person)
    return graph_service.get_graph_neighbors(
        person_id,
        perspective_id=person_id,
        filters=filters,
    )


@_wrap
def tool_list_relationships_from(
    person: str, domain: str | None = None, direct_only: bool = False
):
    person_id = _person_id(person)
    rows = relationship.list_relationships_from(
        person_id, domain=domain, direct_only=bool(direct_only)
    )
    return {
        "perspective": _person_brief(person_id),
        "relationships": [
            {
                "target": {"id": row["target"]["id"], "name": row["target"]["name"]},
                "primary": row["primary"],
                "additional": row["additional"],
            }
            for row in rows
        ],
    }


@_wrap
def tool_set_perspective(person: str):
    person_id = _person_id(person)
    current = state.set_perspective(person_id)
    return {
        "perspective_person_id": current["perspective_person_id"],
        "default_perspective_person_id": current["default_perspective_person_id"],
    }


@_wrap
def tool_add_person(
    name: str,
    aliases: list[str] | None = None,
    birth_year: int | None = None,
    gender: str | None = None,
    group: str | None = None,
    notes: str | None = None,
):
    group_id = None
    if group:
        group_row = None
        for candidate in _all_groups():
            if candidate["id"] == group or candidate["name"].lower() == group.lower():
                group_row = candidate
                break
        if group_row is None:
            group_row = people_create_group(group)
        group_id = group_row["id"]
    created = people.create_person(
        name=name,
        aliases=aliases,
        birth_year=birth_year,
        gender=gender,
        note_en=notes,
        group_id=group_id,
        origin="user_via_hermes",
    )
    return {"person": _person_brief(created["id"])}


def _all_groups():
    from ..services import groups

    return groups.list_groups()


def people_create_group(name: str):
    from ..services import groups

    return groups.create_group(name)


@_wrap
def tool_update_person(person: str, name: str | None = None, **changes):
    person_id = _person_id(person)
    notes = changes.pop("notes", None)
    updated = people.update_person(
        person_id,
        name=name,
        note_en=notes,
        origin="user_via_hermes",
    )
    return {"person": _person_brief(updated["id"])}


@_wrap
def tool_add_family_fact(fact_type: str, **fact):
    if fact_type == "parent_child":
        parent = _person_id(fact["parent"])
        child = _person_id(fact["child"])
        return family.add_parent_child(
            parent_id=parent,
            child_id=child,
            role=fact.get("role", "parent"),
            kind=fact.get("kind", "biological"),
            origin="user_via_hermes",
        )
    if fact_type == "marriage":
        person_a = _person_id(fact["person_a"])
        person_b = _person_id(fact["person_b"])
        return family.add_marriage(
            person_a=person_a,
            person_b=person_b,
            status=fact.get("status", "married"),
            year=fact.get("year"),
            children_status=fact.get("children_status"),
            origin="user_via_hermes",
        )
    if fact_type == "sibling_group":
        return family.add_sibling_group(
            member_ids=[_person_id(member) for member in fact["members"]],
            type_=fact.get("type"),
            ordered=bool(fact.get("ordered", False)),
            origin="user_via_hermes",
        )
    raise errors.ValidationError(
        "fact_type must be parent_child, marriage or sibling_group."
    )


@_wrap
def tool_add_general_relationship(
    person_a: str,
    person_b: str,
    type: str,
    directionality: str = "symmetric",
    label_a_to_b: str | None = None,
    label_b_to_a: str | None = None,
    notes: str | None = None,
):
    a = _person_id(person_a)
    b = _person_id(person_b)
    row = general.add_general_relationship(
        person_a=a,
        person_b=b,
        type=type,
        directionality=directionality,
        label_a_to_b=label_a_to_b,
        label_b_to_a=label_b_to_a,
        notes=notes,
    )
    return {
        "relationship": {
            "id": row["id"],
            "person_a": row["person_a"],
            "person_b": row["person_b"],
            "type": row["type"],
            "directionality": row["directionality"],
            "label_a_to_b": row["label_a_to_b"],
            "label_b_to_a": row["label_b_to_a"],
        }
    }


@_wrap
def tool_remove_general_relationship(relationship_id: int):
    return general.delete_general_relationship(int(relationship_id))


@_wrap
def tool_read_journal(person: str):
    person_id = _person_id(person)
    result = journals.read_journal(person_id)
    return {
        "person_id": result["person_id"],
        "content": result["content"],
        "modified_ns": result["modified_ns"],
    }


@_wrap
def tool_append_journal(person: str, text: str, heading: str | None = None):
    person_id = _person_id(person)
    return journals.append_journal(
        person_id, text, heading=heading, origin="user_via_hermes"
    )


@_wrap
def tool_search_journals(query: str):
    return search.search(query)["results"]


@_wrap
def tool_create_backup(label: str | None = None):
    return backups.create_backup(label=label)


@_wrap
def tool_list_backups():
    return {"backups": backups.list_backups()}


@_wrap
def tool_resolve_person(query: str):
    resolved = resolve_person(query)
    return {"matches": [resolved]} if not resolved.get("exact") else {"matches": [resolved]}


TOOL_DEFINITIONS = [
    {
        "name": "search_people",
        "description": "Search people by name or alias and return candidate ids.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name or alias."},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_person",
        "description": "Get one person by exact id, name, or alias.",
        "parameters": {
            "type": "object",
            "properties": {
                "person": {"type": "string", "description": "Person id, name, or alias."}
            },
            "required": ["person"],
        },
    },
    {
        "name": "list_people",
        "description": "List every person with stable id and display name.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 1000}},
        },
    },
    {
        "name": "get_relationship",
        "description": "How is the target person related from the perspective person's side?",
        "parameters": {
            "type": "object",
            "properties": {
                "perspective": {"type": "string", "description": "Person id, name or alias."},
                "target": {"type": "string", "description": "Person id, name or alias."},
            },
            "required": ["perspective", "target"],
        },
    },
    {
        "name": "compare_people",
        "description": "Compare two people in both directions.",
        "parameters": {
            "type": "object",
            "properties": {
                "person_a": {"type": "string"},
                "person_b": {"type": "string"},
            },
            "required": ["person_a", "person_b"],
        },
    },
    {
        "name": "get_relationship_paths",
        "description": "Return the exact graph paths that explain a relationship.",
        "parameters": {
            "type": "object",
            "properties": {
                "perspective": {"type": "string", "description": "Person id, name or alias."},
                "target": {"type": "string", "description": "Person id, name or alias."},
                "max_depth": {"type": "integer", "description": "1-30 (default 10)."},
                "max_paths": {"type": "integer", "description": "1-50 (default 10)."},
            },
            "required": ["perspective", "target"],
        },
    },
    {
        "name": "get_neighbors",
        "description": "Return a person's graph neighbours for progressive expansion.",
        "parameters": {
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "parents",
                            "children",
                            "siblings",
                            "spouses",
                            "general",
                            "all",
                        ],
                    },
                    "description": "Categories to expand; defaults to all direct.",
                },
            },
            "required": ["person"],
        },
    },
    {
        "name": "list_relationships_from",
        "description": "Every relationship from one person's perspective.",
        "parameters": {
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "domain": {"type": "string", "enum": ["family", "general"], "default": None},
                "direct_only": {"type": "boolean", "default": False},
            },
            "required": ["person"],
        },
    },
    {
        "name": "set_perspective",
        "description": "Make a person the current UI perspective.",
        "parameters": {
            "type": "object",
            "properties": {"person": {"type": "string"}},
            "required": ["person"],
        },
    },
    {
        "name": "add_person",
        "description": "Add one new person.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "birth_year": {"type": "integer"},
                "gender": {"type": "string", "enum": ["male", "female", "unknown"]},
                "group": {"type": "string", "description": "Existing group name/id or a new group name."},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_person",
        "description": "Update one person's display name or notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "name": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["person"],
        },
    },
    {
        "name": "add_family_fact",
        "description": "Record an objective family fact. fact_type is parent_child, marriage, or sibling_group.",
        "parameters": {
            "type": "object",
            "properties": {
                "fact_type": {"type": "string", "enum": ["parent_child", "marriage", "sibling_group"]},
                "parent": {"type": "string"},
                "child": {"type": "string"},
                "role": {"type": "string", "enum": ["mother", "father", "parent", "unknown"]},
                "kind": {
                    "type": "string",
                    "enum": ["biological", "adopted", "step", "foster", "guardian", "unknown", "unspecified"],
                },
                "person_a": {"type": "string"},
                "person_b": {"type": "string"},
                "status": {"type": "string", "enum": ["married", "divorced", "widowed", "unknown"]},
                "year": {"type": "integer"},
                "members": {"type": "array", "items": {"type": "string"}},
                "type": {"type": "string", "enum": ["full"]},
                "ordered": {"type": "boolean"},
            },
            "required": ["fact_type"],
        },
    },
    {
        "name": "add_general_relationship",
        "description": "Record a friend/colleague/custom relationship between two people.",
        "parameters": {
            "type": "object",
            "properties": {
                "person_a": {"type": "string"},
                "person_b": {"type": "string"},
                "type": {
                    "type": "string",
                    "description": "close_friend, friend, best_friend, colleague, former_colleague, mentor, mentee, neighbour, acquaintance, or custom.",
                },
                "directionality": {"type": "string", "enum": ["symmetric", "directional"], "default": "symmetric"},
                "label_a_to_b": {"type": "string"},
                "label_b_to_a": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["person_a", "person_b", "type"],
        },
    },
    {
        "name": "remove_general_relationship",
        "description": "Delete a general relationship by its numeric id.",
        "parameters": {
            "type": "object",
            "properties": {"relationship_id": {"type": "integer"}},
            "required": ["relationship_id"],
        },
    },
    {
        "name": "read_journal",
        "description": "Read one person's Markdown journal.",
        "parameters": {
            "type": "object",
            "properties": {"person": {"type": "string"}},
            "required": ["person"],
        },
    },
    {
        "name": "append_journal",
        "description": "Append a dated entry to one person's journal.",
        "parameters": {
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "text": {"type": "string"},
                "heading": {"type": "string"},
            },
            "required": ["person", "text"],
        },
    },
    {
        "name": "search_journals",
        "description": "Full-text search across all journals.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "create_backup",
        "description": "Create a timestamped local backup.",
        "parameters": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
        },
    },
    {
        "name": "list_backups",
        "description": "List existing local backups.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "resolve_person",
        "description": "Resolve a name or alias to exactly one person id when unambiguous.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]

HANDLERS = {
    "search_people": tool_search_people,
    "get_person": tool_get_person,
    "list_people": tool_list_people,
    "get_relationship": tool_get_relationship,
    "compare_people": tool_compare_people,
    "get_relationship_paths": tool_get_relationship_paths,
    "get_neighbors": tool_get_neighbors,
    "list_relationships_from": tool_list_relationships_from,
    "set_perspective": tool_set_perspective,
    "add_person": tool_add_person,
    "update_person": tool_update_person,
    "add_family_fact": tool_add_family_fact,
    "add_general_relationship": tool_add_general_relationship,
    "remove_general_relationship": tool_remove_general_relationship,
    "read_journal": tool_read_journal,
    "append_journal": tool_append_journal,
    "search_journals": tool_search_journals,
    "create_backup": tool_create_backup,
    "list_backups": tool_list_backups,
    "resolve_person": tool_resolve_person,
}


def list_tools() -> list[dict]:
    return TOOL_DEFINITIONS


def run_tool(name: str, arguments: dict) -> dict:
    if name not in HANDLERS:
        return {
            "ok": False,
            "error": {
                "code": "UNKNOWN_TOOL",
                "message": f"Unknown Hermes tool: {name}",
            },
        }
    handler = HANDLERS[name]
    return handler(**(arguments or {}))
