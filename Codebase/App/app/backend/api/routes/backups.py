"""Backups API Routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...data_root.errors import DataRootError
from ...services.backups import (
    execute_create_backup,
    execute_restore_backup,
    execute_verify_backup,
    get_backup_details,
    list_backups,
)

router = APIRouter(prefix="/api/backups", tags=["backups"])


class CreateBackupRequest(BaseModel):
    label: str = Field(default="manual", description="Optional descriptive label for backup")


class RestoreBackupRequest(BaseModel):
    confirmation_token: str = Field(default="RESTORE", description="Must be 'RESTORE' to confirm")


@router.get("")
def get_backups():
    return {"backups": list_backups()}


@router.post("")
def create(req: CreateBackupRequest | None = None):
    try:
        label = req.label if req else "manual"
        res = execute_create_backup(label=label)
        backup_obj = {
            "id": res["id"],
            "name": res["id"],
            "path": res["path"],
            "manifest": res.get("manifest"),
            "verification": res.get("verification"),
        }
        return {"ok": True, "backup": backup_obj}
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc


@router.get("/{backup_id}")
def details(backup_id: str):
    try:
        return get_backup_details(backup_id)
    except DataRootError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()) from exc


@router.get("/{backup_id}/verify")
@router.post("/{backup_id}/verify")
def verify(backup_id: str):
    try:
        return execute_verify_backup(backup_id)
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc


@router.post("/{backup_id}/restore")
def restore(backup_id: str, req: RestoreBackupRequest | None = None):
    try:
        token = req.confirmation_token if req else "RESTORE"
        return execute_restore_backup(backup_id, confirmation_token=token)
    except DataRootError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": str(exc), "code": "RESTORE_FAILED"}) from exc
