"""Seed the demo world: ATS34 real workbook data + coherent synthetic ATS35.

- raw_data stand-in: stations, sensors, raw observations, environment readings ;
- physical point catalogue: nine known REFs + monitoring points ;
- two ready-to-run processings (network + single station) with active v1.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .db import Base, engine
from .templates import base_payload, measurement_for

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATS34_WINDOW = ("2025-03-09T00:00:00.000Z", "2025-03-10T23:59:59.999Z")
REF_SUFFIXES = ["329", "332", "335", "341", "347", "360", "363", "366", "369"]
SHARED_WITH_ATS35 = ["329", "335", "341", "347", "360"]

# Seeded run parameters follow the real site rhythm: 4-hourly cycles,
# ~25-minute desynchronisation between stations, 4-hourly publication grid.
SEEDED_RUN = {
    "trigger": "event-driven",
    "cycle_tolerance_minutes": 12,
    "sync_tolerance_minutes": 60,
    "max_epoch_to_slot_minutes": 330,
    "max_reused_age_minutes": 300,
    "allow_future_minutes": 45,
    "allow_reuse_last_cycle": True,
    "missing_station_policy": "provisional",
    "catch_up_on_late_data": True,
}
SEEDED_OUTPUT = {"grid_minutes": 240}


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(func.count(models.Station.code))) == 0:
        seed(db)


def seed(db: Session) -> None:
    ats34 = json.loads((DATA_DIR / "ats34.generated.json").read_text())
    ats35 = json.loads((DATA_DIR / "ats35.generated.json").read_text())

    # -- Stations -------------------------------------------------------------
    db.add(models.Station(code="NTE_ATS34", name="ATS34 — NTE portal (real workbook)", instrument_model="Leica TM50", site="NTE", instrument_height_m=0.0, e=280483.3552, n=288515.7764, h=31.5058))
    db.add(models.Station(code="NTE_ATS35", name="ATS35 — NTE north side (synthetic)", instrument_model="Leica TS16", site="NTE", instrument_height_m=0.0, e=280498.0, n=288548.0, h=32.1))

    # -- Sensors ---------------------------------------------------------------
    sensor_ids: dict[tuple[str, str], int] = {}

    def add_sensor(station: str, row: dict) -> None:
        prism_constant = float(row.get("PrismConstant") or 0.0)
        measurement_type = row.get("PrismType") or ("reflectorless" if prism_constant == 0.0 else "prism")
        if measurement_type not in {"prism", "reflective-sheet", "reflectorless"}:
            measurement_type = "prism"
        sensor = models.Sensor(
            station_code=station,
            raw_name=row["TargetName"],
            measurement_type=measurement_type,
            prism_constant_required_m=prism_constant,
            prism_constant_applied_m=0.0,
            target_height_m=float(row.get("TargetHeight") or 0.0),
        )
        db.add(sensor)
        db.flush()
        sensor_ids[(station, row["TargetName"])] = sensor.id

    for row in ats34["lookup"]:
        add_sensor("NTE_ATS34", row)
    for row in ats35["lookup"]:
        add_sensor("NTE_ATS35", row)

    # -- Raw observations (ATS34: one real day; ATS35: full synthetic day) -----
    for raw in ats34["rawObservations"]:
        if not (ATS34_WINDOW[0] <= raw["epoch"] <= ATS34_WINDOW[1]):
            continue
        db.add(
            models.RawObservation(
                id=raw["id"],
                station_code="NTE_ATS34",
                sensor_id=sensor_ids[("NTE_ATS34", raw["rawTargetName"])],
                epoch=raw["epoch"],
                record_number=raw["recordNumber"],
                hz_rad=math.radians(raw["hzDeg"]),
                vz_rad=math.radians(raw["vzDeg"]),
                sd_m=raw["sdM"],
            )
        )
    for raw in ats35["rawObservations"]:
        db.add(
            models.RawObservation(
                id=raw["id"],
                station_code="NTE_ATS35",
                sensor_id=sensor_ids[("NTE_ATS35", raw["rawTargetName"])],
                epoch=raw["epoch"],
                record_number=raw["recordNumber"],
                hz_rad=math.radians(raw["hzDeg"]),
                vz_rad=math.radians(raw["vzDeg"]),
                sd_m=raw["sdM"],
            )
        )

    # -- Environment readings (ATS34 synthetic series; ATS35 from generator) ---
    rng = random.Random(7)
    start = datetime(2025, 3, 8, 23, 0, tzinfo=timezone.utc)
    for step in range(300):
        t = start + timedelta(minutes=10 * step)
        hours = (t - datetime(2025, 3, 9, 0, 0, tzinfo=timezone.utc)).total_seconds() / 3600.0
        db.add(
            models.EnvironmentReading(
                station_code="NTE_ATS34",
                epoch=_iso(t),
                temperature_c=9.0 + 4.0 * math.sin((hours - 3.0) / 24.0 * 2.0 * math.pi) + rng.gauss(0, 0.3),
                pressure_hpa=1008.0 + 1.5 * math.sin(hours / 24.0 * 2.0 * math.pi) + rng.gauss(0, 0.5),
            )
        )
    for row in ats35["environment"]:
        db.add(
            models.EnvironmentReading(
                station_code="NTE_ATS35",
                epoch=row["epoch"],
                temperature_c=row["temperatureC"],
                pressure_hpa=row["pressureHpa"],
            )
        )

    # -- Physical point catalogue ----------------------------------------------
    header = {row["PointId"]: row for row in ats34["header"]}
    for suffix in REF_SUFFIXES:
        ref = header[f"L34RE1100_{suffix}"]
        db.add(
            models.PhysicalPoint(
                id=f"REF_{suffix}",
                label=f"Référence site {suffix} / Site reference {suffix}",
                known_e=float(ref["Easting"]),
                known_n=float(ref["Northing"]),
                known_h=float(ref["Height"]),
                sigma_e_m=float(ref["StDevE"]) if ref["StDevE"] != "*" else 0.002,
                sigma_n_m=float(ref["StDevN"]) if ref["StDevN"] != "*" else 0.002,
                sigma_h_m=float(ref["StDevH"]) if ref["StDevH"] != "*" else 0.002,
            )
        )
    for row in ats34["lookup"]:
        name = row["TargetName"]
        if name.startswith("L34RE1100_"):
            continue
        db.add(models.PhysicalPoint(id=f"PP_{name}", label=f"{name} (ATS34)"))
    for target in ats35["meta"]["sharedReferences"]:
        pass  # REFs already created above
    for name in ("L35MPO101_401", "L35MPO102_402", "L35MPO103_403", "L35MPO104_404"):
        db.add(models.PhysicalPoint(id=f"PP_{name}", label=f"{name} (ATS35)"))
    db.flush()

    # -- Processings -------------------------------------------------------------
    db.add_all(
        [
            _network_processing(sensor_ids),
            _single_processing(sensor_ids),
        ]
    )
    db.add(models.DemoState(key="late_data", value={"delivered": False, "cycle": ats35["meta"]["scenarios"]["heldBackCycle"], "count": len(ats35["heldBackObservations"])}))
    db.add(models.AuditEvent(kind="seed", message="Demo world seeded: ATS34 real day + ATS35 synthetic coherent station", payload={"ats34_obs": True}))
    db.commit()

    # Pre-run day 1 so the app is alive on first open: 08:00 stays provisional
    # (ATS35 cycle held back), ready for the catch-up scenario.
    from .services import engine as engine_service

    for processing in db.execute(select(models.Processing)).scalars():
        version = processing.versions[0]
        if processing.kind == "network":
            for hour in (0, 4, 8, 12, 16, 20):
                engine_service.run_pipeline(db, processing, version, f"2025-03-09T{hour:02d}:00:00.000Z", trigger="scheduled")
        else:
            for hour in (0, 4):
                engine_service.run_pipeline(db, processing, version, f"2025-03-09T{hour:02d}:00:00.000Z", trigger="scheduled")
    db.commit()


def _version_payload_base(kind: str) -> dict:
    payload = base_payload("uk", kind)
    payload["initialisation"] = {"method": "local-system", "window_from": ATS34_WINDOW[0], "window_to": "2025-03-09T05:00:00.000Z"}
    payload["run"] = dict(SEEDED_RUN)
    payload["output"] = dict(SEEDED_OUTPUT)
    return payload


def _ats34_station_entry() -> dict:
    return {
        "code": "NTE_ATS34",
        "required": True,
        "instrument_height_m": 0.0,
        "coordinates": {"mode": "weak", "e": 280483.3552, "n": 288515.7764, "h": 31.5058, "sigma_m": 0.1},
    }


def _ats35_station_entry() -> dict:
    return {
        "code": "NTE_ATS35",
        "required": True,
        "instrument_height_m": 0.0,
        "coordinates": {"mode": "free", "e": 280498.0, "n": 288548.0, "h": 32.1},
    }


def _ats34_targets(sensor_ids: dict[tuple[str, str], int]) -> tuple[list[dict], list[dict]]:
    targets, points = [], []
    for (station, raw_name), sensor_id in sorted(sensor_ids.items()):
        if station != "NTE_ATS34":
            continue
        if raw_name.startswith("L34RE1100_"):
            suffix = raw_name.rsplit("_", 1)[1]
            point_id, role = f"REF_{suffix}", "reference"
        else:
            point_id, role = f"PP_{raw_name}", "monitoring"
        targets.append(
            {
                "station_code": station,
                "sensor_id": sensor_id,
                "raw_name": raw_name,
                "physical_point_id": point_id,
                "role": role,
                "measurement": measurement_for("uk", "prism", 0.0089),
                # Tuned to the observed noise of the real ATS34 workbook data.
                "weights": {"direction_arcsec": 3.0, "zenith_arcsec": 3.5, "distance_mm": 2.0, "distance_ppm": 2.0},
            }
        )
    return targets, points


def _network_processing(sensor_ids: dict[tuple[str, str], int]) -> models.Processing:
    payload = _version_payload_base("network")
    payload["stations"] = [_ats34_station_entry(), _ats35_station_entry()]
    targets, _ = _ats34_targets(sensor_ids)
    for suffix in SHARED_WITH_ATS35:
        raw_name = f"L35RE1100_{suffix}"
        targets.append(
            {
                "station_code": "NTE_ATS35",
                "sensor_id": sensor_ids[("NTE_ATS35", raw_name)],
                "raw_name": raw_name,
                "physical_point_id": f"REF_{suffix}",
                "role": "reference",
                "measurement": measurement_for("uk", "prism", 0.0089),
                "weights": {"direction_arcsec": 1.5, "zenith_arcsec": 2.0, "distance_mm": 1.0, "distance_ppm": 1.0},
            }
        )
    for name in ("L35MPO101_401", "L35MPO102_402", "L35MPO103_403", "L35MPO104_404"):
        measurement_type = "reflectorless" if name == "L35MPO104_404" else "prism"
        targets.append(
            {
                "station_code": "NTE_ATS35",
                "sensor_id": sensor_ids[("NTE_ATS35", name)],
                "raw_name": name,
                "physical_point_id": f"PP_{name}",
                "role": "monitoring",
                "measurement": measurement_for("uk", measurement_type, 0.0 if measurement_type == "reflectorless" else 0.0089),
                "weights": {"direction_arcsec": 1.5, "zenith_arcsec": 2.0, "distance_mm": 1.0, "distance_ppm": 1.0},
            }
        )
    payload["targets"] = targets
    points = []
    header_coords = {
        "329": (280558.5586, 288493.5581, 30.7208, 0.002, 0.001),
        "332": (280550.5465, 288495.4275, 30.6846, 0.002, 0.001),
        "335": (280541.7455, 288497.4865, 30.6461, 0.001, 0.001),
        "341": (280523.692, 288501.7133, 30.5793, 0.001, 0.001),
        "347": (280505.9113, 288507.4331, 30.5209, 0.001, 0.001),
        "360": (280467.5316, 288516.449, 30.328, 0.001, 0.001),
        "363": (280459.2769, 288518.3956, 30.2715, 0.001, 0.001),
        "366": (280450.3657, 288520.4992, 30.2448, 0.001, 0.001),
        "369": (280441.3887, 288522.6124, 30.202, 0.001, 0.001),
    }
    for suffix in REF_SUFFIXES:
        e, n, h, se, sn = header_coords[suffix]
        points.append(
            {
                "id": f"REF_{suffix}",
                "role": "reference",
                "known": {"e": e, "n": n, "h": h},
                "constraint": {"e": "weak", "n": "weak", "h": "weak"},
                "sigma_m": {"e": se, "n": sn, "h": 0.002},
            }
        )
    for target in targets:
        point_id = target["physical_point_id"]
        if point_id.startswith("PP_") and not any(p["id"] == point_id for p in points):
            points.append({"id": point_id, "role": "monitoring", "known": None, "constraint": {"e": "free", "n": "free", "h": "free"}, "sigma_m": {}})
    payload["physical_points"] = points

    processing = models.Processing(
        name="NTE Network — ATS34 + ATS35",
        description="Réseau connecté 2 stations : 5 références communes, données réelles ATS34 + station synthétique cohérente ATS35. / Connected 2-station network: 5 shared references, real ATS34 data + coherent synthetic ATS35.",
        kind="network",
        template="uk",
        state="active",
    )
    processing.versions.append(
        models.ConfigVersion(number=1, status="active", valid_from=ATS34_WINDOW[0], valid_to=None, payload=payload, origin="seed")
    )
    return processing


def _single_processing(sensor_ids: dict[tuple[str, str], int]) -> models.Processing:
    payload = _version_payload_base("single-station")
    payload["stations"] = [_ats34_station_entry()]
    targets, _ = _ats34_targets(sensor_ids)
    payload["targets"] = targets
    points = []
    header_coords = {
        "329": (280558.5586, 288493.5581, 30.7208, 0.002, 0.001),
        "332": (280550.5465, 288495.4275, 30.6846, 0.002, 0.001),
        "335": (280541.7455, 288497.4865, 30.6461, 0.001, 0.001),
        "341": (280523.692, 288501.7133, 30.5793, 0.001, 0.001),
        "347": (280505.9113, 288507.4331, 30.5209, 0.001, 0.001),
        "360": (280467.5316, 288516.449, 30.328, 0.001, 0.001),
        "363": (280459.2769, 288518.3956, 30.2715, 0.001, 0.001),
        "366": (280450.3657, 288520.4992, 30.2448, 0.001, 0.001),
        "369": (280441.3887, 288522.6124, 30.202, 0.001, 0.001),
    }
    for suffix in REF_SUFFIXES:
        e, n, h, se, sn = header_coords[suffix]
        points.append({"id": f"REF_{suffix}", "role": "reference", "known": {"e": e, "n": n, "h": h}, "constraint": {"e": "weak", "n": "weak", "h": "weak"}, "sigma_m": {"e": se, "n": sn, "h": 0.002}})
    for target in targets:
        point_id = target["physical_point_id"]
        if point_id.startswith("PP_") and not any(p["id"] == point_id for p in points):
            points.append({"id": point_id, "role": "monitoring", "known": None, "constraint": {"e": "free", "n": "free", "h": "free"}, "sigma_m": {}})
    payload["physical_points"] = points
    processing = models.Processing(
        name="NTE ATS34 — Station seule",
        description="Station unique sur données réelles du classeur ATS34 (1 jour). / Single station on real ATS34 workbook data (1 day).",
        kind="single-station",
        template="uk",
        state="active",
    )
    processing.versions.append(
        models.ConfigVersion(number=1, status="active", valid_from=ATS34_WINDOW[0], valid_to=None, payload=payload, origin="seed")
    )
    return processing


def deliver_late_data(db: Session) -> dict:
    """Deliver the held-back ATS35 06:26 cycle and mark affected slots."""
    state = db.get(models.DemoState, "late_data")
    if state is None or state.value.get("delivered"):
        return {"delivered": False, "reason": "already delivered"}
    ats35 = json.loads((DATA_DIR / "ats35.generated.json").read_text())
    sensor_map = {
        sensor.raw_name: sensor.id
        for sensor in db.execute(select(models.Sensor).where(models.Sensor.station_code == "NTE_ATS35")).scalars()
    }
    for raw in ats35["heldBackObservations"]:
        db.add(
            models.RawObservation(
                id=raw["id"],
                station_code="NTE_ATS35",
                sensor_id=sensor_map[raw["rawTargetName"]],
                epoch=raw["epoch"],
                record_number=raw["recordNumber"],
                hz_rad=math.radians(raw["hzDeg"]),
                vz_rad=math.radians(raw["vzDeg"]),
                sd_m=raw["sdM"],
            )
        )
    state.value = {**state.value, "delivered": True, "delivered_at": _iso(datetime.now(timezone.utc))}
    db.add(models.AuditEvent(kind="late-data", message=f"Late ATS35 cycle {state.value['cycle']} delivered ({state.value['count']} observations)", payload={}))
    db.commit()
    return {"delivered": True, "cycle": state.value["cycle"], "count": state.value["count"]}
