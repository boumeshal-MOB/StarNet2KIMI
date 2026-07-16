"""Pure topographic processing facade used by the BTM AWS Lambda adapter.

The module contains no database, HTTP or AWS calls. BTM resolves project ids,
configuration versions and raw rows before invoking the Lambda, then persists
the returned run result itself.
"""

from __future__ import annotations

import copy
import math
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from btm_topography import (
    adjust_network,
    apply_distance_corrections,
    auto_adjust,
    initialise_network,
    prepare_scalar_observations,
    select_network_epochs,
)

try:  # Lambda image copies this package to /var/task/starnet.
    from starnet import build_dat, build_prj, parse_err, parse_pts
except ImportError:  # Local FastAPI repository/tests.
    from app.services.starnet import build_dat, build_prj, parse_err, parse_pts

from .contracts import ContractError, require_list, require_mapping

ENGINE_ID = "python-lsq-v1"
SUPPORTED_OPERATIONS = {
    "run-processing",
    "calculate",
    "adjust",
    "auto-adjust",
    "initialise",
    "prepare-sights",
    "correct-distance",
    "synchronise",
    "build-starnet-inputs",
    "parse-starnet-outputs",
}


def execute(operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if operation not in SUPPORTED_OPERATIONS:
        raise ContractError(f"Unsupported operation {operation!r}")
    handlers: dict[str, Callable[[], Any]] = {
        "run-processing": lambda: run_processing(payload),
        "calculate": lambda: calculate(payload),
        "adjust": lambda: adjust_network(payload),
        "auto-adjust": lambda: auto_adjust(payload, payload.get("auto_adjust", {})),
        "initialise": lambda: initialise_network(payload),
        "prepare-sights": lambda: {
            "observations": prepare_scalar_observations(payload["sights"], payload["default_weights"])
        },
        "correct-distance": lambda: apply_distance_corrections(
            payload["observation"],
            payload["measurement"],
            payload["atmospheric_policy"],
            payload.get("environment_readings", []),
        ),
        "synchronise": lambda: select_network_epochs(
            payload["observations"],
            payload["station_codes"],
            payload["slot"],
            cycle_tolerance_minutes=float(payload["cycle_tolerance_minutes"]),
            fresh_tolerance_minutes=float(payload["fresh_tolerance_minutes"]),
            max_reused_age_minutes=float(payload["max_reused_age_minutes"]),
            max_epoch_to_slot_minutes=float(payload["max_epoch_to_slot_minutes"]),
            allow_future_minutes=float(payload.get("allow_future_minutes", 0)),
        ),
        "build-starnet-inputs": lambda: build_starnet_inputs(payload),
        "parse-starnet-outputs": lambda: parse_starnet_outputs(payload),
    }
    return handlers[operation]()


def run_processing(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the complete stateless BTM processing from a resolved snapshot."""
    started = time.perf_counter()
    config = require_mapping(payload.get("config"), "payload.config")
    raw_rows = [
        require_mapping(row, "raw_observations[]")
        for row in require_list(payload.get("raw_observations"), "payload.raw_observations")
    ]
    environment = [
        require_mapping(row, "environment_readings[]")
        for row in payload.get("environment_readings", [])
    ]
    slot_iso = str(payload.get("slot") or "")
    if not slot_iso:
        raise ContractError("payload.slot is required")

    run_cfg = require_mapping(config.get("run", {}), "config.run")
    output_cfg = require_mapping(config.get("output", {}), "config.output")
    adjustment_cfg = require_mapping(config.get("adjustment", {}), "config.adjustment")
    atmospheric_cfg = require_mapping(
        require_mapping(config.get("corrections", {}), "config.corrections").get("atmospheric", {}),
        "config.corrections.atmospheric",
    )
    stations = [
        require_mapping(row, "config.stations[]")
        for row in require_list(config.get("stations"), "config.stations")
    ]
    targets = [
        require_mapping(row, "config.targets[]")
        for row in require_list(config.get("targets"), "config.targets")
    ]
    physical_points = [
        require_mapping(row, "config.physical_points[]")
        for row in require_list(config.get("physical_points"), "config.physical_points")
    ]
    station_codes = [str(row["code"]) for row in stations]
    slot = _instant(slot_iso)
    diagnostics: dict[str, Any] = {"slot": slot_iso, "steps": []}

    allow_future = float(run_cfg.get("allow_future_minutes", 45))
    max_age = float(run_cfg.get("max_epoch_to_slot_minutes", 90))
    window_from = slot - timedelta(minutes=max_age)
    window_to = slot + timedelta(minutes=allow_future)
    eligible = [row for row in raw_rows if window_from <= _instant(str(row["epoch"])) <= window_to]
    sync = select_network_epochs(
        [
            {
                "station_code": str(row["station_code"]),
                "target_name": str(row.get("target_name") or row.get("sensor_name") or row.get("sensor_id")),
                "epoch": str(row["epoch"]),
                "observation_id": row["id"],
            }
            for row in eligible
        ],
        station_codes,
        slot_iso,
        cycle_tolerance_minutes=float(run_cfg.get("cycle_tolerance_minutes", 12)),
        fresh_tolerance_minutes=float(run_cfg.get("sync_tolerance_minutes", 35)),
        max_reused_age_minutes=float(run_cfg.get("max_reused_age_minutes", 180)),
        max_epoch_to_slot_minutes=max_age,
        allow_future_minutes=allow_future,
    )
    diagnostics["synchronisation"] = {
        key: value for key, value in sync.items() if key != "selected_observations"
    }
    station_by_code = {str(row["code"]): row for row in stations}
    missing_required = [
        row["station_code"]
        for row in sync["stations"]
        if row["state"] == "missing"
        and station_by_code[str(row["station_code"])].get("required", True)
    ]
    if missing_required and not run_cfg.get("allow_missing_required", False):
        return _failure_response(
            started,
            diagnostics,
            f"Required station(s) without usable cycle: {', '.join(missing_required)}",
        )

    raw_by_id = {row["id"]: row for row in eligible}
    target_by_key = {
        (str(row["station_code"]), str(row["sensor_id"])): row for row in targets
    }
    env_by_station: dict[str, list[dict[str, Any]]] = {}
    for row in environment:
        env_by_station.setdefault(str(row["station_code"]), []).append(row)

    sights: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    provisional_reasons: list[str] = []
    for selected in sync["selected_observations"]:
        raw = raw_by_id.get(selected["observation_id"])
        if raw is None:
            continue
        target = target_by_key.get((str(raw["station_code"]), str(raw["sensor_id"])))
        if target is None or target.get("excluded"):
            continue
        measurement_cfg = require_mapping(target.get("measurement", {}), "target.measurement")
        measurement = {
            "measurement_type": measurement_cfg.get(
                "type", raw.get("measurement_type", "prism")
            ),
            "required_constant_m": measurement_cfg.get(
                "required_constant_m", raw.get("prism_constant_required_m", 0.0)
            ),
            "already_applied_constant_m": measurement_cfg.get(
                "already_applied_constant_m", raw.get("prism_constant_applied_m", 0.0)
            ),
        }
        trace = apply_distance_corrections(
            {"slope_distance_m": float(raw["sd_m"]), "epoch": str(raw["epoch"])},
            measurement,
            atmospheric_cfg,
            env_by_station.get(str(raw["station_code"]), []),
        )
        if trace["blocking"]:
            provisional_reasons.append(
                f"atmospheric correction blocked for {raw.get('target_name', raw['sensor_id'])}"
            )
            continue
        if trace["provisional"]:
            provisional_reasons.append(
                f"atmospheric fallback ({trace['atmospheric_source']}) on {raw['station_code']}"
            )
        traces.append(
            {
                "observation_id": raw["id"],
                "station_code": raw["station_code"],
                "target_name": raw.get("target_name")
                or raw.get("sensor_name")
                or str(raw["sensor_id"]),
                "physical_point_id": target["physical_point_id"],
                **trace,
            }
        )
        weights = require_mapping(target.get("weights", {}), "target.weights")
        sights.append(
            {
                "id": raw["id"],
                "raw_observation_id": raw["id"],
                "station_id": str(raw["station_code"]),
                "target_id": str(target["physical_point_id"]),
                "hz_rad": float(raw["hz_rad"]),
                "vz_rad": float(raw["vz_rad"]),
                "slope_distance_m": float(trace["final_slope_distance_m"]),
                "instrument_height_m": float(
                    station_by_code[str(raw["station_code"])].get("instrument_height_m", 0.0)
                ),
                "target_height_m": float(
                    raw.get("target_height_m", target.get("target_height_m", 0.0))
                ),
                "direction_arcsec": weights.get("direction_arcsec"),
                "zenith_arcsec": weights.get("zenith_arcsec"),
                "distance_mm": weights.get("distance_mm"),
                "distance_ppm": weights.get("distance_ppm"),
            }
        )
    diagnostics["corrections"] = {
        "count": len(traces),
        "formula_id": atmospheric_cfg.get("formula_id", "standard-dry-air-ppm-v1"),
        "mode": atmospheric_cfg.get("mode"),
        "traces": traces,
    }
    if not sights:
        return _failure_response(started, diagnostics, "No usable observation after corrections")

    initialisation = _compute_initials(config, raw_rows)
    initials = {key: tuple(value) for key, value in initialisation["initials"].items()}
    points, constraints = _build_points_and_constraints(stations, physical_points, initials)
    default_weights = require_mapping(
        config.get(
            "default_weights",
            {
                "direction_arcsec": 1.5,
                "zenith_arcsec": 2.0,
                "distance_mm": 1.0,
                "distance_ppm": 1.0,
            },
        ),
        "config.default_weights",
    )
    calculation_payload = {
        "points": points,
        "sights": sights,
        "constraints": constraints,
        "default_weights": default_weights,
        "adjustment": adjustment_cfg,
        "auto_adjust": adjustment_cfg.get("auto_adjust", {}),
        "starnet": {
            "generate_inputs": True,
            "comment": str(payload.get("processing_name") or "BTM Topographic Adjustment")
            + f" — slot {slot_iso}",
            "run_label": str(
                payload.get("run_label")
                or f"BTM_{payload.get('processing_id', 'processing')}_{slot_iso[:16]}"
            ),
        },
    }
    calculated = calculate(calculation_payload)
    result = calculated["result"]
    chi_status = result.get("chi_square_status", "not-applicable")
    if not result.get("ok") or chi_status == "failed":
        status = "failed"
    elif provisional_reasons or any(
        row["state"] in {"reused", "missing"} for row in sync["stations"]
    ):
        status = "provisional"
    else:
        status = "success"
    if provisional_reasons:
        diagnostics["provisional_reasons"] = sorted(set(provisional_reasons))
    diagnostics["initialisation"] = {
        "coverage": initialisation.get("coverage"),
        "station_solutions": initialisation.get("station_solutions"),
        "failures": initialisation.get("failures"),
    }
    return {
        "engine": ENGINE_ID,
        "status": status,
        "chi_square_status": chi_status,
        "slot": slot_iso,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "result": result,
        "diagnostics": diagnostics,
        "starnet_inputs": calculated.get("starnet_inputs", {}),
        "output_values": build_output_values(result, initials, slot_iso),
        "output_grid_minutes": int(output_cfg.get("grid_minutes", 30)),
    }


def calculate(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Adjust a fully prepared network and always produce future STAR*NET inputs."""
    points = [
        require_mapping(row, "points[]")
        for row in require_list(payload.get("points"), "payload.points")
    ]
    constraints = [require_mapping(row, "constraints[]") for row in payload.get("constraints", [])]
    default_weights = require_mapping(payload.get("default_weights", {}), "payload.default_weights")
    sights = [require_mapping(row, "sights[]") for row in payload.get("sights", [])]
    if payload.get("observations") is not None:
        observations = [
            require_mapping(row, "observations[]")
            for row in require_list(payload["observations"], "payload.observations")
        ]
    else:
        if not sights:
            raise ContractError("payload.sights or payload.observations is required")
        observations = prepare_scalar_observations(sights, default_weights)
    excluded = {str(value) for value in payload.get("excluded_observation_ids", [])}
    if excluded:
        for row in observations:
            if str(row.get("id")) in excluded or str(row.get("raw_observation_id")) in excluded:
                row["excluded"] = True
    adjustment = require_mapping(
        payload.get("adjustment", payload.get("options", {})), "payload.adjustment"
    )
    options = {
        "chi_square_significance": float(adjustment.get("chi_square_significance", 0.05)),
        "confidence_level": float(adjustment.get("confidence_level", 0.95)),
        "convergence_threshold_m": float(adjustment.get("convergence_threshold_m", 1e-6)),
        "max_iterations": int(adjustment.get("max_iterations", 20)),
        "error_propagation": bool(adjustment.get("error_propagation", True)),
        "fixed_orientations_rad": adjustment.get("fixed_orientations_rad", {}),
    }
    adjust_payload = {
        "points": points,
        "observations": observations,
        "constraints": constraints,
        "options": options,
    }
    auto_cfg = require_mapping(
        payload.get("auto_adjust", adjustment.get("auto_adjust", {})), "payload.auto_adjust"
    )
    result = auto_adjust(adjust_payload, auto_cfg) if auto_cfg.get("enabled") else adjust_network(adjust_payload)
    response: dict[str, Any] = {"engine": ENGINE_ID, "result": result}
    starnet_cfg = require_mapping(payload.get("starnet", {}), "payload.starnet")
    if starnet_cfg.get("generate_inputs", True):
        response["starnet_inputs"] = build_starnet_inputs(
            {
                "points": points,
                "sights": sights,
                "constraints": constraints,
                "default_weights": default_weights,
                "adjustment": adjustment,
                **starnet_cfg,
            }
        )
    return response


def build_starnet_inputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    points = [
        copy.deepcopy(require_mapping(row, "points[]"))
        for row in require_list(payload.get("points"), "payload.points")
    ]
    sights = [
        copy.deepcopy(require_mapping(row, "sights[]"))
        for row in require_list(payload.get("sights"), "payload.sights")
    ]
    constraints = [require_mapping(row, "constraints[]") for row in payload.get("constraints", [])]
    default_weights = require_mapping(payload.get("default_weights", {}), "payload.default_weights")
    by_point: dict[str, dict[str, dict[str, Any]]] = {}
    for row in constraints:
        by_point.setdefault(str(row["point_id"]), {})[str(row["component"])] = row
    for point in points:
        point_id = str(point["id"])
        point.setdefault("constraint", {})
        point.setdefault("sigma_m", {})
        for axis in ("e", "n", "h"):
            if axis in point["constraint"]:
                continue
            row = by_point.get(point_id, {}).get(axis)
            if row is None:
                point["constraint"][axis] = "free"
            else:
                sigma = float(row["sigma"])
                point["constraint"][axis] = "fixed" if sigma <= 1e-4 else "weak"
                point["sigma_m"][axis] = sigma
    for sight in sights:
        if "sigmas" in sight:
            continue
        sight["sigmas"] = {
            "direction_rad": math.radians(
                float(sight.get("direction_arcsec") or default_weights.get("direction_arcsec", 1.5))
                / 3600.0
            ),
            "zenith_rad": math.radians(
                float(sight.get("zenith_arcsec") or default_weights.get("zenith_arcsec", 2.0))
                / 3600.0
            ),
            "distance_m": float(
                sight.get("distance_mm") or default_weights.get("distance_mm", 1.0)
            )
            / 1000.0,
        }
    dat_content, engine_names = build_dat(
        points=points, sights=sights, comment=str(payload.get("comment", ""))
    )
    prj_content = build_prj(
        adjustment=require_mapping(payload.get("adjustment", {}), "payload.adjustment"),
        run_label=str(payload.get("run_label", "BTM_TOPOGRAPHIC_ADJUSTMENT")),
    )
    return {
        "dat": dat_content,
        "prj": prj_content,
        "engine_names": engine_names,
        "files": ["input.dat", "project.prj"],
    }


def parse_starnet_outputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    pts = payload.get("pts")
    err = payload.get("err")
    if not isinstance(pts, str) or not isinstance(err, str):
        raise ContractError("payload.pts and payload.err must be strings")
    points = parse_pts(pts)
    summary = parse_err(err)
    names = require_mapping(payload.get("engine_names", {}), "payload.engine_names")
    inverse = {str(engine_name): str(point_id) for point_id, engine_name in names.items()}
    for point in points:
        point["physical_point_id"] = inverse.get(str(point["name"]))
    return {
        "points": points,
        "summary": summary,
        "lst_present": isinstance(payload.get("lst"), str) and bool(payload.get("lst")),
    }


def build_output_values(
    result: Mapping[str, Any],
    initials: Mapping[str, tuple[float, float, float]],
    slot_iso: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in result.get("points", []):
        if point.get("role") == "station":
            continue
        initial = initials.get(
            str(point["id"]),
            (float(point["e"]), float(point["n"]), float(point["h"])),
        )
        values = {
            "X": point["e"],
            "Y": point["n"],
            "Z": point["h"],
            "DX": float(point["e"]) - initial[0],
            "DY": float(point["n"]) - initial[1],
            "DZ": float(point["h"]) - initial[2],
            "SX": point["sigma_e"],
            "SY": point["sigma_n"],
            "SZ": point["sigma_h"],
        }
        for component, value in values.items():
            rows.append(
                {
                    "point_id": str(point["id"]),
                    "component": component,
                    "slot": slot_iso,
                    "value": float(value),
                }
            )
    return rows


def _compute_initials(config: Mapping[str, Any], raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    init = require_mapping(config.get("initialisation", {}), "config.initialisation")
    stations = [require_mapping(row, "config.stations[]") for row in config["stations"]]
    targets = [require_mapping(row, "config.targets[]") for row in config["targets"]]
    physical_points = [
        require_mapping(row, "config.physical_points[]") for row in config["physical_points"]
    ]
    known_points = {
        str(row["id"]): (
            float(row["known"]["e"]),
            float(row["known"]["n"]),
            float(row["known"]["h"]),
        )
        for row in physical_points
        if row.get("known")
    }
    window_from = _instant(str(init["window_from"])) if init.get("window_from") else None
    window_to = _instant(str(init["window_to"])) if init.get("window_to") else None
    point_of = {
        (str(row["station_code"]), str(row["sensor_id"])): str(row["physical_point_id"])
        for row in targets
    }
    observations = []
    for raw in raw_rows:
        epoch = _instant(str(raw["epoch"]))
        if window_from and epoch < window_from:
            continue
        if window_to and epoch > window_to:
            continue
        point_id = point_of.get((str(raw["station_code"]), str(raw["sensor_id"])))
        if point_id is None:
            continue
        observations.append(
            {
                "station_id": str(raw["station_code"]),
                "physical_point_id": point_id,
                "epoch": str(raw["epoch"]),
                "hz_rad": float(raw["hz_rad"]),
                "vz_rad": float(raw["vz_rad"]),
                "slope_distance_m": float(raw["sd_m"]),
                "target_height_m": float(raw.get("target_height_m", 0.0)),
            }
        )
    station_payload = []
    for station in stations:
        row: dict[str, Any] = {
            "id": str(station["code"]),
            "instrument_height_m": float(station.get("instrument_height_m", 0.0)),
        }
        coords = require_mapping(station.get("coordinates", {}), "station.coordinates")
        if coords.get("mode") == "fixed":
            row["fixed_coordinates"] = (
                float(coords["e"]),
                float(coords["n"]),
                float(coords["h"]),
            )
            if coords.get("orientation_rad") is not None:
                row["fixed_orientation_rad"] = float(coords["orientation_rad"])
        elif coords.get("e") is not None:
            row["approximate_coordinates"] = (
                float(coords["e"]),
                float(coords["n"]),
                float(coords["h"]),
            )
        station_payload.append(row)
    result = initialise_network(
        {
            "observations": observations,
            "stations": station_payload,
            "known_points": known_points,
            "expected_pairs": [
                (str(row["station_code"]), str(row["physical_point_id"])) for row in targets
            ],
        }
    )
    initials: dict[str, tuple[float, float, float]] = dict(known_points)
    for row in result["coordinates"]:
        initials[str(row["point_id"])] = (
            float(row["e"]),
            float(row["n"]),
            float(row["h"]),
        )
    for row in result["station_solutions"]:
        initials[str(row["station_id"])] = (
            float(row["e"]),
            float(row["n"]),
            float(row["h"]),
        )
    result["initials"] = {key: list(value) for key, value in initials.items()}
    return result


def _build_points_and_constraints(
    stations: list[dict[str, Any]],
    physical_points: list[dict[str, Any]],
    initials: Mapping[str, tuple[float, float, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    points: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for station in stations:
        station_id = str(station["code"])
        coords = require_mapping(station.get("coordinates", {}), "station.coordinates")
        initial = initials.get(station_id) or (coords.get("e"), coords.get("n"), coords.get("h"))
        if initial is None or initial[0] is None:
            raise ContractError(f"Station {station_id} has no initial coordinates")
        points.append(
            {
                "id": station_id,
                "e": float(initial[0]),
                "n": float(initial[1]),
                "h": float(initial[2]),
                "role": "station",
                "free": coords.get("mode") != "fixed",
            }
        )
        if coords.get("mode") in {"fixed", "weak"}:
            sigma = float(
                coords.get("sigma_m", 0.1 if coords.get("mode") == "weak" else 1e-5)
            )
            for axis, value in zip(("e", "n", "h"), initial, strict=True):
                constraints.append(
                    {
                        "point_id": station_id,
                        "component": axis,
                        "value": float(value),
                        "sigma": sigma if coords.get("mode") == "weak" else 1e-5,
                    }
                )
    for point in physical_points:
        point_id = str(point["id"])
        initial = initials.get(point_id)
        if initial is None:
            continue
        known = point.get("known")
        points.append(
            {
                "id": point_id,
                "e": float(initial[0]),
                "n": float(initial[1]),
                "h": float(initial[2]),
                "role": point.get("role", "monitoring"),
                "free": known is None,
            }
        )
        if known is None:
            continue
        modes = require_mapping(
            point.get("constraint", {"e": "weak", "n": "weak", "h": "weak"}),
            "point.constraint",
        )
        sigmas = require_mapping(point.get("sigma_m", {}), "point.sigma_m")
        for axis in ("e", "n", "h"):
            mode = modes.get(axis, "weak")
            if mode == "free":
                continue
            constraints.append(
                {
                    "point_id": point_id,
                    "component": axis,
                    "value": float(known[axis]),
                    "sigma": 1e-5 if mode == "fixed" else float(sigmas.get(axis, 0.002)),
                }
            )
    return points, constraints


def _failure_response(started: float, diagnostics: dict[str, Any], message: str) -> dict[str, Any]:
    diagnostics["failure"] = message
    return {
        "engine": ENGINE_ID,
        "status": "failed",
        "chi_square_status": "not-applicable",
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "result": {},
        "diagnostics": diagnostics,
        "starnet_inputs": {},
        "output_values": [],
    }


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        return instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)
