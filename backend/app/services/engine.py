"""Run pipeline: raw_data → synchronisation → corrections → initialisation →
weighted least squares → STAR*NET artifacts → published outputs.

The Python engine computes; STAR*NET files are built for the production
handoff and parsed back through the same contract the worker will use.
"""

from __future__ import annotations

import copy
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from btm_topography.adjustment import adjust_network, auto_adjust
from btm_topography.corrections import apply_distance_corrections
from btm_topography.initialisation import initialise_network
from btm_topography.preparation import prepare_scalar_observations
from btm_topography.synchronisation import select_network_epochs

from .. import models
from . import starnet

ENGINE_ID = "python-lsq-v1"
COMPONENTS = ("X", "Y", "Z", "DX", "DY", "DZ", "SX", "SY", "SZ")

_initials_cache: dict[int, dict[str, Any]] = {}


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def slot_floor(instant: datetime, grid_minutes: int) -> datetime:
    minute = (instant.minute // grid_minutes) * grid_minutes
    return instant.replace(minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Initial coordinates
# ---------------------------------------------------------------------------

def compute_initials(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Median-based initial coordinates over the version's initialisation window."""
    init = payload.get("initialisation", {})
    window_from = init.get("window_from")
    window_to = init.get("window_to")
    station_codes = [s["code"] for s in payload["stations"]]
    known_points = {
        p["id"]: (p["known"]["e"], p["known"]["n"], p["known"]["h"])
        for p in payload["physical_points"]
        if p.get("known")
    }
    query = (
        select(models.RawObservation, models.Sensor)
        .join(models.Sensor, models.RawObservation.sensor_id == models.Sensor.id)
        .where(models.RawObservation.station_code.in_(station_codes))
    )
    if window_from:
        query = query.where(models.RawObservation.epoch >= window_from)
    if window_to:
        query = query.where(models.RawObservation.epoch <= window_to)

    point_of = {(t["station_code"], t["sensor_id"]): t["physical_point_id"] for t in payload["targets"]}
    observations = []
    for raw, sensor in db.execute(query).all():
        point_id = point_of.get((raw.station_code, raw.sensor_id))
        if point_id is None:
            continue
        observations.append(
            {
                "station_id": raw.station_code,
                "physical_point_id": point_id,
                "epoch": raw.epoch,
                "hz_rad": raw.hz_rad,
                "vz_rad": raw.vz_rad,
                "slope_distance_m": raw.sd_m,
                "target_height_m": sensor.target_height_m,
            }
        )
    stations_payload = []
    for station in payload["stations"]:
        row: dict[str, Any] = {"id": station["code"], "instrument_height_m": station.get("instrument_height_m", 0.0)}
        coords = station.get("coordinates", {})
        if coords.get("mode") == "fixed":
            row["fixed_coordinates"] = (coords["e"], coords["n"], coords["h"])
            if coords.get("orientation_rad") is not None:
                row["fixed_orientation_rad"] = coords["orientation_rad"]
        elif coords.get("e") is not None:
            row["approximate_coordinates"] = (coords["e"], coords["n"], coords["h"])
        stations_payload.append(row)

    result = initialise_network(
        {
            "observations": observations,
            "stations": stations_payload,
            "known_points": known_points,
            "expected_pairs": [(t["station_code"], t["physical_point_id"]) for t in payload["targets"]],
        }
    )
    initials: dict[str, tuple[float, float, float]] = {}
    for point_id, coord in known_points.items():
        initials[point_id] = (coord[0], coord[1], coord[2])
    for row in result["coordinates"]:
        initials[row["point_id"]] = (row["e"], row["n"], row["h"])
    for row in result["station_solutions"]:
        initials[row["station_id"]] = (row["e"], row["n"], row["h"])
    result["initials"] = {key: list(value) for key, value in initials.items()}
    return result


def initials_for(db: Session, version: models.ConfigVersion) -> dict[str, Any]:
    cached = _initials_cache.get(version.id)
    if cached is None:
        cached = compute_initials(db, version.payload)
        _initials_cache[version.id] = cached
    return cached


# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    db: Session,
    processing: models.Processing,
    version: models.ConfigVersion,
    slot_iso: str,
    trigger: str,
    overrides: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = copy.deepcopy(version.payload)
    if overrides:
        _apply_overrides(payload, overrides)
    run_cfg = payload.get("run", {})
    output_cfg = payload.get("output", {})
    adj_cfg = payload.get("adjustment", {})
    corr_cfg = payload.get("corrections", {}).get("atmospheric", {})

    slot = _instant(slot_iso)
    diagnostics: dict[str, Any] = {"trigger": trigger, "slot": slot_iso, "steps": []}

    # 1 — Synchronisation: one acquisition cycle per station.
    allow_future = float(run_cfg.get("allow_future_minutes", 45))
    window_from = _iso(slot - timedelta(minutes=float(run_cfg.get("max_epoch_to_slot_minutes", 90))))
    station_codes = [s["code"] for s in payload["stations"]]
    raw_rows = db.execute(
        select(models.RawObservation, models.Sensor)
        .join(models.Sensor, models.RawObservation.sensor_id == models.Sensor.id)
        .where(models.RawObservation.station_code.in_(station_codes))
        .where(models.RawObservation.epoch >= window_from)
        .where(models.RawObservation.epoch <= _iso(slot + timedelta(minutes=allow_future)))
    ).all()
    sync = select_network_epochs(
        [
            {
                "station_code": raw.station_code,
                "target_name": sensor.raw_name,
                "epoch": raw.epoch,
                "observation_id": raw.id,
            }
            for raw, sensor in raw_rows
        ],
        station_codes,
        slot_iso,
        cycle_tolerance_minutes=float(run_cfg.get("cycle_tolerance_minutes", 12)),
        fresh_tolerance_minutes=float(run_cfg.get("sync_tolerance_minutes", 35)),
        max_reused_age_minutes=float(run_cfg.get("max_reused_age_minutes", 180)),
        max_epoch_to_slot_minutes=float(run_cfg.get("max_epoch_to_slot_minutes", 90)),
        allow_future_minutes=allow_future,
    )
    diagnostics["synchronisation"] = {k: v for k, v in sync.items() if k != "selected_observations"}
    missing_required = [
        s["station_code"]
        for s in sync["stations"]
        if s["state"] == "missing"
        and next(p for p in payload["stations"] if p["code"] == s["station_code"]).get("required", True)
    ]
    if missing_required and not run_cfg.get("allow_missing_required", False):
        return _finish(
            db, processing, version, slot_iso, trigger, persist, started, diagnostics,
            status="failed", failure=f"Required station(s) without usable cycle: {', '.join(missing_required)}",
        )

    # 2 — Corrections (prism then atmosphere, exactly once, fully traced).
    raw_by_id = {raw.id: (raw, sensor) for raw, sensor in raw_rows}
    target_cfg = {(t["station_code"], t["sensor_id"]): t for t in payload["targets"]}
    env_by_station: dict[str, list[dict[str, Any]]] = {}
    for reading in db.execute(
        select(models.EnvironmentReading).where(models.EnvironmentReading.station_code.in_(station_codes))
    ).scalars():
        env_by_station.setdefault(reading.station_code, []).append(
            {"epoch": reading.epoch, "temperature_c": reading.temperature_c, "pressure_hpa": reading.pressure_hpa}
        )

    sights: list[dict[str, Any]] = []
    correction_traces: list[dict[str, Any]] = []
    provisional_reasons: list[str] = []
    for selected in sync["selected_observations"]:
        found = raw_by_id.get(selected["observation_id"])
        if found is None:
            continue
        raw, sensor = found
        cfg = target_cfg.get((raw.station_code, raw.sensor_id))
        if cfg is None or cfg.get("excluded"):
            continue
        measurement = {
            "measurement_type": cfg["measurement"]["type"],
            "required_constant_m": cfg["measurement"].get("required_constant_m", 0.0),
            "already_applied_constant_m": cfg["measurement"].get("already_applied_constant_m", 0.0),
        }
        trace = apply_distance_corrections(
            {"slope_distance_m": raw.sd_m, "epoch": raw.epoch},
            measurement,
            corr_cfg,
            env_by_station.get(raw.station_code, []),
        )
        if trace["blocking"]:
            provisional_reasons.append(f"atmospheric correction blocked for {sensor.raw_name}")
            continue
        if trace["provisional"]:
            provisional_reasons.append(
                f"atmospheric fallback ({trace['atmospheric_source']}) on {raw.station_code}"
            )
        correction_traces.append(
            {
                "observation_id": raw.id,
                "station_code": raw.station_code,
                "target_name": sensor.raw_name,
                "physical_point_id": cfg["physical_point_id"],
                **trace,
            }
        )
        sights.append(
            {
                "id": raw.id,
                "station_id": raw.station_code,
                "target_id": cfg["physical_point_id"],
                "hz_rad": raw.hz_rad,
                "vz_rad": raw.vz_rad,
                "slope_distance_m": trace["final_slope_distance_m"],
                "instrument_height_m": payload_stations(payload)[raw.station_code].get("instrument_height_m", 0.0),
                "target_height_m": sensor.target_height_m,
                "direction_arcsec": cfg["weights"].get("direction_arcsec"),
                "zenith_arcsec": cfg["weights"].get("zenith_arcsec"),
                "distance_mm": cfg["weights"].get("distance_mm"),
                "distance_ppm": cfg["weights"].get("distance_ppm"),
            }
        )
    diagnostics["corrections"] = {
        "count": len(correction_traces),
        "formula_id": corr_cfg.get("formula_id", "standard-dry-air-ppm-v1"),
        "mode": corr_cfg.get("mode"),
        "traces": correction_traces,
    }
    if not sights:
        return _finish(
            db, processing, version, slot_iso, trigger, persist, started, diagnostics,
            status="failed", failure="No usable observation after corrections",
        )

    # 3 — Points, constraints, initials.
    init = initials_for(db, version) if persist or version.id is not None else compute_initials(db, payload)
    initials = {key: tuple(value) for key, value in init["initials"].items()}
    points: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for station in payload["stations"]:
        coords = station.get("coordinates", {})
        initial = initials.get(station["code"]) or (coords.get("e"), coords.get("n"), coords.get("h"))
        if initial is None or initial[0] is None:
            return _finish(
                db, processing, version, slot_iso, trigger, persist, started, diagnostics,
                status="failed", failure=f"Station {station['code']} has no initial coordinates",
            )
        points.append({"id": station["code"], "e": initial[0], "n": initial[1], "h": initial[2], "role": "station", "free": coords.get("mode") != "fixed"})
        if coords.get("mode") in {"fixed", "weak"}:
            sigma = float(coords.get("sigma_m", 0.1 if coords.get("mode") == "weak" else 1e-5))
            for axis, value in zip(("e", "n", "h"), initial):
                constraints.append(
                    {"point_id": station["code"], "component": axis, "value": float(value), "sigma": sigma if coords.get("mode") == "weak" else 1e-5}
                )
    for point in payload["physical_points"]:
        known = point.get("known")
        initial = initials.get(point["id"])
        if initial is None:
            diagnostics["steps"].append(f"no initial coordinate for {point['id']} — skipped")
            continue
        points.append({"id": point["id"], "e": initial[0], "n": initial[1], "h": initial[2], "role": point.get("role", "monitoring"), "free": known is None})
        if known is not None:
            constraint = point.get("constraint", {"e": "weak", "n": "weak", "h": "weak"})
            sigma = point.get("sigma_m", {})
            for axis in ("e", "n", "h"):
                mode = constraint.get(axis, "weak")
                if mode == "free":
                    continue
                constraints.append(
                    {
                        "point_id": point["id"],
                        "component": axis,
                        "value": float(known[axis]),
                        "sigma": 1e-5 if mode == "fixed" else float(sigma.get(axis, 0.002)),
                    }
                )

    default_weights = payload.get("default_weights", {"direction_arcsec": 1.5, "zenith_arcsec": 2.0, "distance_mm": 1.0, "distance_ppm": 1.0})
    observations = prepare_scalar_observations(sights, default_weights)
    excluded_ids = set((overrides or {}).get("excluded_observation_ids", []))
    if excluded_ids:
        for observation in observations:
            if observation["raw_observation_id"] in excluded_ids:
                observation["excluded"] = True

    # 4 — STAR*NET artifacts (what the Windows worker will receive).
    dat_content, engine_names = starnet.build_dat(
        points=[{**p, "constraint": _constraint_of(p, payload), "sigma_m": _sigma_of(p, payload)} for p in points],
        sights=[
            {
                **sight,
                "sigmas": {
                    "direction_rad": math.radians((sight.get("direction_arcsec") or default_weights["direction_arcsec"]) / 3600.0),
                    "zenith_rad": math.radians((sight.get("zenith_arcsec") or default_weights["zenith_arcsec"]) / 3600.0),
                    "distance_m": (sight.get("distance_mm") or default_weights["distance_mm"]) / 1000.0,
                },
            }
            for sight in sights
        ],
        comment=f"{processing.name} — slot {slot_iso}",
    )
    prj_content = starnet.build_prj(adjustment=adj_cfg, run_label=f"BTM_{processing.id}_{slot_iso[:16]}")

    # 5 — Adjustment (auto-adjust never runs when chi² is not interpretable).
    options = {
        "chi_square_significance": float(adj_cfg.get("chi_square_significance", 0.05)),
        "confidence_level": float(adj_cfg.get("confidence_level", 0.95)),
        "convergence_threshold_m": float(adj_cfg.get("convergence_threshold_m", 1e-6)),
        "max_iterations": int(adj_cfg.get("max_iterations", 20)),
        "error_propagation": bool(adj_cfg.get("error_propagation", True)),
    }
    adjust_payload = {"points": points, "observations": observations, "constraints": constraints, "options": options}
    auto_cfg = adj_cfg.get("auto_adjust", {})
    result = auto_adjust(adjust_payload, auto_cfg) if auto_cfg.get("enabled") else adjust_network(adjust_payload)

    # 6 — Round-trip through the native-file contract (.pts / .err parsed back).
    pts_content = "\n".join(
        f"{engine_names.get(p['id'], p['id'])} {p['e']:.4f} {p['n']:.4f} {p['h']:.4f} "
        f"{p['sigma_e']:.4f} {p['sigma_n']:.4f} {p['sigma_h']:.4f}"
        for p in result.get("points", [])
    ) + "\n"
    err_content = "\n".join(
        [
            f"CONVERGED {'YES' if result.get('converged') else 'NO'}",
            f"ITERATIONS {result.get('iterations', 0)}",
            f"CHI2_STATUS {result.get('chi_square_status', 'not-applicable')}",
            f"RANK {result.get('rank', 0)}",
            f"RANK_DEFICIENCY {result.get('rank_deficiency', 0)}",
        ]
    ) + "\n" + (f"VARIANCE_FACTOR {result['variance_factor']:.6f}\n" if math.isfinite(result.get("variance_factor", float("nan"))) else "")
    ingested_points = starnet.parse_pts(pts_content)
    ingested_summary = starnet.parse_err(err_content)

    starnet_artifacts = {
        "dat": dat_content,
        "prj": prj_content,
        "pts": pts_content,
        "err": err_content,
        "engine_names": engine_names,
        "ingested_point_count": len(ingested_points),
        "ingested_summary": ingested_summary,
    }

    chi_status = result.get("chi_square_status", "not-applicable")
    if not result.get("ok"):
        status = "failed"
    elif chi_status == "failed":
        status = "failed"
    elif provisional_reasons or any(s["state"] == "reused" for s in sync["stations"]) or any(
        s["state"] == "missing" for s in sync["stations"]
    ):
        status = "provisional"
    else:
        status = "success"
    if provisional_reasons:
        diagnostics["provisional_reasons"] = sorted(set(provisional_reasons))
    diagnostics["initialisation"] = {
        "coverage": init.get("coverage"),
        "station_solutions": init.get("station_solutions"),
        "failures": init.get("failures"),
    }

    return _finish(
        db, processing, version, slot_iso, trigger, persist, started, diagnostics,
        status=status, result=result, initials=initials, starnet=starnet_artifacts,
        grid_minutes=int(output_cfg.get("grid_minutes", 30)),
    )


def _finish(
    db: Session,
    processing: models.Processing,
    version: models.ConfigVersion,
    slot_iso: str,
    trigger: str,
    persist: bool,
    started: float,
    diagnostics: dict[str, Any],
    *,
    status: str,
    result: dict[str, Any] | None = None,
    initials: dict[str, tuple[float, float, float]] | None = None,
    starnet: dict[str, Any] | None = None,
    failure: str | None = None,
    grid_minutes: int = 30,
) -> dict[str, Any]:
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = result or {}
    if failure:
        diagnostics["failure"] = failure
    run_payload = {
        "processing_id": processing.id,
        "version_id": version.id,
        "slot": slot_iso,
        "trigger": trigger,
        "status": status,
        "chi_square_status": result.get("chi_square_status", "not-applicable"),
        "engine": ENGINE_ID,
        "result": _public_result(result, initials),
        "diagnostics": diagnostics,
        "starnet": starnet or {},
        "duration_ms": duration_ms,
    }
    if not persist:
        run_payload["id"] = None
        return run_payload

    run = models.Run(**run_payload)
    db.add(run)
    db.flush()
    if status in {"success", "provisional"} and result.get("points"):
        publish_outputs(db, processing, run, result, initials or {}, slot_iso)
    db.add(
        models.AuditEvent(
            processing_id=processing.id,
            kind="run",
            message=f"Run {trigger} slot {slot_iso}: {status} (chi² {run_payload['chi_square_status']})",
            payload={"run_id": run.id, "status": status, "duration_ms": duration_ms},
        )
    )
    db.commit()
    run_payload["id"] = run.id
    run_payload["created_at"] = run.created_at
    return run_payload


def publish_outputs(
    db: Session,
    processing: models.Processing,
    run: models.Run,
    result: dict[str, Any],
    initials: dict[str, tuple[float, float, float]],
    slot_iso: str,
) -> None:
    """Replace the value of the same variable at the same slot — idempotent."""
    for point in result["points"]:
        if point.get("role") == "station":
            continue
        initial = initials.get(point["id"], (point["e"], point["n"], point["h"]))
        values = {
            "X": point["e"], "Y": point["n"], "Z": point["h"],
            "DX": point["e"] - initial[0], "DY": point["n"] - initial[1], "DZ": point["h"] - initial[2],
            "SX": point["sigma_e"], "SY": point["sigma_n"], "SZ": point["sigma_h"],
        }
        for component, value in values.items():
            db.execute(
                delete(models.OutputValue).where(
                    models.OutputValue.processing_id == processing.id,
                    models.OutputValue.point_id == point["id"],
                    models.OutputValue.component == component,
                    models.OutputValue.slot == slot_iso,
                )
            )
            db.add(
                models.OutputValue(
                    processing_id=processing.id,
                    point_id=point["id"],
                    component=component,
                    slot=slot_iso,
                    value=float(value),
                    run_id=run.id,
                )
            )


def resolve_version(db: Session, processing_id: int, slot_iso: str) -> models.ConfigVersion | None:
    versions = db.execute(
        select(models.ConfigVersion)
        .where(models.ConfigVersion.processing_id == processing_id)
        .where(models.ConfigVersion.status.in_(["active", "inactive"]))
        .where(models.ConfigVersion.valid_from <= slot_iso)
        .order_by(models.ConfigVersion.valid_from.desc())
    ).scalars().all()
    for version in versions:
        if version.valid_to is None or version.valid_to > slot_iso:
            return version
    return None


def active_version(db: Session, processing_id: int) -> models.ConfigVersion | None:
    return db.execute(
        select(models.ConfigVersion)
        .where(models.ConfigVersion.processing_id == processing_id)
        .where(models.ConfigVersion.status == "active")
    ).scalars().first()


def payload_stations(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["code"]: s for s in payload["stations"]}


def _constraint_of(point: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    for station in payload["stations"]:
        if station["code"] == point["id"]:
            mode = station.get("coordinates", {}).get("mode", "free")
            return {"e": mode, "n": mode, "h": mode}
    for physical in payload["physical_points"]:
        if physical["id"] == point["id"]:
            return physical.get("constraint", {"e": "free", "n": "free", "h": "free"})
    return {"e": "free", "n": "free", "h": "free"}


def _sigma_of(point: dict[str, Any], payload: dict[str, Any]) -> dict[str, float]:
    for station in payload["stations"]:
        if station["code"] == point["id"]:
            sigma = float(station.get("coordinates", {}).get("sigma_m", 0.1))
            return {"e": sigma, "n": sigma, "h": sigma}
    for physical in payload["physical_points"]:
        if physical["id"] == point["id"]:
            return physical.get("sigma_m", {})
    return {}


def _apply_overrides(payload: dict[str, Any], overrides: dict[str, Any]) -> None:
    if "adjustment" in overrides:
        payload["adjustment"].update(overrides["adjustment"])
    if "corrections" in overrides:
        payload.setdefault("corrections", {}).setdefault("atmospheric", {}).update(overrides["corrections"])
    for target_patch in overrides.get("target_weights", []):
        for target in payload["targets"]:
            if target["station_code"] == target_patch["station_code"] and target["sensor_id"] == target_patch["sensor_id"]:
                target["weights"].update(target_patch.get("weights", {}))
    if "default_weights" in overrides:
        payload["default_weights"].update(overrides["default_weights"])


def _public_result(result: dict[str, Any], initials: dict[str, tuple[float, float, float]] | None) -> dict[str, Any]:
    if not result:
        return {}
    public = dict(result)
    if initials:
        for point in public.get("points", []):
            initial = initials.get(point["id"])
            if initial is not None:
                point["initial_e"], point["initial_n"], point["initial_h"] = initial
                point["delta_e"] = point["e"] - initial[0]
                point["delta_n"] = point["n"] - initial[1]
                point["delta_h"] = point["h"] - initial[2]
    return public
