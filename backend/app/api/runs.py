"""Runs: manual run, reprocess, run detail, published outputs."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..services import engine as engine_service

router = APIRouter(prefix="/api", tags=["runs"])


def run_summary(run: models.Run) -> dict:
    return {
        "id": run.id,
        "processing_id": run.processing_id,
        "version_id": run.version_id,
        "slot": run.slot,
        "trigger": run.trigger,
        "status": run.status,
        "chi_square_status": run.chi_square_status,
        "engine": run.engine,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at,
        "indicators": run.result.get("indicators") if run.result else None,
    }


def run_detail(run: models.Run) -> dict:
    detail = run_summary(run)
    detail["result"] = run.result
    detail["diagnostics"] = run.diagnostics
    detail["starnet"] = run.starnet
    return detail


class RunRequest(BaseModel):
    slot: str | None = None


@router.post("/processings/{processing_id}/run")
def run_now(processing_id: int, body: RunRequest, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    slot = body.slot
    if slot is None:
        version = engine_service.active_version(db, processing_id)
        grid = int((version.payload.get("output", {}) if version else {}).get("grid_minutes", 30))
        last = db.scalar(select(models.RawObservation.epoch).order_by(models.RawObservation.epoch.desc()).limit(1))
        if last is None:
            raise HTTPException(422, "No raw observations available")
        slot = engine_service._iso(engine_service.slot_floor(engine_service._instant(last), grid))
    version = engine_service.resolve_version(db, processing_id, slot)
    if version is None:
        raise HTTPException(422, f"No configuration version valid at {slot}")
    result = engine_service.run_pipeline(db, processing, version, slot, trigger="manual")
    return result


class ReprocessRequest(BaseModel):
    from_slot: str
    to_slot: str


@router.post("/processings/{processing_id}/reprocess")
def reprocess(processing_id: int, body: ReprocessRequest, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    start, end = engine_service._instant(body.from_slot), engine_service._instant(body.to_slot)
    if end < start:
        raise HTTPException(422, "to_slot must be after from_slot")
    results = []
    slot = start
    while slot <= end:
        slot_iso = engine_service._iso(slot)
        version = engine_service.resolve_version(db, processing_id, slot_iso)
        grid = 30
        if version is not None:
            grid = int(version.payload.get("output", {}).get("grid_minutes", 30))
            results.append(engine_service.run_pipeline(db, processing, version, slot_iso, trigger="reprocess"))
        else:
            results.append({"slot": slot_iso, "status": "failed", "failure": "no valid version"})
        slot += timedelta(minutes=grid)
    db.add(models.AuditEvent(processing_id=processing_id, kind="reprocess", message=f"Reprocess {body.from_slot} → {body.to_slot}: {len(results)} slots", payload={"slots": len(results)}))
    db.commit()
    return {"slots": len(results), "results": [{k: r.get(k) for k in ("id", "slot", "status", "chi_square_status")} for r in results]}


@router.get("/processings/{processing_id}/runs")
def list_runs(processing_id: int, limit: int = 60, db: Session = Depends(get_db)) -> list[dict]:
    runs = db.execute(
        select(models.Run).where(models.Run.processing_id == processing_id).order_by(models.Run.slot.desc()).limit(limit)
    ).scalars().all()
    return [run_summary(run) for run in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(models.Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run_detail(run)


@router.get("/processings/{processing_id}/outputs")
def outputs(processing_id: int, component: str = "DZ", db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(models.OutputValue)
        .where(models.OutputValue.processing_id == processing_id)
        .where(models.OutputValue.component == component.upper())
        .order_by(models.OutputValue.slot)
    ).scalars().all()
    series: dict[str, list[dict]] = {}
    for row in rows:
        series.setdefault(row.point_id, []).append({"slot": row.slot, "value": row.value, "run_id": row.run_id})
    return {"component": component.upper(), "series": series}
