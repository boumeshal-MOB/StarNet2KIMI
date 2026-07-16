"""Robust initial-coordinate calculation for one station or a connected network."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from statistics import median
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from .geometry import azimuth, circular_mean, circular_median, normalize_face, polar_to_enh, wrap_pi


def initialise_network(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Initialise coordinates from a representative observation window.

    Physical identity is an explicit input mapping; names are never guessed.  Each
    station/physical-point representative uses circular median Hz and ordinary medians Vz/Sd.
    A fixed anchor can define a local frame.  Remaining stations are resected jointly with
    directions, zeniths and distances, which resolves the mirror ambiguity of distance-only
    two-circle intersections.
    """

    observations = [dict(row) for row in payload.get("observations", [])]
    stations = [dict(row) for row in payload.get("stations", [])]
    known_points = {str(key): tuple(map(float, value)) for key, value in payload.get("known_points", {}).items()}
    expected_pairs = {tuple(item) for item in payload.get("expected_pairs", [])}
    if not observations:
        raise ValueError("The initialisation window contains no observations")
    representatives = _representatives(observations)
    available_pairs = set(representatives)
    expected_pairs = expected_pairs or available_pairs

    station_coordinates: dict[str, tuple[float, float, float]] = {}
    station_approximates: dict[str, tuple[float, float, float]] = {}
    station_orientations: dict[str, float] = {}
    station_diagnostics: dict[str, dict[str, Any]] = {}
    for station in stations:
        station_id = str(station["id"])
        if station.get("fixed_coordinates") is not None:
            station_coordinates[station_id] = tuple(map(float, station["fixed_coordinates"]))
        if station.get("approximate_coordinates") is not None:
            station_approximates[station_id] = tuple(map(float, station["approximate_coordinates"]))
        if station.get("fixed_orientation_rad") is not None:
            station_orientations[station_id] = float(station["fixed_orientation_rad"])
            station_diagnostics[station_id] = {
                "method": "fixed-anchor",
                "tie_count": 0,
                "horizontal_rms_m": 0.0,
                "angular_rms_arcsec": 0.0,
                "warnings": [],
            }

    # Known station coordinates plus known target coordinates determine orientation.
    for station in stations:
        station_id = str(station["id"])
        if station_id in station_orientations or station_id not in station_coordinates:
            continue
        origin = station_coordinates[station_id]
        angles: list[float] = []
        weights: list[float] = []
        ties: list[str] = []
        for (source_station, target_id), observation in representatives.items():
            if source_station != station_id or target_id not in known_points:
                continue
            target = known_points[target_id]
            angles.append(wrap_pi(azimuth(origin[0], origin[1], target[0], target[1]) - observation["hz_rad"]))
            weights.append(max(1.0, observation["slope_distance_m"]))
            ties.append(target_id)
        if angles:
            orientation = circular_mean(angles, weights)
            station_orientations[station_id] = orientation
            deviations = [wrap_pi(value - orientation) for value in angles]
            station_diagnostics[station_id] = {
                "method": "known-reference-orientation",
                "tie_count": len(ties),
                "ties": ties,
                "horizontal_rms_m": 0.0,
                "angular_rms_arcsec": _rms(deviations) * 180.0 * 3600.0 / math.pi,
                "warnings": ["A single reference does not control orientation"] if len(ties) == 1 else [],
            }

    estimates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    radiated: set[str] = set()

    def radiate(station_id: str) -> None:
        if station_id in radiated or station_id not in station_coordinates or station_id not in station_orientations:
            return
        station_row = next(row for row in stations if str(row["id"]) == station_id)
        for (source_station, target_id), observation in representatives.items():
            if source_station != station_id:
                continue
            coordinate = polar_to_enh(
                station_coordinates[station_id],
                observation["slope_distance_m"],
                observation["hz_rad"],
                observation["vz_rad"],
                station_orientations[station_id],
                float(station_row.get("instrument_height_m", 0.0)),
                float(observation.get("target_height_m", 0.0)),
            )
            estimates[target_id].append(
                {
                    "station_id": station_id,
                    "coordinate": coordinate,
                    "source_observation_count": observation["source_count"],
                }
            )
        radiated.add(station_id)

    for station_id in list(station_orientations):
        radiate(station_id)

    # Propagate the datum through explicitly shared physical points.
    for _ in range(len(stations)):
        progressed = False
        coordinate_catalogue = dict(known_points)
        coordinate_catalogue.update(
            {
                point_id: tuple(median(row["coordinate"][axis] for row in rows) for axis in range(3))
                for point_id, rows in estimates.items()
                if rows
            }
        )
        for station in stations:
            station_id = str(station["id"])
            if station_id in station_orientations:
                continue
            ties = [
                {"target_id": target_id, "target": coordinate_catalogue[target_id], **observation}
                for (source_station, target_id), observation in representatives.items()
                if source_station == station_id and target_id in coordinate_catalogue
            ]
            if len(ties) < 2:
                continue
            approximate = station_approximates.get(station_id, (0.0, 0.0, 0.0))
            solution = _resect_station(ties, approximate, float(station.get("instrument_height_m", 0.0)))
            if not solution["ok"]:
                continue
            station_coordinates[station_id] = solution["coordinate"]
            station_orientations[station_id] = solution["orientation_rad"]
            station_diagnostics[station_id] = {
                "method": "network-resection",
                "tie_count": len(ties),
                "ties": [tie["target_id"] for tie in ties],
                "horizontal_rms_m": solution["distance_rms_m"],
                "angular_rms_arcsec": solution["angular_rms_arcsec"],
                "condition_number": solution["condition_number"],
                "warnings": ["Two common points solve the resection but provide weak redundancy; three well-spread points are recommended"]
                if len(ties) == 2
                else [],
            }
            radiate(station_id)
            progressed = True
        if not progressed:
            break

    failures = [
        {
            "station_id": str(station["id"]),
            "reason": "Station cannot be oriented: confirm at least two shared points or provide reference coordinates",
        }
        for station in stations
        if str(station["id"]) not in station_orientations
    ]
    coordinates = []
    for point_id, rows in sorted(estimates.items()):
        if point_id in known_points:
            continue
        centre = tuple(median(row["coordinate"][axis] for row in rows) for axis in range(3))
        horizontal_spread = max(math.hypot(row["coordinate"][0] - centre[0], row["coordinate"][1] - centre[1]) for row in rows)
        vertical_spread = max(abs(row["coordinate"][2] - centre[2]) for row in rows)
        coordinates.append(
            {
                "point_id": point_id,
                "e": centre[0],
                "n": centre[1],
                "h": centre[2],
                "station_count": len({row["station_id"] for row in rows}),
                "source_observation_count": sum(row["source_observation_count"] for row in rows),
                "horizontal_spread_m": horizontal_spread,
                "vertical_spread_m": vertical_spread,
            }
        )
    epochs = sorted(str(row["epoch"]) for row in observations)
    physical_points_expected = {target for _, target in expected_pairs}
    physical_points_available = {target for _, target in available_pairs}
    return {
        "coordinates": coordinates,
        "station_solutions": [
            {
                "station_id": station_id,
                "e": station_coordinates[station_id][0],
                "n": station_coordinates[station_id][1],
                "h": station_coordinates[station_id][2],
                "orientation_rad": station_orientations[station_id],
                **station_diagnostics.get(station_id, {}),
            }
            for station_id in station_orientations
        ],
        "failures": failures,
        "coverage": {
            "window_from": epochs[0],
            "window_to": epochs[-1],
            "aggregation": "component medians over the selected observation window",
            "raw_observation_count": len(observations),
            "representative_count": len(representatives),
            "available_station_target_pairs": len(available_pairs & expected_pairs),
            "expected_station_target_pairs": len(expected_pairs),
            "available_physical_points": len(physical_points_available & physical_points_expected),
            "expected_physical_points": len(physical_points_expected),
            "missing_pairs": sorted([list(pair) for pair in expected_pairs - available_pairs]),
        },
    }


