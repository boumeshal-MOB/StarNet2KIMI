"""Analysis Lab: trial adjustments with overrides, never touching production."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..services import engine as engine_service

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class TrialRequest(BaseModel):
    processing_id: int
    slot: str
    version_id: int | None = None
    overrides: dict = {}


@router.post("/trial")
def trial(body: TrialRequest, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, body.processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    if body.version_id is not None:
        version = db.get(models.ConfigVersion, body.version_id)
        if version is None or version.processing_id != body.processing_id:
            raise HTTPException(404, "Version not found")
    else:
        version = engine_service.resolve_version(db, body.processing_id, body.slot)
        if version is None:
            raise HTTPException(422, f"No configuration version valid at {body.slot}")
    result = engine_service.run_pipeline(db, processing, version, body.slot, trigger="analysis", overrides=body.overrides, persist=False)
    result["processing_id"] = processing.id
    return result


class SaveDraftRequest(BaseModel):
    processing_id: int
    base_version_id: int
    payload: dict
    note: str = ""


@router.post("/save-draft")
def save_draft(body: SaveDraftRequest, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, body.processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    base = db.get(models.ConfigVersion, body.base_version_id)
    if base is None or base.processing_id != body.processing_id:
        raise HTTPException(404, "Base version not found")
    next_number = max(v.number for v in processing.versions) + 1
    draft = models.ConfigVersion(
        processing_id=body.processing_id,
        number=next_number,
        status="draft",
        valid_from=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        valid_to=None,
        payload=body.payload,
        origin="analysis-lab",
    )
    db.add(draft)
    db.add(models.AuditEvent(processing_id=body.processing_id, kind="version", message=f"Draft v{next_number} saved from Analysis Lab ({body.note})", payload={}))
    db.commit()
    return {"id": draft.id, "number": draft.number, "status": draft.status}
