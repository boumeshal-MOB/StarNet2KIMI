"""Generate the synthetic-but-coherent NTE_ATS35 dataset.

ATS35 is a second total station north of the real ATS34 reference line.  It
follows the real site rhythm — six 4-hourly cycles per day, like ATS34 — but
measures ~25 minutes later (:26-:33), which exercises network synchronisation
on the 4-hourly publication grid.

It observes five of the nine physical REF points shared with ATS34 (raw names
``L35RE1100_3xx`` — recognisable by suffix, never merged by name) plus four
monitoring targets of its own.  Observations are forward-simulated from the
real header coordinates with deterministic noise, so the network adjustment
has something real to solve: ATS35's position/orientation and its four MPO
targets are unknowns recovered through the shared REFs.

Scenarios embedded in the dataset:
- 2025-03-09T08:26 cycle held back (late delivery -> catch-up demo);
- 2025-03-09T16:26 cycle carries an +8 mm distance blunder on L35MPO102_402
  (auto-adjust demo: the point is redundant, so the blunder is detectable);
- ATS35 temperature/pressure gap 12:00-16:00 (atmospheric fallback demo).
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

rng = random.Random(42)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ATS34 = json.loads((DATA_DIR / "ats34.generated.json").read_text())

HEADER = {row["PointId"]: row for row in ATS34["header"]}

STATION_ID = "NTE_ATS35"
STATION_E = 280498.0
STATION_N = 288548.0
STATION_H = 32.1
INSTRUMENT_HEIGHT = 0.0
ORIENTATION_RAD = 0.35  # unknown to the engine, solved by resection/adjustment

# Shared physical references (observed by both stations).  Raw names carry the
# station prefix; the physical identity is an explicit mapping in the app.
SHARED_REFS = ["329", "335", "341", "347", "360"]

# ATS35-only monitoring targets (E, N, H) in the same local frame.
MPO_TARGETS = {
    "L35MPO101_401": (280490.0, 288590.0, 33.2),
    "L35MPO102_402": (280515.0, 288605.0, 34.1),
    "L35MPO103_403": (280478.0, 288618.0, 33.8),
    "L35MPO104_404": (280530.0, 288585.0, 33.5),  # reflectorless
}

DAYS = (datetime(2025, 3, 9, tzinfo=timezone.utc), datetime(2025, 3, 10, tzinfo=timezone.utc))
CYCLE_HOURS = (0, 4, 8, 12, 16, 20)
CYCLE_MINUTE = 26
HELD_BACK_CYCLE = datetime(2025, 3, 9, 8, 26, tzinfo=timezone.utc)
BLUNDER_CYCLE = datetime(2025, 3, 9, 16, 26, tzinfo=timezone.utc)
BLUNDER_TARGET = "L35RE1100_341"
BLUNDER_SD_M = 0.008
ENV_GAP = (datetime(2025, 3, 9, 12, 0, tzinfo=timezone.utc), datetime(2025, 3, 9, 16, 0, tzinfo=timezone.utc))

DIR_NOISE_RAD = math.radians(1.5 / 3600.0)
VZ_NOISE_RAD = math.radians(2.0 / 3600.0)


def sd_sigma(distance_m: float) -> float:
    return math.hypot(0.001, distance_m * 1e-6)  # 1 mm + 1 ppm


def observe(target_e: float, target_n: float, target_h: float, prism_constant_m: float) -> tuple[float, float, float]:
    de = target_e - STATION_E
    dn = target_n - STATION_N
    dh = target_h - STATION_H - INSTRUMENT_HEIGHT
    horizontal = math.hypot(de, dn)
    slope = math.hypot(horizontal, dh)
    hz = math.atan2(de, dn) - ORIENTATION_RAD
    vz = math.atan2(horizontal, dh)
    hz += rng.gauss(0.0, DIR_NOISE_RAD)
    vz += rng.gauss(0.0, VZ_NOISE_RAD)
    # UK convention: the station does NOT apply the prism constant; the raw
    # distance is short by the constant and BTM adds it back during correction.
    slope += rng.gauss(0.0, sd_sigma(slope)) - prism_constant_m
    return hz % (2.0 * math.pi), vz, slope


def iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def target_coordinates(name: str) -> tuple[float, float, float]:
    if name.startswith("L35RE1100_"):
        suffix = name.rsplit("_", 1)[1]
        ref = HEADER[f"L34RE1100_{suffix}"]
        return float(ref["Easting"]), float(ref["Northing"]), float(ref["Height"])
    return MPO_TARGETS[name]


ALL_TARGETS = [f"L35RE1100_{suffix}" for suffix in SHARED_REFS] + list(MPO_TARGETS)

cycles: list[datetime] = []
for day in DAYS:
    for hour in CYCLE_HOURS:
        cycles.append(day.replace(hour=hour, minute=CYCLE_MINUTE))

raw: list[dict] = []
held_back: list[dict] = []
record = 22590000
for cycle_start in cycles:
    for target in ALL_TARGETS:
        epoch = cycle_start + timedelta(minutes=rng.uniform(0, 7), seconds=rng.uniform(0, 59))
        prism_constant = 0.0 if target == "L35MPO104_404" else 0.0089
        hz, vz, sd = observe(*target_coordinates(target), prism_constant)
        if cycle_start == BLUNDER_CYCLE and target == BLUNDER_TARGET:
            sd += BLUNDER_SD_M
        row = {
            "id": f"obs-{STATION_ID}-{target}-{record}",
            "stationId": STATION_ID,
            "rawTargetName": target,
            "epoch": iso(epoch),
            "recordNumber": record,
            "hzDeg": round(math.degrees(hz), 5),
            "vzDeg": round(math.degrees(vz), 5),
            "sdM": round(sd, 4),
        }
        record += 1
        if cycle_start == HELD_BACK_CYCLE:
            held_back.append(row)
        else:
            raw.append(row)

# Environment series, 10-minute granularity over both days, minus the gap.
environment: list[dict] = []
t = DAYS[0] - timedelta(minutes=56)
end = DAYS[-1] + timedelta(hours=23)
while t <= end:
    hours = (t - DAYS[0]).total_seconds() / 3600.0
    temperature = 9.0 + 4.0 * math.sin((hours - 3.0) / 24.0 * 2.0 * math.pi) + rng.gauss(0, 0.3)
    pressure = 1008.0 + 1.5 * math.sin(hours / 24.0 * 2.0 * math.pi) + rng.gauss(0, 0.5)
    if not (ENV_GAP[0] <= t < ENV_GAP[1]):
        environment.append(
            {
                "stationId": STATION_ID,
                "epoch": iso(t),
                "temperatureC": round(temperature, 2),
                "pressureHpa": round(pressure, 2),
            }
        )
    t += timedelta(minutes=10)

lookup = []
for target in ALL_TARGETS:
    reflectorless = target == "L35MPO104_404"
    lookup.append(
        {
            "RTS": STATION_ID,
            "TargetName": target,
            "AdjustmentName": target,
            "OutputName": target,
            "TargetHeight": 0,
            "PrismConstant": 0 if reflectorless else 0.0089,
            "PrismType": "reflectorless" if reflectorless else "prism",
            "PrismGrade": "",
            "AdjustmentEnabled": True,
            "GraphEnabled": False,
        }
    )

header = [
    {
        "UsedFromCycle": "2025-03-09T00:00:00.000Z",
        "Code": "C",
        "PointId": STATION_ID,
        "Easting": STATION_E,
        "Northing": STATION_N,
        "Height": STATION_H,
        "StDevE": 0.1,
        "StDevN": 0.1,
        "StDevH": "*",
    }
]

payload = {
    "meta": {
        "source": "synthetic generator (scripts/generate_ats35.py)",
        "stations": [STATION_ID],
        "sharedReferences": [f"REF_{suffix}" for suffix in SHARED_REFS],
        "stationTruth": {
            "e": STATION_E,
            "n": STATION_N,
            "h": STATION_H,
            "orientationRad": ORIENTATION_RAD,
        },
        "scenarios": {
            "heldBackCycle": iso(HELD_BACK_CYCLE),
            "blunder": {"cycle": iso(BLUNDER_CYCLE), "target": BLUNDER_TARGET, "sdAddedM": BLUNDER_SD_M},
            "environmentGap": {"from": iso(ENV_GAP[0]), "to": iso(ENV_GAP[1])},
        },
    },
    "rawObservations": raw,
    "heldBackObservations": held_back,
    "environment": environment,
    "lookup": lookup,
    "header": header,
}

out = DATA_DIR / "ats35.generated.json"
out.write_text(json.dumps(payload, indent=1))
print(f"wrote {out}: {len(raw)} observations, {len(held_back)} held back, {len(environment)} env readings")
