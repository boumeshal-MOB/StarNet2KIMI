"""Country templates (UK / France) — single source for version payload defaults."""

from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "uk": {
        "label": "UK — Leica (HS2/NTE)",
        "default_weights": {"direction_arcsec": 1.0, "zenith_arcsec": 1.5, "distance_mm": 1.0, "distance_ppm": 1.0},
        "atmospheric": {
            "mode": "cycle-temperature-pressure",
            "tolerance_minutes": 45,
            "missing_policy": "fixed-fallback",
            "fallback_temperature_c": 12.0,
            "fallback_pressure_hpa": 1013.25,
            "mark_provisional": True,
        },
        "prism_examples_m": [0.0, 0.0089, 0.0265, 0.03],
    },
    "fr": {
        "label": "France — Topcon MS AX",
        "default_weights": {"direction_arcsec": 1.5, "zenith_arcsec": 2.0, "distance_mm": 1.0, "distance_ppm": 1.0},
        "atmospheric": {"mode": "already-applied"},
        "prism_examples_m": [0.0, 0.0255],
    },
    "custom": {
        "label": "Personnalisé / Custom",
        "default_weights": {"direction_arcsec": 1.5, "zenith_arcsec": 2.0, "distance_mm": 1.0, "distance_ppm": 1.0},
        "atmospheric": {"mode": "fixed-temperature-pressure", "temperature_c": 12.0, "pressure_hpa": 1013.25},
        "prism_examples_m": [0.0],
    },
}

DEFAULT_ADJUSTMENT = {
    "dimension": "3D",
    "units_linear": "M",
    "units_angular": "DEG",
    "system": "LOCAL",
    "coordinate_order": "ENH",
    "convergence_threshold_m": 1e-6,
    "max_iterations": 20,
    "chi_square_significance": 0.05,
    "confidence_level": 0.95,
    "error_propagation": True,
    "refraction_coefficient": 0.14,
    "auto_adjust": {"enabled": True, "max_iterations": 5, "max_standardized_residual": 3.0, "outliers_removed_per_iteration": 1},
}

DEFAULT_RUN = {
    "trigger": "event-driven",
    "cycle_tolerance_minutes": 12,
    "sync_tolerance_minutes": 35,
    "max_epoch_to_slot_minutes": 90,
    "max_reused_age_minutes": 180,
    "allow_future_minutes": 45,
    "allow_reuse_last_cycle": True,
    "missing_station_policy": "provisional",
    "catch_up_on_late_data": True,
}

DEFAULT_OUTPUT = {"grid_minutes": 30}


def measurement_for(template: str, measurement_type: str, prism_constant_m: float) -> dict[str, Any]:
    """Required/applied constants by template — never correct twice."""
    if measurement_type == "reflectorless":
        return {"type": "reflectorless", "required_constant_m": 0.0, "already_applied_constant_m": 0.0, "target_height_m": 0.0}
    if template == "fr":
        applied = 0.0255 if abs(prism_constant_m - 0.0255) < 1e-9 else 0.0
        return {"type": measurement_type, "required_constant_m": applied, "already_applied_constant_m": applied, "target_height_m": 0.0}
    return {"type": measurement_type, "required_constant_m": prism_constant_m, "already_applied_constant_m": 0.0, "target_height_m": 0.0}


def base_payload(template: str, kind: str) -> dict[str, Any]:
    tpl = TEMPLATES[template]
    return {
        "schema": "btm-topographic-adjustment/v1",
        "template": template,
        "kind": kind,
        "stations": [],
        "targets": [],
        "physical_points": [],
        "initialisation": {"method": "local-system", "window_from": None, "window_to": None},
        "corrections": {"atmospheric": dict(tpl["atmospheric"])},
        "adjustment": dict(DEFAULT_ADJUSTMENT),
        "default_weights": dict(tpl["default_weights"]),
        "run": dict(DEFAULT_RUN),
        "output": dict(DEFAULT_OUTPUT),
    }
