"""Surveying geometry helpers (azimuth from North, clockwise)."""

from __future__ import annotations

import math
from collections.abc import Iterable

TAU = 2.0 * math.pi
ARCSEC_TO_RAD = math.pi / (180.0 * 3600.0)


def wrap_pi(angle: float) -> float:
    """Return an angle in [-pi, pi)."""

    return (angle + math.pi) % TAU - math.pi


def wrap_two_pi(angle: float) -> float:
    return angle % TAU


def azimuth(e0: float, n0: float, e1: float, n1: float) -> float:
    return wrap_two_pi(math.atan2(e1 - e0, n1 - n0))


def circular_mean(values: Iterable[float], weights: Iterable[float] | None = None) -> float:
    angles = list(values)
    if not angles:
        raise ValueError("A circular mean requires at least one angle")
    factors = list(weights) if weights is not None else [1.0] * len(angles)
    if len(factors) != len(angles):
        raise ValueError("Angle and weight counts differ")
    sine = sum(weight * math.sin(angle) for angle, weight in zip(angles, factors, strict=True))
    cosine = sum(weight * math.cos(angle) for angle, weight in zip(angles, factors, strict=True))
    if math.hypot(sine, cosine) < 1e-15:
        raise ValueError("Circular mean is undefined for antipodal directions")
    return math.atan2(sine, cosine)


def circular_median(values: Iterable[float]) -> float:
    angles = list(values)
    centre = circular_mean(angles)
    unwrapped = sorted(centre + wrap_pi(value - centre) for value in angles)
    middle = len(unwrapped) // 2
    if len(unwrapped) % 2:
        return wrap_two_pi(unwrapped[middle])
    return wrap_two_pi((unwrapped[middle - 1] + unwrapped[middle]) / 2.0)


def normalize_face(hz_rad: float, vz_rad: float) -> tuple[float, float, bool]:
    """Normalize face II to face I, matching STAR*NET ``.NORMALIZE ON`` semantics.

    A face-II zenith observation is in (pi, 2*pi).  Its equivalent face-I reading is
    ``hz + pi`` and ``2*pi - vz``.  Invalid zenith angles are rejected explicitly.
    """

    if not math.isfinite(hz_rad) or not math.isfinite(vz_rad):
        raise ValueError("Horizontal and zenith angles must be finite")
    if not 0.0 <= vz_rad <= TAU:
        raise ValueError("Zenith angle must be in [0, 2*pi]")
    hz = wrap_two_pi(hz_rad)
    vz = wrap_two_pi(vz_rad)
    if vz > math.pi:
        return wrap_two_pi(hz + math.pi), TAU - vz, True
    return hz, vz, False


def polar_to_enh(
    station: tuple[float, float, float],
    slope_distance_m: float,
    hz_rad: float,
    vz_rad: float,
    orientation_rad: float,
    instrument_height_m: float = 0.0,
    target_height_m: float = 0.0,
) -> tuple[float, float, float]:
    hz, vz, _ = normalize_face(hz_rad, vz_rad)
    horizontal = slope_distance_m * math.sin(vz)
    delta_h = slope_distance_m * math.cos(vz)
    direction = hz + orientation_rad
    return (
        station[0] + horizontal * math.sin(direction),
        station[1] + horizontal * math.cos(direction),
        station[2] + instrument_height_m + delta_h - target_height_m,
    )
