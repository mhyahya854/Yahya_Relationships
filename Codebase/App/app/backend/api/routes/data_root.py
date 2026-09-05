"""Data Root API Routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...data_root.errors import DataRootError
from ...services.data_root import (
    get_data_root_status,
    initialize_new_data_root,
    move_data_root,
    restore_backup_to_data_root,
    safe_repair_active_data_root,
    switch_data_root,
    validate_active_data_root,
)

router = APIRouter(prefix="/api/data-root", tags=["data-root"])


class MoveDataRootRequest(BaseModel):
    destination_path: str = Field(..., description="Target directory path for moving active data root")


class SwitchDataRootRequest(BaseModel):
    target_path: str = Field(..., description="Target existing valid data root directory path")


class InitializeDataRootRequest(BaseModel):
    target_path: str = Field(..., description="Target directory path for brand new data root")
    owner_name: str = Field("Mohammad Yahya Hussain", description="Initial owner name")


class RestoreDataRootRequest(BaseModel):
    backup_path: str = Field(..., description="Path to valid backup directory")
    target_path: str | None = Field(None, description="Optional target directory path to restore into")


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


@router.post("/initialize")
def initialize(req: InitializeDataRootRequest):
    try:
        return initialize_new_data_root(req.target_path, owner_name=req.owner_name)
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": str(exc), "code": "INITIALIZE_FAILED"}) from exc


@router.post("/restore-to")
def restore_to(req: RestoreDataRootRequest):
    try:
        return restore_backup_to_data_root(req.backup_path, target_root=req.target_path)
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": str(exc), "code": "RESTORE_FAILED"}) from exc
