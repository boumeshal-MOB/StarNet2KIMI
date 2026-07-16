"""Build native STAR*NET `.dat` input records used by the Windows worker."""

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
        return f"{float(sigma_m):.4f}"
    return FREE


def _angle_dms(rad: float) -> str:
    degrees = math.degrees(float(rad)) % 360.0
    whole = int(degrees)
    minutes_total = (degrees - whole) * 60.0
    minutes = int(minutes_total)
    seconds = (minutes_total - minutes) * 60.0
    if seconds >= 59.995:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        whole = (whole + 1) % 360
    return f"{whole:03d}-{minutes:02d}-{seconds:05.2f}"


def build_dat(
    *,
    points: list[dict[str, Any]],
    sights: list[dict[str, Any]],
    comment: str = "",
    scale_factor: float = 1.0,
) -> tuple[str, dict[str, str]]:
    """Return native-style `.dat` content and the physical-point name mapping.

    `DM` follows the real STAR*NET files supplied for validation:
    ``DM target direction distance zenith HI/HT``.
    Per-observation uncertainties remain traceable in comments. The approved
    STAR*NET instrument/project template is responsible for certified weights.
    """
    taken: set[str] = set()
    names = {str(point["id"]): engine_name(str(point["id"]), taken) for point in points}

    lines = [f"# BTM Topographic Adjustment — {comment}".rstrip()]
    lines.append("# Corrected slope distances: prism and atmospheric corrections already applied by BTM.")
    lines.append("# C name E N H sigmaE sigmaN sigmaH   (! fixed, numeric weak, * free)")
    for point in points:
        point_id = str(point["id"])
        constraint = point.get("constraint", {})
        sigmas = point.get("sigma_m", {})
        tokens = [
            _sigma_token(str(constraint.get(axis, "free")), sigmas.get(axis))
            for axis in ("e", "n", "h")
        ]
        lines.append(
            f"C   {names[point_id]}   {float(point['e']):.5f}   {float(point['n']):.5f}   "
            f"{float(point['h']):.5f}   {tokens[0]}   {tokens[1]}   {tokens[2]}"
        )

    lines.extend(["", f".SCALE {float(scale_factor):.12f}", ""])
    by_station: dict[str, list[dict[str, Any]]] = {}
    for sight in sights:
        by_station.setdefault(str(sight["station_id"]), []).append(sight)

    for station_id, station_sights in by_station.items():
        lines.append(f"DB {names.get(station_id, station_id)}")
        for sight in station_sights:
            target = names.get(str(sight["target_id"]), str(sight["target_id"]))
            sigmas = sight.get("sigmas", {})
            if sigmas:
                lines.append(
                    "# BTM_WEIGHT "
                    f"raw={sight.get('raw_observation_id', sight.get('id', ''))} "
                    f"direction_rad={float(sigmas.get('direction_rad', 0.0)):.12g} "
                    f"zenith_rad={float(sigmas.get('zenith_rad', 0.0)):.12g} "
                    f"distance_m={float(sigmas.get('distance_m', 0.0)):.12g}"
                )
            hi = float(sight.get("instrument_height_m", 0.0))
            ht = float(sight.get("target_height_m", 0.0))
            lines.append(
                f"DM  {target:<24} {_angle_dms(float(sight['hz_rad']))}  "
                f"{float(sight['slope_distance_m']):.5f}  "
                f"{_angle_dms(float(sight['vz_rad']))}  {hi:.3f}/{ht:.3f}"
            )
        lines.extend(["DE", ""])

    return "\n".join(lines).rstrip() + "\n", names
