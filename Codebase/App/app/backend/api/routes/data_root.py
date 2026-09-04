"""Data Root API Routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...data_root.errors import DataRootError
from ...services.data_root import (
    get_data_root_status,
    move_data_root,
    safe_repair_active_data_root,
    switch_data_root,
    validate_active_data_root,
)

router = APIRouter(prefix="/api/data-root", tags=["data-root"])


class MoveDataRootRequest(BaseModel):
    destination_path: str = Field(..., description="Target directory path for moving active data root")


class SwitchDataRootRequest(BaseModel):
    target_path: str = Field(..., description="Target existing valid data root directory path")


@router.get("")
def status():
    return get_data_root_status()


@router.get("/health")
def health():
    return get_data_root_status()


@router.post("/validate")
def validate():
    return validate_active_data_root()


@router.post("/repair")
def repair():
    return safe_repair_active_data_root()


@router.post("/move")
def move(req: MoveDataRootRequest):
    try:
        return move_data_root(req.destination_path)
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": str(exc), "code": "MOVE_FAILED"}) from exc


@router.post("/switch")
def switch(req: SwitchDataRootRequest):
    try:
        return switch_data_root(req.target_path)
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": str(exc), "code": "SWITCH_FAILED"}) from exc
