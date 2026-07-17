from __future__ import annotations

import math

from app.services.starnet import (
    build_dat,
    build_prj,
    parse_dat,
    parse_err,
    parse_lst,
    parse_project,
    parse_pts,
)


def test_native_pts_four_columns_is_supported():
    points = parse_pts(
        "NTE_ATS34 280483.35735 288515.77163 31.50836\n"
        "TARGET_01 280500.10000 288520.20000 30.40000\n"
    )
    assert len(points) == 2
    assert points[0]["sigma_e"] is None
    assert points[0]["e"] == 280483.35735


def test_native_err_warning_log_is_non_fatal():
    summary = parse_err(
        "MicroSurvey STAR*NET-PRO Error Log\n\n"
        "WARNING Network Has No Fixed XY Stations\n\n"
        "WARNING Network Has No Fixed Z Stations\n\n"
        "Network Processing Completed with 2 Warnings\n"
    )
    assert summary["completed"] is True
    assert summary["converged"] is True
    assert summary["warning_count"] == 2
    assert summary["error_count"] == 0


def test_native_lst_extracts_statistics_coordinates_and_sigmas():
    listing = """
MicroSurvey STAR*NET-PRO Version 6.0.43
Run Date: Tue Apr 29 2025 13:42:48
Project Name       HS2_S1_NTE
Data File List  1. 20250301_160000.dat

Adjustment Statistical Summary
==============================
Iterations              =      2
Number of Stations      =     43
Number of Observations  =    155
Number of Unknowns      =    130
Number of Redundant Obs =     25
Total     155        24.837         0.997
The Chi-Square Test at 5.00% Level Passed
Lower/Upper Bounds (0.724/1.275)

Adjusted Coordinates (Meters)
Station                   E              N          Elev   Description
NTE_ATS34          280483.3574    288515.7716     31.5084

Station Coordinate Standard Deviations (Meters)
Station                     E             N             Elev
NTE_ATS34                 0.000645      0.000579      0.000424

Station Coordinate Error Ellipses (Meters)
Station                 Semi-Major    Semi-Minor   Azimuth of       Elev
NTE_ATS34                 0.001579      0.001416      93-10       0.000831

Adjusted Distance Observations (Meters)
From       To              Distance      Residual   StdErr StdRes
NTE_ATS34  REF_001          24.0652        0.0027   0.0015   1.8
"""
    parsed = parse_lst(listing)
    assert parsed["metadata"]["version"] == "6.0.43"
    assert parsed["summary"]["chi_square_status"] == "passed"
    assert parsed["summary"]["iterations"] == 2
    assert parsed["summary"]["max_standardized_residual"] == 1.8
    assert parsed["points"][0]["sigma_e"] == 0.000645
    assert parsed["points"][0]["error_ellipse"]["semi_major"] == 0.001579


def test_native_prj_and_snproj_sections_are_parsed():
    project = parse_project(
        "*STAR*NET 3\n#\n# 14.0.2.9137\n#\n"
        "[Adjustment]\n"
        "adjustment_type 3D\n"
        "linear_units Meters\n"
        "coordinate_order EN\n"
        "[USER]\nusername\n"
    )
    assert project["format_version"] == 3
    assert project["software_version"] == "14.0.2.9137"
    assert project["sections"]["Adjustment"]["adjustment_type"] == "3D"
    assert project["sections"]["USER"]["username"] == ""


def test_native_dat_direction_distance_zenith_order_is_parsed():
    parsed = parse_dat(
        "C NTE_ATS34 280483.3552 288515.7764 31.5058 0.100 0.100 *\n"
        ".SCALE 0.999991321520396\n"
        "DB NTE_ATS34\n"
        "DM TARGET_01 072-01-12.9 193.6106 089-31-52.3 0/0\n"
        "DE\n"
    )
    assert parsed["scale_factor"] == 0.999991321520396
    observation = parsed["observations"][0]
    assert observation["slope_distance_m"] == 193.6106
    assert abs(observation["direction_rad"] - math.radians(72.02025)) < 1e-12
    assert observation["instrument_height_m"] == 0.0


def test_builders_emit_native_project_and_dat_shapes():
    points = [
        {
            "id": "S1",
            "e": 0.0,
            "n": 0.0,
            "h": 0.0,
            "constraint": {"e": "fixed", "n": "fixed", "h": "fixed"},
            "sigma_m": {},
        },
        {
            "id": "P1",
            "e": 10.0,
            "n": 10.0,
            "h": 1.0,
            "constraint": {"e": "free", "n": "free", "h": "free"},
            "sigma_m": {},
        },
    ]
    sights = [
        {
            "id": "obs-1",
            "station_id": "S1",
            "target_id": "P1",
            "hz_rad": math.radians(72.02025),
            "vz_rad": math.radians(89.53119444444444),
            "slope_distance_m": 193.6106,
            "instrument_height_m": 0.0,
            "target_height_m": 0.0,
        }
    ]
    dat, _ = build_dat(points=points, sights=sights, comment="test")
    assert "DB S1" in dat
    assert "072-01-12.90" in dat
    assert "193.61060  089-31-52.30  0.000/0.000" in dat

    project = build_prj(adjustment={"dimension": "3D"}, run_label="UNIT_TEST")
    assert project.startswith("*STAR*NET 3")
    assert "[Adjustment]" in project
    assert "adjustment_type                3D" in project
    assert "# RUN_LABEL UNIT_TEST" in project
