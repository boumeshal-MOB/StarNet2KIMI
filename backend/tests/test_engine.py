"""Engine pipeline tests against the seeded demo world."""

from __future__ import annotations

from sqlalchemy import select

from app import models
from app.seed import deliver_late_data
from app.services import engine as eng


def _network(db):
    return db.execute(select(models.Processing).where(models.Processing.kind == "network")).scalars().first()


def test_network_adjustment_passes_and_recovers_ats35(db):
    processing = _network(db)
    result = eng.run_pipeline(db, processing, processing.versions[0], "2025-03-09T00:00:00.000Z", trigger="manual")
    assert result["status"] == "success"
    assert result["chi_square_status"] == "passed"
    points = {p["id"]: p for p in result["result"]["points"]}
    ats35 = points["NTE_ATS35"]
    # Recovered through shared REFs only — truth is 280498 / 288548 / 32.1.
    assert abs(ats35["e"] - 280498.0) < 0.005
    assert abs(ats35["n"] - 288548.0) < 0.005
    assert abs(ats35["h"] - 32.1) < 0.005
    mpo = points["PP_L35MPO101_401"]
    assert (mpo["e"] - 280490.0) ** 2 + (mpo["n"] - 288590.0) ** 2 < 0.005**2
    orientations = {o["station_id"]: o for o in result["result"]["orientations"]}
    assert abs(orientations["NTE_ATS35"]["value_rad"] - 0.35) < 0.001


def test_missing_station_marks_provisional(db):
    processing = _network(db)
    # ATS35 08:26 cycle is held back by the seed.
    result = eng.run_pipeline(db, processing, processing.versions[0], "2025-03-09T08:00:00.000Z", trigger="manual")
    assert result["status"] == "provisional"
    stations = {s["station_code"]: s for s in result["diagnostics"]["synchronisation"]["stations"]}
    assert stations["NTE_ATS35"]["state"] == "reused"


def test_late_delivery_catch_up_replaces_outputs(db):
    processing = _network(db)
    version = processing.versions[0]
    before = eng.run_pipeline(db, processing, version, "2025-03-09T08:00:00.000Z", trigger="manual")
    assert before["status"] == "provisional"
    outcome = deliver_late_data(db)
    assert outcome["delivered"] is True
    after = eng.run_pipeline(db, processing, version, "2025-03-09T08:00:00.000Z", trigger="catch-up")
    assert after["status"] == "success"
    # Same slot values are replaced, not duplicated.
    rows = db.execute(
        select(models.OutputValue).where(
            models.OutputValue.processing_id == processing.id,
            models.OutputValue.slot == "2025-03-09T08:00:00.000Z",
            models.OutputValue.component == "DZ",
        )
    ).scalars().all()
    point_ids = [row.point_id for row in rows]
    assert len(point_ids) == len(set(point_ids))


def test_blunder_triggers_auto_adjust(db):
    processing = _network(db)
    result = eng.run_pipeline(db, processing, processing.versions[0], "2025-03-09T16:00:00.000Z", trigger="manual")
    attempts = result["result"].get("auto_adjust_attempts", [])
    assert attempts, "auto-adjust should have excluded the +8 mm blunder"
    excluded = {a["excluded_scalar_observation_id"] for a in attempts}
    assert any("L35RE1100_341" in item for item in excluded)
    assert result["chi_square_status"] == "passed"


def test_corrections_applied_once_and_traced(db):
    processing = _network(db)
    result = eng.run_pipeline(db, processing, processing.versions[0], "2025-03-09T00:00:00.000Z", trigger="manual")
    traces = result["diagnostics"]["corrections"]["traces"]
    assert traces
    for trace in traces:
        assert trace["formula_id"] == "standard-dry-air-ppm-v1"
        # prism delta is exactly required - applied, never zero for UK prisms
        if "L35MPO104_404" not in trace["target_name"]:
            assert abs(trace["prism_delta_m"] - 0.0089) < 1e-9
        expected = (trace["stored_slope_distance_m"] + trace["prism_delta_m"]) * trace["atmospheric_scale"]
        assert abs(trace["final_slope_distance_m"] - expected) < 1e-9


def test_starnet_artifacts_round_trip(db):
    processing = _network(db)
    result = eng.run_pipeline(db, processing, processing.versions[0], "2025-03-09T00:00:00.000Z", trigger="manual")
    artifacts = result["starnet"]
    assert "DB NTE_ATS34" in artifacts["dat"]
    assert "DB NTE_ATS35" in artifacts["dat"]
    assert "SCALE_FACTOR 1.0" in artifacts["prj"]
    assert artifacts["ingested_point_count"] == len(result["result"]["points"])
    assert artifacts["ingested_summary"]["converged"] is True
    assert artifacts["ingested_summary"]["chi_square_status"] == "passed"
    # one engine name per physical point, shared across stations
    assert artifacts["engine_names"]["REF_329"] == "REF_329"
