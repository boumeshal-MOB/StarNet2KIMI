"""Catalogue endpoints: stations, sensors, physical points, templates, audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..templates import TEMPLATES

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/bootstrap")
def bootstrap(db: Session = Depends(get_db)) -> dict:
    stations = []
    for station in db.execute(select(models.Station)).scalars():
        obs_count = db.scalar(
            select(func.count(models.RawObservation.id)).where(models.RawObservation.station_code == station.code)
        )
        last_epoch = db.scalar(
            select(func.max(models.RawObservation.epoch)).where(models.RawObservation.station_code == station.code)
        )
        sensors = [
            {
                "id": sensor.id,
                "raw_name": sensor.raw_name,
                "measurement_type": sensor.measurement_type,
                "prism_constant_required_m": sensor.prism_constant_required_m,
                "target_height_m": sensor.target_height_m,
            }
            for sensor in db.execute(select(models.Sensor).where(models.Sensor.station_code == station.code)).scalars()
        ]
        env_count = db.scalar(
            select(func.count(models.EnvironmentReading.id)).where(models.EnvironmentReading.station_code == station.code)
        )
        stations.append(
            {
                "code": station.code,
                "name": station.name,
                "instrument_model": station.instrument_model,
                "site": station.site,
                "coordinates": {"e": station.e, "n": station.n, "h": station.h},
                "observation_count": obs_count,
                "last_observation_epoch": last_epoch,
                "environment_readings": env_count,
                "sensors": sensors,
            }
        )
    points = [
        {
            "id": point.id,
            "label": point.label,
            "known": None
            if point.known_e is None
            else {"e": point.known_e, "n": point.known_n, "h": point.known_h},
            "sigma_m": None
            if point.sigma_e_m is None
            else {"e": point.sigma_e_m, "n": point.sigma_n_m, "h": point.sigma_h_m},
        }
        for point in db.execute(select(models.PhysicalPoint)).scalars()
    ]
    templates = {key: {"label": value["label"], "prism_examples_m": value["prism_examples_m"], "atmospheric": value["atmospheric"], "default_weights": value["default_weights"]} for key, value in TEMPLATES.items()}
    return {"stations": stations, "physical_points": points, "templates": templates}


@router.get("/audit")
def audit(processing_id: int | None = None, limit: int = 100, db: Session = Depends(get_db)) -> list[dict]:
    query = select(models.AuditEvent).order_by(models.AuditEvent.id.desc()).limit(limit)
    if processing_id is not None:
        query = query.where(models.AuditEvent.processing_id == processing_id)
    return [
        {"id": event.id, "ts": event.ts, "kind": event.kind, "message": event.message, "payload": event.payload, "processing_id": event.processing_id}
        for event in db.execute(query).scalars()
    ]
