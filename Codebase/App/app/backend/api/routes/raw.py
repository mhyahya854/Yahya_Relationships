"""Phase 12 Raw review API: explicit scan, review, approval, and safe move."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...data_root.errors import DataRootError
from ...domain import raw_intake

router = APIRouter(prefix="/api/raw", tags=["raw"])


class RawCorrectionRequest(BaseModel):
    classification: str | None = None
    destination_relative_path: str | None = Field(default=None, max_length=1024)
    note: str | None = Field(default=None, max_length=4000)


class RawDecisionRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=4000)


def _error(exc: DataRootError, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=exc.to_dict())


@router.get("")
def list_items(
    filter_name: str | None = Query(default=None, alias="filter"),
    query: str | None = Query(default=None, max_length=500),
):
    try:
        return raw_intake.list_raw_items(filter_name=filter_name, query=query)
    except DataRootError as exc:
        raise _error(exc) from exc


@router.post("/scan")
def scan():
    try:
        return raw_intake.scan_raw()
    except DataRootError as exc:
        raise _error(exc) from exc


@router.post("/recover")
def recover():
    try:
        return raw_intake.recover_pending_moves()
    except DataRootError as exc:
        raise _error(exc) from exc


@router.get("/{item_id}")
def item(item_id: str):
    try:
        return raw_intake.get_raw_item(item_id)
    except DataRootError as exc:
        raise _error(exc, 404 if exc.code == "RAW_ITEM_NOT_FOUND" else 400) from exc


@router.post("/{item_id}/rehash")
def rehash(item_id: str):
    try:
        return raw_intake.rehash_item(item_id)
    except DataRootError as exc:
        raise _error(exc) from exc


@router.post("/{item_id}/correct")
def correct(item_id: str, payload: RawCorrectionRequest):
    try:
        return raw_intake.correct_item(
            item_id,
            classification=payload.classification,
            destination_relative_path=payload.destination_relative_path,
            note=payload.note,
        )
    except DataRootError as exc:
        raise _error(exc) from exc


@router.post("/{item_id}/decision")
def decision(item_id: str, payload: RawDecisionRequest):
    try:
        return raw_intake.decide_item(item_id, payload.decision, note=payload.note)
    except DataRootError as exc:
        raise _error(exc) from exc


@router.post("/{item_id}/move")
def move(item_id: str):
    try:
        return raw_intake.move_approved_item(item_id)
    except DataRootError as exc:
        raise _error(exc) from exc
