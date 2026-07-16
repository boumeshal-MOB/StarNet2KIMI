"""STAR*NET package contract tests."""

from __future__ import annotations

import math

import pytest

from app.services.starnet import build_dat, build_prj, engine_name, parse_err, parse_pts


def test_engine_names_valid_unique_and_stable():
    taken = set()
    names = [engine_name(raw, taken) for raw in ["REF-329", "REF 329", "MPO/001 long-name-extra", ""]]
    assert len(set(names)) == 4
    for name in names:
        assert 1 <= len(name) <= 15
        assert all(c.isalnum() or c == "_" for c in name)
    assert engine_name("REF_329") == "REF_329"


def test_build_dat_constraints_and_blocks():
    dat, names = build_dat(
        points=[
            {"id": "ST1", "e": 0.0, "n": 0.0, "h": 0.0, "constraint": {"e": "fixed", "n": "fixed", "h": "fixed"}},
            {"id": "REF1", "e": 10.0, "n": 0.0, "h": 1.0, "constraint": {"e": "weak", "n": "weak", "h": "weak"}, "sigma_m": {"e": 0.002, "n": 0.002, "h": 0.002}},
        ],
        sights=[
            {"station_id": "ST1", "target_id": "REF1", "hz_rad": math.pi / 2, "vz_rad": math.pi / 2, "slope_distance_m": 10.0, "raw_observation_id": "o1"},
        ],
    )
    assert "C ST1 0.0000 0.0000 0.0000 ! ! !" in dat
    assert "C REF1 10.0000 0.0000 1.0000 0.0020 0.0020 0.0020" in dat
    assert "DB ST1" in dat and "DM REF1" in dat and dat.rstrip().endswith("DE")
    assert names == {"ST1": "ST1", "REF1": "REF1"}


def test_parse_pts_and_err():
    pts = parse_pts("# comment\nREF_329 280558.5586 288493.5581 30.7208 0.0012 0.0011 0.0019\n")
    assert pts[0]["name"] == "REF_329"
    assert pts[0]["sigma_h"] == pytest.approx(0.0019)
    with pytest.raises(ValueError):
        parse_pts("only three fields here\n")
    summary = parse_err("CONVERGED YES\nITERATIONS 3\nCHI2_STATUS not-applicable\nWARNING rank watch\n")
    assert summary["converged"] is True
    assert summary["chi_square_status"] == "not-applicable"
    assert summary["warnings"] == ["rank watch"]
    with pytest.raises(ValueError):
        parse_err("CHI2_STATUS maybe\n")


def test_build_prj_separates_corrections():
    prj = build_prj(adjustment={"dimension": "3D", "auto_adjust": {"enabled": True, "max_iterations": 4, "max_standardized_residual": 2.5}}, run_label="X")
    assert "SCALE_FACTOR 1.0" in prj  # never fed by the atmospheric formula
    assert "AUTO_ADJUST ON" in prj
    assert "DIMENSION 3D" in prj
