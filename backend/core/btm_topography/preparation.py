"""Convert one raw total-station sight into auditable scalar observations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .geometry import normalize_face
from .weights import effective_sigmas


def prepare_scalar_observations(
    sights: Iterable[Mapping[str, Any]], default_weights: Mapping[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for sight in sights:
        hz, vz, face_two = normalize_face(float(sight["hz_rad"]), float(sight["vz_rad"]))
        sigmas = effective_sigmas(
            slope_distance_m=float(sight["slope_distance_m"]),
            zenith_rad=vz,
            direction_arcsec=float(sight.get("direction_arcsec", default_weights["direction_arcsec"])),
            zenith_arcsec=float(sight.get("zenith_arcsec", default_weights["zenith_arcsec"])),
            distance_mm=float(sight.get("distance_mm", default_weights["distance_mm"])),
            distance_ppm=float(sight.get("distance_ppm", default_weights["distance_ppm"])),
            instrument_centering_m=float(default_weights.get("instrument_centering_m", 0)),
            target_centering_m=float(default_weights.get("target_centering_m", 0)),
            vertical_centering_m=float(default_weights.get("vertical_centering_m", 0)),
        )
        base = {
            "raw_observation_id": str(sight["id"]),
            "station_id": str(sight["station_id"]),
            "target_id": str(sight["target_id"]),
            "instrument_height_m": float(sight.get("instrument_height_m", 0)),
            "target_height_m": float(sight.get("target_height_m", 0)),
            "protected": bool(sight.get("protected", False)),
            "face_two_normalized": face_two,
        }
        excluded = set(sight.get("excluded_components", []))
        components = {
            "hz": hz,
            "vz": vz,
            "sd": float(sight["slope_distance_m"]),
        }
        for kind, value in components.items():
            result.append(
                {
                    **base,
                    "id": f"{sight['id']}:{kind}",
                    "kind": kind,
                    "value": value,
                    "sigma": sigmas[kind],
                    "excluded": kind in excluded,
                }
            )
    return result
