"""STAR*NET-compatible observation standard-error propagation."""

from __future__ import annotations

import math

from .geometry import ARCSEC_TO_RAD


def effective_sigmas(
    *,
    slope_distance_m: float,
    zenith_rad: float,
    direction_arcsec: float,
    zenith_arcsec: float,
    distance_mm: float,
    distance_ppm: float,
    instrument_centering_m: float,
    target_centering_m: float,
    vertical_centering_m: float,
) -> dict[str, float]:
    """Propagate default measurement and centering errors per STAR*NET manual.

    The direction/zenith centering terms are angular (radians).  Distance components remain
    in metres.  Distance constant and ppm terms are root-sum-squared, not linearly added.
    """

    numeric_inputs = {
        "slope_distance_m": slope_distance_m,
        "zenith_rad": zenith_rad,
        "direction_arcsec": direction_arcsec,
        "zenith_arcsec": zenith_arcsec,
        "distance_mm": distance_mm,
        "distance_ppm": distance_ppm,
        "instrument_centering_m": instrument_centering_m,
        "target_centering_m": target_centering_m,
        "vertical_centering_m": vertical_centering_m,
    }
    if any(not math.isfinite(value) for value in numeric_inputs.values()):
        raise ValueError("Weight inputs must be finite")
    if slope_distance_m <= 0:
        raise ValueError("Slope distance must be greater than zero")
    for name, value in numeric_inputs.items():
        if name not in {"slope_distance_m", "zenith_rad"} and value < 0:
            raise ValueError(f"{name} must be non-negative")
    horizontal = abs(slope_distance_m * math.sin(zenith_rad))
    vertical = slope_distance_m * math.cos(zenith_rad)
    horizontal = max(horizontal, 1e-9)
    centering2 = instrument_centering_m**2 + target_centering_m**2
    sigma_hz = math.sqrt((direction_arcsec * ARCSEC_TO_RAD) ** 2 + centering2 / horizontal**2)
    sigma_sd_measurement = math.hypot(distance_mm / 1000.0, slope_distance_m * distance_ppm * 1e-6)
    sigma_sd = math.sqrt(
        sigma_sd_measurement**2
        + (horizontal / slope_distance_m) ** 2 * centering2
        + 2.0 * (vertical / slope_distance_m) ** 2 * vertical_centering_m**2
    )
    sigma_vz = math.sqrt(
        (zenith_arcsec * ARCSEC_TO_RAD) ** 2
        + (vertical / slope_distance_m) ** 2 * centering2 / slope_distance_m**2
        + 2.0 * (horizontal / slope_distance_m) ** 2 * vertical_centering_m**2 / slope_distance_m**2
    )
    result = {"hz": sigma_hz, "vz": sigma_vz, "sd": sigma_sd}
    if any(value <= 0 for value in result.values()):
        raise ValueError("Each effective observation sigma must be greater than zero")
    return result
