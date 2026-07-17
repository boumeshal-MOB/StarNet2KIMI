from __future__ import annotations

from app.services.starnet import parse_dat
from lambda_app.native_outputs import parse_native_outputs


def test_err_explicit_non_convergence_overrides_lst_iterations():
    result = parse_native_outputs(
        {
            "pts": "P1 10.0000 20.0000 5.0000\n",
            "err": "CONVERGED NO\nITERATIONS 4\n",
            "lst": """
MicroSurvey STAR*NET-PRO Version 6.0.43
Adjustment Statistical Summary
Iterations = 4
The Chi-Square Test at 5.00% Level Passed

Adjusted Coordinates (Meters)
Station E N Elev
P1 10.0000 20.0000 5.0000
""",
            "engine_names": {"POINT-1": "P1"},
        }
    )

    assert result["summary"]["converged"] is False
    assert result["summary"]["iterations"] == 4
    assert result["points"][0]["physical_point_id"] == "POINT-1"


def test_legacy_btm_dat_with_weights_keeps_distance_and_zenith_order():
    parsed = parse_dat(
        "DB S1\n"
        "DM P1 45.00000 90.00000 123.4567 0.00001000 0.00002000 0.0010 1.500 1.800  # raw:obs-1\n"
        "DE\n"
    )

    observation = parsed["observations"][0]
    assert observation["slope_distance_m"] == 123.4567
    assert observation["zenith_deg"] == 90.0
    assert observation["instrument_height_m"] == 1.5
    assert observation["target_height_m"] == 1.8


def test_legacy_btm_dat_without_weights_is_detected_by_raw_marker():
    parsed = parse_dat(
        "DB S1\n"
        "DM P1 45.00000 90.00000 12.5000 1.500 1.800  # raw:obs-2\n"
        "DE\n"
    )

    observation = parsed["observations"][0]
    assert observation["slope_distance_m"] == 12.5
    assert observation["zenith_deg"] == 90.0


def test_native_numeric_dat_order_is_not_swapped():
    parsed = parse_dat(
        ".SCALE 1.0\n"
        "DB S1\n"
        "DM P1 45.00000 12.5000 90.00000 1.500 1.800\n"
        "DE\n"
    )

    observation = parsed["observations"][0]
    assert observation["slope_distance_m"] == 12.5
    assert observation["zenith_deg"] == 90.0
