"""API smoke tests over the seeded demo world."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_api_end_to_end(db):
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"

    boot = client.get("/api/bootstrap").json()
    assert {s["code"] for s in boot["stations"]} == {"NTE_ATS34", "NTE_ATS35"}
    assert len(boot["physical_points"]) >= 47

    processings = client.get("/api/processings").json()
    assert len(processings) == 2
    network = next(p for p in processings if p["kind"] == "network")

    run = client.post(f"/api/processings/{network['id']}/run", json={"slot": "2025-03-09T04:00:00.000Z"}).json()
    assert run["status"] == "success"
    assert run["chi_square_status"] == "passed"

    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["result"]["points"]
    assert detail["starnet"]["dat"]

    trial = client.post(
        "/api/analysis/trial",
        json={"processing_id": network["id"], "slot": "2025-03-09T04:00:00.000Z", "overrides": {"default_weights": {"direction_arcsec": 5.0}}},
    ).json()
    assert trial["id"] is None  # analysis never persists
    assert trial["result"]["points"]

    outputs = client.get(f"/api/processings/{network['id']}/outputs?component=DZ").json()
    assert outputs["series"]

    # connectivity rule: a network without shared points is rejected
    bad = client.post(
        "/api/processings",
        json={
            "name": "broken",
            "kind": "network",
            "template": "uk",
            "payload": {
                "stations": [{"code": "NTE_ATS34"}, {"code": "NTE_ATS35"}],
                "targets": [],
                "physical_points": [],
            },
        },
    )
    assert bad.status_code == 422


def test_version_lifecycle(db):
    client = TestClient(app)
    processing = client.get("/api/processings").json()[0]
    versions = client.get(f"/api/processings/{processing['id']}").json()["versions"]
    active = next(v for v in versions if v["status"] == "active")

    draft = client.post(f"/api/processings/{processing['id']}/versions", json={"from_version_id": active["id"]}).json()
    assert draft["status"] == "draft" and draft["number"] == 2

    activated = client.post(f"/api/processings/{processing['id']}/versions/{draft['id']}/activate", json={}).json()
    assert activated["status"] == "active"

    refreshed = client.get(f"/api/processings/{processing['id']}").json()["versions"]
    old = next(v for v in refreshed if v["id"] == active["id"])
    assert old["status"] == "inactive" and old["valid_to"] is not None

    diff = client.get(f"/api/processings/{processing['id']}/compare", params={"a": active["id"], "b": draft["id"]}).json()
    assert diff["diff"] == []