def _representatives(observations: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        hz, vz, _ = normalize_face(float(row["hz_rad"]), float(row["vz_rad"]))
        grouped[(str(row["station_id"]), str(row["physical_point_id"]))].append({**row, "hz_rad": hz, "vz_rad": vz})
    result = {}
    for key, rows in grouped.items():
        result[key] = {
            "hz_rad": circular_median(float(row["hz_rad"]) for row in rows),
            "vz_rad": median(float(row["vz_rad"]) for row in rows),
            "slope_distance_m": median(float(row["slope_distance_m"]) for row in rows),
            "target_height_m": median(float(row.get("target_height_m", 0.0)) for row in rows),
            "source_count": len(rows),
        }
    return result


def _resect_station(
    ties: list[dict[str, Any]], approximate: tuple[float, float, float], instrument_height_m: float
) -> dict[str, Any]:
    orientation_candidates = [
        wrap_pi(azimuth(approximate[0], approximate[1], tie["target"][0], tie["target"][1]) - tie["hz_rad"])
        for tie in ties
    ]
    orientation0 = circular_mean(orientation_candidates)

    def residuals(values: np.ndarray) -> np.ndarray:
        e, n, h, orientation = values
        result: list[float] = []
        for tie in ties:
            target = tie["target"]
            de = target[0] - e
            dn = target[1] - n
            dh = target[2] + float(tie.get("target_height_m", 0.0)) - h - instrument_height_m
            horizontal = math.hypot(de, dn)
            slope = math.hypot(horizontal, dh)
            result.extend(
                [
                    wrap_pi(math.atan2(de, dn) - orientation - tie["hz_rad"]) / math.radians(2.0 / 3600.0),
                    wrap_pi(math.atan2(horizontal, dh) - tie["vz_rad"]) / math.radians(2.0 / 3600.0),
                    (slope - tie["slope_distance_m"]) / 0.002,
                ]
            )
        return np.asarray(result)

    solution = least_squares(
        residuals,
        np.asarray([*approximate, orientation0]),
        x_scale="jac",
        max_nfev=100,
        ftol=1e-12,
        xtol=1e-12,
        gtol=1e-12,
    )
    singular = np.linalg.svd(solution.jac, compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 1e-14 else float("inf")
    raw = residuals(solution.x).reshape((-1, 3))
    return {
        "ok": bool(solution.success and np.linalg.matrix_rank(solution.jac) == 4),
        "coordinate": (float(solution.x[0]), float(solution.x[1]), float(solution.x[2])),
        "orientation_rad": wrap_pi(float(solution.x[3])),
        "distance_rms_m": _rms(raw[:, 2].tolist()) * 0.002,
        "angular_rms_arcsec": _rms(raw[:, :2].flatten().tolist()) * 2.0,
        "condition_number": condition,
    }


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0
