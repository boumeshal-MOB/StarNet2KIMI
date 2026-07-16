"""Slope-distance corrections with explicit provenance and no STAR*NET scale confusion."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

ATMOSPHERIC_FORMULA_ID = "standard-dry-air-ppm-v1"
ATMOSPHERIC_FORMULA = "ppm = 281.8 - 0.29065 * P_hPa / (1 + T_C / 273.15)"


def atmospheric_ppm(temperature_c: float, pressure_hpa: float) -> float:
    if not math.isfinite(temperature_c) or not -80 <= temperature_c <= 80:
        raise ValueError("Temperature must be finite and between -80 and 80 degC")
    if not math.isfinite(pressure_hpa) or not 300 <= pressure_hpa <= 1200:
        raise ValueError("Pressure must be finite and between 300 and 1200 hPa")
    return 281.8 - 0.29065 * pressure_hpa / (1.0 + temperature_c / 273.15)


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Observation and environment epochs must include a timezone")
    return parsed


def _nearest_environment(
    readings: Iterable[Mapping[str, Any]], epoch: str, tolerance_minutes: float
) -> tuple[Mapping[str, Any], float] | None:
    source_time = _instant(epoch)
    candidates: list[tuple[float, Mapping[str, Any]]] = []
    for reading in readings:
        try:
            atmospheric_ppm(float(reading["temperature_c"]), float(reading["pressure_hpa"]))
            age = abs((_instant(str(reading["epoch"])) - source_time).total_seconds()) / 60.0
        except (KeyError, TypeError, ValueError):
            continue
        if age <= tolerance_minutes:
            candidates.append((age, reading))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def apply_distance_corrections(
    observation: Mapping[str, Any],
    measurement: Mapping[str, Any],
    atmospheric_policy: Mapping[str, Any],
    environment_readings: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Apply reflector then atmospheric correction exactly once to a slope distance.

    For a prism or sheet the two constants must be explicit.  Reflectorless measurements are
    forced to zero.  This avoids silently treating an unresolved prism constant as 0 mm.
    """

    stored = float(observation["slope_distance_m"])
    if not math.isfinite(stored) or stored <= 0:
        raise ValueError("Stored slope distance must be finite and greater than zero")
    measurement_type = measurement["measurement_type"]
    if measurement_type == "reflectorless":
        prism_delta = 0.0
    elif measurement_type in {"prism", "reflective-sheet"}:
        if measurement.get("required_constant_m") is None or measurement.get("already_applied_constant_m") is None:
            raise ValueError("Reflector constants must be resolved before distance correction")
        required = float(measurement["required_constant_m"])
        already_applied = float(measurement["already_applied_constant_m"])
        if not math.isfinite(required) or not math.isfinite(already_applied):
            raise ValueError("Reflector constants must be finite")
        prism_delta = required - already_applied
    else:
        raise ValueError(f"Unsupported measurement_type {measurement_type!r}")
    after_prism = stored + prism_delta

    mode = atmospheric_policy["mode"]
    temperature = pressure = age = None
    provisional = blocking = False
    warnings: list[str] = []
    source = mode
    if mode in {"already-applied", "none"}:
        ppm = 0.0
    elif mode == "fixed-temperature-pressure":
        temperature = atmospheric_policy.get("temperature_c")
        pressure = atmospheric_policy.get("pressure_hpa")
        ppm, source, provisional, blocking, warnings = _resolve_atmosphere_or_missing(
            temperature, pressure, atmospheric_policy, "fixed values are invalid"
        )
    elif mode == "cycle-temperature-pressure":
        tolerance_minutes = float(atmospheric_policy.get("tolerance_minutes", 0))
        if not math.isfinite(tolerance_minutes) or tolerance_minutes < 0:
            raise ValueError("Atmospheric temporal tolerance must be finite and non-negative")
        found = _nearest_environment(
            environment_readings,
            str(observation["epoch"]),
            tolerance_minutes,
        )
        if found:
            age, reading = found
            temperature = float(reading["temperature_c"])
            pressure = float(reading["pressure_hpa"])
            ppm = atmospheric_ppm(temperature, pressure)
            source = "cycle"
        else:
            ppm, source, provisional, blocking, warnings = _resolve_atmosphere_or_missing(
                None, None, atmospheric_policy, "no valid cycle T/P in tolerance"
            )
    else:
        raise ValueError(f"Unsupported atmospheric mode {mode!r}")

    scale = 1.0 + ppm * 1e-6
    return {
        "stored_slope_distance_m": stored,
        "prism_delta_m": prism_delta,
        "distance_after_prism_m": after_prism,
        "atmospheric_ppm": ppm,
        "atmospheric_scale": scale,
        "temperature_c": temperature,
        "pressure_hpa": pressure,
        "environment_age_minutes": age,
        "atmospheric_source": source,
        "formula_id": ATMOSPHERIC_FORMULA_ID,
        "formula": ATMOSPHERIC_FORMULA,
        "final_slope_distance_m": after_prism * scale,
        "provisional": provisional,
        "blocking": blocking,
        "warnings": warnings,
    }


def _resolve_atmosphere_or_missing(
    temperature: Any, pressure: Any, policy: Mapping[str, Any], reason: str
) -> tuple[float, str, bool, bool, list[str]]:
    try:
        return atmospheric_ppm(float(temperature), float(pressure)), "fixed", False, False, []
    except (TypeError, ValueError):
        pass
    missing = policy.get("missing_policy", "wait-or-fail")
    provisional = bool(policy.get("mark_provisional", True))
    if missing == "fixed-fallback":
        try:
            ppm = atmospheric_ppm(float(policy["fallback_temperature_c"]), float(policy["fallback_pressure_hpa"]))
            return ppm, "fallback-fixed", provisional, False, [reason]
        except (KeyError, TypeError, ValueError):
            return 0.0, "missing-blocking", True, True, [f"{reason}; fallback is invalid"]
    if missing == "continue-without-correction":
        return 0.0, "none", provisional, False, [reason]
    if missing == "assume-already-corrected":
        return 0.0, "assumed-already-corrected", provisional, False, [reason]
    if missing == "wait-or-fail":
        return 0.0, "missing-blocking", True, True, [reason]
    raise ValueError(f"Unsupported missing environment policy {missing!r}")
