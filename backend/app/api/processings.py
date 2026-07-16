"""Processings and versioned configurations."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..services import engine as engine_service
from ..services.engine import active_version
from ..templates import base_payload

router = APIRouter(prefix="/api/processings", tags=["processings"])


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def version_summary(version: models.ConfigVersion) -> dict:
    return {
        "id": version.id,
        "processing_id": version.processing_id,
        "number": version.number,
        "status": version.status,
        "valid_from": version.valid_from,
        "valid_to": version.valid_to,
        "origin": version.origin,
        "created_at": version.created_at,
        "payload": version.payload,
    }


def processing_summary(db: Session, processing: models.Processing) -> dict:
    active = active_version(db, processing.id)
    last_run = db.execute(
        select(models.Run).where(models.Run.processing_id == processing.id).order_by(models.Run.id.desc()).limit(1)
    ).scalars().first()
    run_count = len(db.execute(select(models.Run.id).where(models.Run.processing_id == processing.id)).scalars().all())
    version_count = len(db.execute(select(models.ConfigVersion.id).where(models.ConfigVersion.processing_id == processing.id)).scalars().all())
    return {
        "id": processing.id,
        "name": processing.name,
        "description": processing.description,
        "kind": processing.kind,
        "template": processing.template,
        "state": processing.state,
        "created_at": processing.created_at,
        "active_version": version_summary(active) if active else None,
        "version_count": version_count,
        "run_count": run_count,
        "last_run": None
        if last_run is None
        else {
            "id": last_run.id,
            "slot": last_run.slot,
            "status": last_run.status,
            "chi_square_status": last_run.chi_square_status,
            "trigger": last_run.trigger,
            "created_at": last_run.created_at,
        },
    }


@router.get("")
def list_processings(db: Session = Depends(get_db)) -> list[dict]:
    return [processing_summary(db, p) for p in db.execute(select(models.Processing).order_by(models.Processing.id)).scalars()]


@router.get("/{processing_id}")
def get_processing(processing_id: int, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    summary = processing_summary(db, processing)
    summary["versions"] = [
        version_summary(v)
        for v in db.execute(
            select(models.ConfigVersion).where(models.ConfigVersion.processing_id == processing_id).order_by(models.ConfigVersion.number)
        ).scalars()
    ]
    return summary


class CreateProcessing(BaseModel):
    name: str
    description: str = ""
    kind: str = "network"
    template: str = "uk"
    state: str = "active"
    payload: dict


@router.post("")
def create_processing(body: CreateProcessing, db: Session = Depends(get_db)) -> dict:
    if body.kind not in {"single-station", "network"}:
        raise HTTPException(422, "kind must be single-station or network")
    stations = {s["code"] for s in body.payload.get("stations", [])}
    if not stations:
        raise HTTPException(422, "At least one station is required")
    if body.kind == "single-station" and len(stations) != 1:
        raise HTTPException(422, "A single-station processing takes exactly one station")
    if body.kind == "network" and len(stations) < 2:
        raise HTTPException(422, "A network processing takes at least two stations")
    _check_connectivity(body.payload)

    processing = models.Processing(name=body.name, description=body.description, kind=body.kind, template=body.template, state=body.state)
    processing.versions.append(
        models.ConfigVersion(number=1, status="active", valid_from=_iso_now(), valid_to=None, payload=body.payload, origin="manual")
    )
    db.add(processing)
    db.add(models.AuditEvent(kind="processing", message=f"Processing «{body.name}» created", payload={"template": body.template, "kind": body.kind}))
    db.commit()
    return processing_summary(db, processing)


def _check_connectivity(payload: dict) -> None:
    """A network must be connected through explicitly shared physical points."""
    stations = [s["code"] for s in payload.get("stations", [])]
    if len(stations) < 2:
        return
    adjacency: dict[str, set[str]] = {station: set() for station in stations}
    by_point: dict[str, set[str]] = {}
    for target in payload.get("targets", []):
        by_point.setdefault(target["physical_point_id"], set()).add(target["station_code"])
    for shared in by_point.values():
        for a in shared:
            adjacency[a] |= shared - {a}
    seen = {stations[0]}
    frontier = [stations[0]]
    while frontier:
        current = frontier.pop()
        for neighbour in adjacency[current] - seen:
            seen.add(neighbour)
            frontier.append(neighbour)
    if seen != set(stations):
        raise HTTPException(422, "Stations do not form a connected network: confirm shared physical points first")


@router.patch("/{processing_id}")
def update_processing(processing_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    for field in ("name", "description", "state"):
        if field in body:
            setattr(processing, field, body[field])
    db.commit()
    return processing_summary(db, processing)


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

class NewDraft(BaseModel):
    from_version_id: int
    payload: dict | None = None


@router.post("/{processing_id}/versions")
def create_draft(processing_id: int, body: NewDraft, db: Session = Depends(get_db)) -> dict:
    processing = db.get(models.Processing, processing_id)
    if processing is None:
        raise HTTPException(404, "Processing not found")
    source = db.get(models.ConfigVersion, body.from_version_id)
    if source is None or source.processing_id != processing_id:
        raise HTTPException(404, "Source version not found")
    next_number = (max(v.number for v in processing.versions) if processing.versions else 0) + 1
    draft = models.ConfigVersion(
        processing_id=processing_id,
        number=next_number,
        status="draft",
        valid_from=_iso_now(),
        valid_to=None,
        payload=body.payload if body.payload is not None else source.payload,
        origin="manual",
    )
    db.add(draft)
    db.add(models.AuditEvent(processing_id=processing_id, kind="version", message=f"Draft v{next_number} created from v{source.number}", payload={}))
    db.commit()
    return version_summary(draft)


@router.post("/{processing_id}/versions/{version_id}/activate")
def activate_version(processing_id: int, version_id: int, body: dict | None = None, db: Session = Depends(get_db)) -> dict:
    version = db.get(models.ConfigVersion, version_id)
    if version is None or version.processing_id != processing_id:
        raise HTTPException(404, "Version not found")
    valid_from = (body or {}).get("valid_from") or _iso_now()
    others = db.execute(
        select(models.ConfigVersion).where(models.ConfigVersion.processing_id == processing_id)
    ).scalars().all()
    for other in others:
        if other.id == version.id:
            continue
        if other.status == "active":
            other.status = "inactive"
            other.valid_to = valid_from
        elif other.status in {"inactive"} and other.valid_to is None and other.valid_from < valid_from:
            other.valid_to = valid_from
    version.status = "active"
    version.valid_from = valid_from
    version.valid_to = None
    engine_service._initials_cache.pop(version.id, None)
    db.add(models.AuditEvent(processing_id=processing_id, kind="version", message=f"Version v{version.number} activated from {valid_from}", payload={}))
    db.commit()
    return version_summary(version)


@router.post("/{processing_id}/versions/{version_id}/archive")
def archive_version(processing_id: int, version_id: int, db: Session = Depends(get_db)) -> dict:
    version = db.get(models.ConfigVersion, version_id)
    if version is None or version.processing_id != processing_id:
        raise HTTPException(404, "Version not found")
    if version.status == "active":
        raise HTTPException(422, "The active version cannot be archived")
    version.status = "archived"
    db.commit()
    return version_summary(version)


@router.get("/{processing_id}/compare")
def compare_versions(processing_id: int, a: int, b: int, db: Session = Depends(get_db)) -> dict:
    va, vb = db.get(models.ConfigVersion, a), db.get(models.ConfigVersion, b)
    if va is None or vb is None or va.processing_id != processing_id or vb.processing_id != processing_id:
        raise HTTPException(404, "Version not found")
    return {"a": va.number, "b": vb.number, "diff": _diff(va.payload, vb.payload)}


def _diff(a, b, path: str = "") -> list[dict]:
    changes = []
    if type(a) is not type(b):
        changes.append({"path": path, "from": a, "to": b})
    elif isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                changes.append({"path": f"{path}.{key}", "from": None, "to": b[key]})
            elif key not in b:
                changes.append({"path": f"{path}.{key}", "from": a[key], "to": None})
            else:
                changes.extend(_diff(a[key], b[key], f"{path}.{key}"))
    elif isinstance(a, list):
        if a != b:
            changes.append({"path": path, "from": f"{len(a)} items", "to": f"{len(b)} items"})
    elif a != b:
        changes.append({"path": path, "from": a, "to": b})
    return changes


@router.get("/{processing_id}/initial-coordinates")
def initial_coordinates(processing_id: int, version_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    version = db.get(models.ConfigVersion, version_id) if version_id else active_version(db, processing_id)
    if version is None or version.processing_id != processing_id:
        raise HTTPException(404, "Version not found")
    return engine_service.initials_for(db, version)
