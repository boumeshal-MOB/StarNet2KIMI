"""Output-slot and whole-station cycle selection.

Selection is station-scoped, never target-scoped: all targets retained for one station come
from the same acquisition cycle.  This prevents a synthetic epoch assembled from unrelated
target timestamps.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Epochs must include a timezone")
    return parsed


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def select_network_epochs(
    observations: Iterable[Mapping[str, Any]],
    station_codes: Iterable[str],
    slot_iso: str,
    *,
    cycle_tolerance_minutes: float,
    fresh_tolerance_minutes: float,
    max_reused_age_minutes: float,
    max_epoch_to_slot_minutes: float,
    allow_future_minutes: float = 0.0,
) -> dict[str, Any]:
    """Choose one acquisition cycle per station and report target availability.

    ``cycle_tolerance_minutes`` groups individual target timestamps belonging to the same
    station cycle.  A cycle representative is its median timestamp.  The selected cycle must
    be no later than ``slot + allow_future_minutes`` and within ``max_epoch_to_slot_minutes``.
    Reuse is reported separately and never disguised as fresh data.
    """

    tolerances = {
        "cycle_tolerance_minutes": cycle_tolerance_minutes,
        "fresh_tolerance_minutes": fresh_tolerance_minutes,
        "max_reused_age_minutes": max_reused_age_minutes,
        "max_epoch_to_slot_minutes": max_epoch_to_slot_minutes,
        "allow_future_minutes": allow_future_minutes,
    }
    for name, value in tolerances.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    slot = _instant(slot_iso)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for observation in observations:
        grouped[str(observation["station_code"])].append(observation)
    result: dict[str, Any] = {"slot": slot_iso, "stations": [], "selected_observations": []}

    for station_code in station_codes:
        source = sorted(grouped.get(station_code, []), key=lambda row: _instant(str(row["epoch"])))
        cycles: list[list[Mapping[str, Any]]] = []
        for observation in source:
            epoch = _instant(str(observation["epoch"]))
            if not cycles:
                cycles.append([observation])
                continue
            current_times = sorted(_instant(str(item["epoch"])) for item in cycles[-1])
            median = current_times[len(current_times) // 2]
            if abs((epoch - median).total_seconds()) <= cycle_tolerance_minutes * 60:
                cycles[-1].append(observation)
            else:
                cycles.append([observation])

        candidates: list[tuple[datetime, list[Mapping[str, Any]]]] = []
        latest = slot + timedelta(minutes=allow_future_minutes)
        earliest = slot - timedelta(minutes=max_epoch_to_slot_minutes)
        for cycle in cycles:
            times = sorted(_instant(str(item["epoch"])) for item in cycle)
            representative = times[(len(times) - 1) // 2]
            if earliest <= representative <= latest:
                candidates.append((representative, cycle))
        if not candidates:
            result["stations"].append(
                {"station_code": station_code, "state": "missing", "target_count": 0, "availability_percent": 0.0}
            )
            continue
        representative, selected = max(candidates, key=lambda candidate: candidate[0])
        offset_minutes = (slot - representative).total_seconds() / 60.0
        age_minutes = max(0.0, offset_minutes)
        state = "fresh" if age_minutes <= fresh_tolerance_minutes else "reused"
        if state == "reused" and age_minutes > max_reused_age_minutes:
            result["stations"].append(
                {"station_code": station_code, "state": "missing", "target_count": 0, "availability_percent": 0.0}
            )
            continue
        unique_targets = {str(item["target_name"]) for item in source}
        selected_by_target: dict[str, Mapping[str, Any]] = {}
        for observation in selected:
            target = str(observation["target_name"])
            previous = selected_by_target.get(target)
            if previous is None or _instant(str(observation["epoch"])) > _instant(str(previous["epoch"])):
                selected_by_target[target] = observation
        retained = list(selected_by_target.values())
        result["selected_observations"].extend(retained)
        result["stations"].append(
            {
                "station_code": station_code,
                "state": state,
                "cycle_epoch": _iso(representative),
                "age_minutes": age_minutes,
                "offset_to_slot_minutes": offset_minutes,
                "target_count": len(retained),
                "expected_target_count": len(unique_targets),
                "availability_percent": 100.0 * len(retained) / max(1, len(unique_targets)),
                "source_epoch_min": _iso(min(_instant(str(item["epoch"])) for item in retained)),
                "source_epoch_max": _iso(max(_instant(str(item["epoch"])) for item in retained)),
            }
        )
    return result
