"""Demo controls: state, reset, late-data delivery with automatic catch-up."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..seed import deliver_late_data, reset_database, seed
from ..services import engine as engine_service

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/state")
def state(db: Session = Depends(get_db)) -> dict:
    late = db.get(models.DemoState, "late_data")
    stats = {
        "stations": len(db.execute(select(models.Station)).scalars().all()),
        "sensors": len(db.execute(select(models.Sensor)).scalars().all()),
        "raw_observations": len(db.execute(select(models.RawObservation.id)).scalars().all()),
        "environment_readings": len(db.execute(select(models.EnvironmentReading.id)).scalars().all()),
        "processings": len(db.execute(select(models.Processing)).scalars().all()),
        "runs": len(db.execute(select(models.Run.id)).scalars().all()),
    }
    return {"late_data": late.value if late else None, "stats": stats}


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> dict:
    engine_service._initials_cache.clear()
    reset_database()
    db2 = next(get_db())
    try:
        seed(db2)
    finally:
        db2.close()
    return {"reset": True}


@router.post("/deliver-late")
def deliver_late(db: Session = Depends(get_db)) -> dict:
    outcome = deliver_late_data(db)
    if not outcome.get("delivered"):
        return {**outcome, "catch_up": []}
    # Catch-up: provisional network runs covering the late cycle are recomputed.
    late_cycle = engine_service._instant(outcome["cycle"])
    catch_up = []
    processings = db.execute(select(models.Processing).where(models.Processing.kind == "network")).scalars().all()
    for processing in processings:
        runs = db.execute(
            select(models.Run).where(models.Run.processing_id == processing.id).where(models.Run.status == "provisional")
        ).scalars().all()
        for run in runs:
            slot = engine_service._instant(run.slot)
            if abs((slot - late_cycle).total_seconds()) > 3600 * 2:
                continue
            version = db.get(models.ConfigVersion, run.version_id)
            if version is None:
                continue
            rerun = engine_service.run_pipeline(db, processing, version, run.slot, trigger="catch-up")
            catch_up.append({"processing_id": processing.id, "slot": run.slot, "run_id": rerun["id"], "status": rerun["status"]})
    db.add(models.AuditEvent(kind="catch-up", message=f"Catch-up recomputed {len(catch_up)} provisional slot(s)", payload={"slots": catch_up}))
    db.commit()
    return {**outcome, "catch_up": catch_up}
