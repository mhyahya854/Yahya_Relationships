"""FastAPI local backend for People Relationships.

The server binds to 127.0.0.1 by default, keeps CORS restricted to the local
frontend origins, and exposes domain operations rather than raw tables.
"""

from __future__ import annotations

import copy
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from .. import config, db  # noqa: E402
from ..hermes import tools as hermes_tools  # noqa: E402
from ..model import (  # noqa: E402
    family_snapshot,
    load_model,
    run_family_audits,
    validate_model,
)
from ..domain.mutations import (  # noqa: E402
    history as mutation_history,
    preview as mutation_preview,
)
from ..domain.relationships import (  # noqa: E402
    graph as graph_service,
    path_service,
)
from ..services import (  # noqa: E402
    backups,
    errors,
    family,
    general,
    groups,
    journals,
    people,
    relationship,
    search,
    state,
)

from ..api.routes import backups as backups_router, data_root as data_root_router
from ..data_root.errors import DataRootError

@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_root_dirs()
    db.migrate()
    yield


app = FastAPI(
    title="People Relationships",
    version=config.APP_VERSION,
    description="Local-first personal relationship brain.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(errors.AppError)
async def app_error_handler(request: Request, exc: errors.AppError):
    return JSONResponse(status_code=exc.http_status, content=exc.as_dict())


@app.exception_handler(DataRootError)
async def data_root_error_handler(request: Request, exc: DataRootError):
    return JSONResponse(status_code=400, content=exc.to_dict())


app.include_router(data_root_router.router)
app.include_router(backups_router.router)


# ---------------------------------------------------------------------------
# App/health/state
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    connection = db.get_connection()
    try:
        info = db.schema_info(connection)
        person_count = connection.execute(
            "SELECT COUNT(*) AS count FROM people"
        ).fetchone()["count"]
    finally:
        connection.close()
    return {
        "ok": True,
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "schema_version": info["schema_version"],
        "people": person_count,
        "data_root": str(config.ROOT),
    }


@app.get("/api/app/info")
def app_info() -> dict:
    model = load_model()
    return {
        "ok": True,
        "title": model["metadata"].get("title", config.APP_NAME),
        "focus_person_id": model["metadata"].get("focus_person"),
        "focus_person_name": next(
            (p["name"] for p in model["people"] if p["id"] == model["metadata"].get("focus_person")),
            None,
        ),
        "revision": model["metadata"].get("revision"),
        "updated": model["metadata"].get("updated"),
        "root": str(config.ROOT),
        "version": config.APP_VERSION,
        "schema_version": config.APP_SCHEMA_VERSION,
    }


@app.get("/api/state")
def get_state() -> dict:
    return state.get_state()


class PerspectivePut(BaseModel):
    perspective_person_id: str


@app.put("/api/state")
def put_state(payload: PerspectivePut) -> dict:
    people.get_person(payload.perspective_person_id)
    return state.set_perspective(payload.perspective_person_id)


@app.post("/api/state/reset")
def reset_state() -> dict:
    return state.reset_perspective()


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------


class PersonCreate(BaseModel):
    name: str
    aliases: list[str] | None = None
    birth_year: int | None = Field(default=None, ge=1800, le=2100)
    gender: str | None = None
    marital_status: str | None = None
    branch: str | None = None
    note_en: str | None = None
    note_ur: str | None = None
    group_id: str | None = None


class PersonUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    birth_year: int | None = Field(default=None, ge=1800, le=2100)
    clear_birth_year: bool = False
    gender: str | None = None
    clear_gender: bool = False
    marital_status: str | None = None
    clear_marital_status: bool = False
    branch: str | None = None
    note_en: str | None = None
    clear_note_en: bool = False
    note_ur: str | None = None
    clear_note_ur: bool = False


@app.get("/api/people")
def api_list_people(query: str | None = None, group_id: str | None = None) -> dict:
    return {"ok": True, "people": people.list_people(query=query, group_id=group_id)}


@app.post("/api/people")
def api_create_person(payload: PersonCreate) -> dict:
    created = people.create_person(
        name=payload.name,
        aliases=payload.aliases,
        birth_year=payload.birth_year,
        gender=payload.gender,
        marital_status=payload.marital_status,
        branch=payload.branch,
        note_en=payload.note_en,
        note_ur=payload.note_ur,
        group_id=payload.group_id,
        origin="user",
    )
    return {"ok": True, "person": created}


@app.get("/api/people/{person_id}")
def api_get_person(person_id: str) -> dict:
    return {"ok": True, "person": people.get_person(person_id)}


@app.patch("/api/people/{person_id}")
def api_update_person(person_id: str, payload: PersonUpdate) -> dict:
    updated = people.update_person(
        person_id,
        name=payload.name,
        aliases=payload.aliases,
        birth_year=payload.birth_year,
        clear_birth_year=payload.clear_birth_year,
        gender=payload.gender,
        clear_gender=payload.clear_gender,
        marital_status=payload.marital_status,
        clear_marital_status=payload.clear_marital_status,
        branch=payload.branch,
        note_en=payload.note_en,
        clear_note_en=payload.clear_note_en,
        note_ur=payload.note_ur,
        clear_note_ur=payload.clear_note_ur,
        origin="user",
    )
    return {"ok": True, "person": updated}


class PersonDelete(BaseModel):
    force: bool = False


@app.delete("/api/people/{person_id}")
def api_delete_person(person_id: str, payload: PersonDelete | None = None) -> dict:
    force = bool(payload.force) if payload else False
    return {"ok": True, **people.delete_person(person_id, force=force)}


class PersonDuplicateCheck(BaseModel):
    name: str
    aliases: list[str] | None = None


@app.post("/api/people/check-duplicate")
def api_check_duplicate_person(payload: PersonDuplicateCheck) -> dict:
    candidates = people.check_duplicate_person(payload.name, aliases=payload.aliases)
    return {"ok": True, "candidates": candidates}


class MutationPreviewRequest(BaseModel):
    action: str
    params: dict = {}


@app.post("/api/mutations/preview")
def api_preview_mutation(payload: MutationPreviewRequest) -> dict:
    return {"ok": True, **mutation_preview.preview_mutation(payload.action, payload.params)}


@app.post("/api/mutations/undo")
def api_undo_mutation() -> dict:
    return mutation_history.undo_last_mutation()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


@app.get("/api/groups")
def api_list_groups() -> dict:
    return {"ok": True, "groups": groups.list_groups()}


class GroupCreate(BaseModel):
    name: str


@app.post("/api/groups")
def api_create_group(payload: GroupCreate) -> dict:
    return {"ok": True, "group": groups.create_group(payload.name)}


class GroupAssign(BaseModel):
    group_id: str
    primary: bool = False


@app.post("/api/people/{person_id}/groups")
def api_assign_group(person_id: str, payload: GroupAssign) -> dict:
    updated = people.assign_group(
        person_id, payload.group_id, primary=payload.primary
    )
    return {"ok": True, "person": updated}


@app.delete("/api/people/{person_id}/groups/{group_id}")
def api_remove_group(person_id: str, group_id: str) -> dict:
    updated = people.remove_group(person_id, group_id)
    return {"ok": True, "person": updated}


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


@app.get("/api/relationships/from/{perspective_id}")
def api_relationships_from(
    perspective_id: str,
    domain: str | None = None,
    direct_only: bool = False,
) -> dict:
    rows = relationship.list_relationships_from(
        perspective_id, domain=domain, direct_only=bool(direct_only)
    )
    brief = people.get_person(perspective_id)
    return {
        "ok": True,
        "perspective": {"id": brief["id"], "name": brief["name"]},
        "relationships": rows,
    }


@app.get("/api/relationships/{perspective_id}/{target_id}")
def api_get_relationship(perspective_id: str, target_id: str) -> dict:
    result = relationship.get_relationship(perspective_id, target_id)
    return {"ok": True, **result}


@app.get("/api/relationships/{perspective_id}/{target_id}/paths")
def api_relationship_paths(
    perspective_id: str,
    target_id: str,
    max_depth: int = Query(default=10),
    max_paths: int = Query(default=10),
) -> dict:
    result = path_service.get_relationship_paths(
        perspective_id,
        target_id,
        max_depth=max_depth,
        max_paths=max_paths,
    )
    return {"ok": True, **result}


@app.get("/api/relationships/graph/neighbors/{person_id}")
def api_graph_neighbors(
    person_id: str,
    perspective_id: str | None = None,
    filters: str | None = None,
) -> dict:
    filter_list = None
    if filters:
        filter_list = [item.strip() for item in filters.split(",") if item.strip()]
    result = graph_service.get_graph_neighbors(
        person_id,
        perspective_id=perspective_id,
        filters=filter_list,
    )
    return {"ok": True, **result}


@app.get("/api/compare/{person_a}/{person_b}")
def api_compare(person_a: str, person_b: str) -> dict:
    return {"ok": True, **relationship.compare_people(person_a, person_b)}


class GeneralRelationshipCreate(BaseModel):
    person_a: str
    person_b: str
    type: str
    directionality: str = "symmetric"
    label_a_to_b: str | None = None
    label_b_to_a: str | None = None
    notes: str | None = None


@app.get("/api/relationships/general")
def api_general_relationships(person_id: str | None = None) -> dict:
    return {"ok": True, "relationships": general.list_general_relationships(person_id)}


@app.post("/api/relationships/general")
def api_create_general(payload: GeneralRelationshipCreate) -> dict:
    row = general.add_general_relationship(
        person_a=payload.person_a,
        person_b=payload.person_b,
        type=payload.type,
        directionality=payload.directionality,
        label_a_to_b=payload.label_a_to_b,
        label_b_to_a=payload.label_b_to_a,
        notes=payload.notes,
    )
    return {"ok": True, "relationship": row}


@app.delete("/api/relationships/general/{relationship_id}")
def api_delete_general(relationship_id: int) -> dict:
    return {"ok": True, **general.delete_general_relationship(relationship_id)}


class GeneralRelationshipUpdate(BaseModel):
    type: str | None = None
    label_a_to_b: str | None = None
    label_b_to_a: str | None = None
    notes: str | None = None


@app.patch("/api/relationships/general/{relationship_id}")
def api_update_general(relationship_id: int, payload: GeneralRelationshipUpdate) -> dict:
    return {
        "ok": True,
        "relationship": general.update_general_relationship(
            relationship_id,
            type=payload.type,
            label_a_to_b=payload.label_a_to_b,
            label_b_to_a=payload.label_b_to_a,
            notes=payload.notes,
        ),
    }


# ---------------------------------------------------------------------------
# Family facts / diagram
# ---------------------------------------------------------------------------


class ParentChildCreate(BaseModel):
    parent_id: str
    child_id: str
    role: str = "parent"
    kind: str = "biological"


@app.post("/api/family/parent-child")
def api_parent_child(payload: ParentChildCreate) -> dict:
    return {
        "ok": True,
        **family.add_parent_child(
            parent_id=payload.parent_id,
            child_id=payload.child_id,
            role=payload.role,
            kind=payload.kind,
            origin="user",
        ),
    }


class ParentChildDelete(BaseModel):
    parent_id: str
    child_id: str


@app.delete("/api/family/parent-child")
def api_delete_parent_child(payload: ParentChildDelete) -> dict:
    return {"ok": True, **family.delete_parent_child(payload.parent_id, payload.child_id)}


class ParentChildUpdate(BaseModel):
    parent_id: str
    child_id: str
    role: str | None = None
    kind: str | None = None


@app.patch("/api/family/parent-child")
def api_update_parent_child(payload: ParentChildUpdate) -> dict:
    return {
        "ok": True,
        **family.update_parent_child(
            payload.parent_id, payload.child_id, role=payload.role, kind=payload.kind
        ),
    }


class MarriageCreate(BaseModel):
    person_a: str
    person_b: str
    status: str = "married"
    year: int | None = Field(default=None, ge=1800, le=2100)
    children_status: str | None = None


@app.post("/api/family/marriage")
def api_marriage(payload: MarriageCreate) -> dict:
    return {
        "ok": True,
        **family.add_marriage(
            person_a=payload.person_a,
            person_b=payload.person_b,
            status=payload.status,
            year=payload.year,
            children_status=payload.children_status,
            origin="user",
        ),
    }


class MarriageDelete(BaseModel):
    person_a: str
    person_b: str


@app.delete("/api/family/marriage")
def api_delete_marriage(payload: MarriageDelete) -> dict:
    return {"ok": True, **family.delete_marriage(payload.person_a, payload.person_b)}


class MarriageUpdate(BaseModel):
    person_a: str
    person_b: str
    status: str | None = None
    year: int | None = Field(default=None, ge=1800, le=2100)
    children_status: str | None = None


@app.patch("/api/family/marriage")
def api_update_marriage(payload: MarriageUpdate) -> dict:
    return {
        "ok": True,
        **family.update_marriage(
            payload.person_a,
            payload.person_b,
            status=payload.status,
            year=payload.year,
            children_status=payload.children_status,
        ),
    }


class SiblingGroupCreate(BaseModel):
    member_ids: list[str]
    type_: str | None = None
    ordered: bool = False


@app.post("/api/family/sibling-group")
def api_create_sibling_group(payload: SiblingGroupCreate) -> dict:
    return {
        "ok": True,
        **family.add_sibling_group(
            member_ids=payload.member_ids,
            type_=payload.type_,
            ordered=payload.ordered,
            origin="user",
        ),
    }


@app.delete("/api/family/sibling-group/{group_id}")
def api_delete_sibling_group(group_id: str) -> dict:
    return {"ok": True, **family.delete_sibling_group(group_id)}


@app.get("/api/family/facts")
def api_family_facts() -> dict:
    return {"ok": True, **family.family_facts()}


@app.get("/api/family/diagram")
def api_family_diagram(perspective_id: str | None = None) -> dict:
    import build_family

    model = load_model()
    focus = perspective_id or model["metadata"].get("focus_person")
    people.get_person(focus)
    adjusted = _diagram_model(model, focus)
    validate_model(adjusted)
    mermaid_text = build_family.build_mermaid(adjusted)
    build_family.audit_render_mapping(adjusted, mermaid_text)
    return {
        "ok": True,
        "perspective_id": focus,
        "mermaid": mermaid_text,
    }


def _diagram_model(model: dict, focus_id: str) -> dict:
    """Copy of the model whose person labels describe relationship to the
    requested perspective (rendering only; nothing is written back)."""
    from build_family import _viewer_pair

    adjusted = copy.deepcopy(model)
    adjusted["metadata"] = dict(adjusted.get("metadata", {}))
    adjusted["metadata"]["focus_person"] = focus_id
    index = {person["id"]: person for person in adjusted["people"]}
    focus_name = index[focus_id]["name"]
    for person in adjusted["people"]:
        if person["id"] == focus_id:
            person["relation_en"] = "Self"
            person["relation_ur"] = "خود"
            continue
        pair = _viewer_pair(model, focus_id, person["id"], index)
        main = pair.get("main") or []
        if not main:
            person["relation_en"] = None
            person["relation_ur"] = None
            continue
        person["relation_en"] = " / ".join(item["en"] for item in main)
        with_ur = [item for item in main if item.get("ur")]
        person["relation_ur"] = with_ur[0]["ur"] if len(with_ur) == 1 else None
    return adjusted


@app.get("/api/family/snapshot")
def api_family_snapshot() -> dict:
    return {"ok": True, **family_snapshot(load_model())}


@app.get("/api/audit/family")
def api_audit_family() -> dict:
    model = load_model()
    validate_model(model)
    audits = run_family_audits(model)
    return {"ok": True, "audits": audits}


# ---------------------------------------------------------------------------
# Journals
# ---------------------------------------------------------------------------


@app.get("/api/people/{person_id}/journal")
def api_read_journal(person_id: str) -> dict:
    return {"ok": True, **journals.read_journal(person_id)}


class JournalSave(BaseModel):
    content: str
    expected_modified_ns: str | None = None
    expected_sha256: str | None = None


@app.put("/api/people/{person_id}/journal")
def api_save_journal(person_id: str, payload: JournalSave) -> dict:
    result = journals.save_journal(
        person_id,
        payload.content,
        expected_modified_ns=payload.expected_modified_ns,
        expected_sha256=payload.expected_sha256,
        origin="user",
    )
    return {"ok": True, **result}


class JournalAppend(BaseModel):
    text: str
    heading: str | None = None


@app.post("/api/people/{person_id}/journal/append")
def api_append_journal(person_id: str, payload: JournalAppend) -> dict:
    result = journals.append_journal(
        person_id, payload.text, heading=payload.heading, origin="user"
    )
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@app.get("/api/search")
def api_search(q: str = "", limit: int = 40) -> dict:
    return {"ok": True, **search.search(q, limit=limit)}


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------


class BackupCreate(BaseModel):
    label: str | None = None


@app.post("/api/backups")
def api_create_backup(payload: BackupCreate | None = None) -> dict:
    label = payload.label if payload else None
    return {"ok": True, "backup": backups.create_backup(label=label)}


@app.get("/api/backups")
def api_list_backups() -> dict:
    return {"ok": True, "backups": backups.list_backups()}


@app.get("/api/backups/{name}/verify")
def api_verify_backup(name: str) -> dict:
    return {"ok": True, **backups.verify_backup(name)}


# ---------------------------------------------------------------------------
# Hermes
# ---------------------------------------------------------------------------


@app.get("/api/hermes/tools")
def api_hermes_tools() -> dict:
    return {"ok": True, "tools": hermes_tools.list_tools()}


class HermesRun(BaseModel):
    tool: str
    arguments: dict = {}


@app.post("/api/hermes/run")
def api_hermes_run(payload: HermesRun) -> dict:
    return hermes_tools.run_tool(payload.tool, payload.arguments)
