"""Build the STAR*NET ``.dat`` observation file for one run.

Conventions (spec doc 23):
- ``C name E N H sigmaE sigmaN sigmaH`` — ``!`` fixed, metres weak, ``*`` free ;
- ``DB station`` / ``DM target hz vz sd [sigmaHz sigmaVz sigmaSd] HI HT`` / ``DE`` ;
- every physical point observed from several stations keeps ONE engine name.
"""

from __future__ import annotations

import math
from typing import Any

from .names import engine_name

FIXED = "!"
FREE = "*"


def _sigma_token(mode: str, sigma_m: float | None) -> str:
    if mode == "fixed":
        return FIXED
    if mode == "weak" and sigma_m is not None:
        return f"{sigma_m:.4f}"
    return FREE


def _angle_deg(rad: float) -> str:
    return f"{math.degrees(rad):.5f}"


def build_dat(
    *,
    points: list[dict[str, Any]],
    sights: list[dict[str, Any]],
    comment: str = "",
) -> tuple[str, dict[str, str]]:
    """Return the .dat content and the physical-point → engine-name mapping."""
    taken: set[str] = set()
    names = {point["id"]: engine_name(str(point["id"]), taken) for point in points}

    lines = [f"# BTM Topographic Adjustment — {comment}".rstrip()]
    lines.append("# C name E N H sigmaE sigmaN sigmaH   (! fixed, * free)")
    for point in points:
        constraint = point.get("constraint", {})
        sigmas = point.get("sigma_m", {})
        tokens = [
            _sigma_token(constraint.get(axis, "free"), sigmas.get(axis))
            for axis in ("e", "n", "h")
        ]
        lines.append(
            f"C {names[point['id']]} {point['e']:.4f} {point['n']:.4f} {point['h']:.4f} "
            f"{tokens[0]} {tokens[1]} {tokens[2]}"
        )

    by_station: dict[str, list[dict[str, Any]]] = {}
    for sight in sights:
        by_station.setdefault(str(sight["station_id"]), []).append(sight)

    for station_id, station_sights in by_station.items():
        lines.append(f"DB {names.get(station_id, station_id)}")
        for sight in station_sights:
            target = names.get(str(sight["target_id"]), str(sight["target_id"]))
            weights = sight.get("sigmas", {})
            tokens = []
            if weights:
                tokens = [
                    f"{weights.get('direction_rad', 0.0):.8f}",
                    f"{weights.get('zenith_rad', 0.0):.8f}",
                    f"{weights.get('distance_m', 0.0):.4f}",
                ]
            hi = float(sight.get("instrument_height_m", 0.0))
            ht = float(sight.get("target_height_m", 0.0))
            tail = (" " + " ".join(tokens)) if tokens else ""
            lines.append(
                f"DM {target} {_angle_deg(sight['hz_rad'])} {_angle_deg(sight['vz_rad'])} "
                f"{sight['slope_distance_m']:.4f}{tail} {hi:.3f} {ht:.3f}"
                f"  # raw:{sight.get('raw_observation_id', '')}"
            )
        lines.append("DE")

    return "\n".join(lines) + "\n", names
