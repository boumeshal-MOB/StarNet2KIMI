"""Input validation shared by the mathematical entry points.

The production API validates a richer JSON schema.  These checks protect the scientific
boundary as well: accepting a zero sigma or a duplicate scalar id would make the adjustment
undefined or its audit trail ambiguous.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any


class ContractError(ValueError):
    """A stable, user-correctable input-contract error."""


def finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ContractError(f"{field} must be a finite number")
    return number


def positive(value: Any, field: str) -> float:
    number = finite(value, field)
    if number <= 0:
        raise ContractError(f"{field} must be greater than zero")
    return number


def probability(value: Any, field: str) -> float:
    number = finite(value, field)
    if not 0 < number < 1:
        raise ContractError(f"{field} must be strictly between 0 and 1")
    return number


def require_unique(items: Iterable[Mapping[str, Any]], field: str, collection: str) -> None:
    seen: set[Any] = set()
    for item in items:
        value = item.get(field)
        if value in seen:
            raise ContractError(f"Duplicate {field} {value!r} in {collection}")
        seen.add(value)


def validate_adjustment_input(payload: Mapping[str, Any]) -> None:
    points = list(payload.get("points", []))
    observations = list(payload.get("observations", []))
    if not points:
        raise ContractError("At least one point is required")
    if not observations:
        raise ContractError("At least one observation is required")
    require_unique(points, "id", "points")
    require_unique(observations, "id", "observations")
    point_ids = {point["id"] for point in points}
    for point in points:
        for component in ("e", "n", "h"):
            finite(point.get(component), f"points[{point.get('id')}].{component}")
    for observation in observations:
        if observation.get("station_id") not in point_ids or observation.get("target_id") not in point_ids:
            raise ContractError(f"Observation {observation.get('id')!r} references an unknown point")
        if observation.get("kind") not in {"hz", "vz", "sd"}:
            raise ContractError(f"Observation {observation.get('id')!r} has an unsupported kind")
        finite(observation.get("value"), f"observations[{observation.get('id')}].value")
        positive(observation.get("sigma"), f"observations[{observation.get('id')}].sigma")
    constraints = list(payload.get("constraints", []))
    for constraint in constraints:
        if constraint.get("point_id") not in point_ids:
            raise ContractError(f"Constraint references unknown point {constraint.get('point_id')!r}")
        if constraint.get("component") not in {"e", "n", "h"}:
            raise ContractError("Constraint component must be e, n or h")
        finite(constraint.get("value"), "constraint.value")
        positive(constraint.get("sigma"), "constraint.sigma")
    options = payload.get("options", {})
    probability(options.get("chi_square_significance", 0.05), "chi_square_significance")
    probability(options.get("confidence_level", 0.95), "confidence_level")
    positive(options.get("convergence_threshold_m", 1e-6), "convergence_threshold_m")
    if int(options.get("max_iterations", 20)) <= 0:
        raise ContractError("max_iterations must be greater than zero")
    for station_id, orientation in options.get("fixed_orientations_rad", {}).items():
        if station_id not in point_ids:
            raise ContractError(f"Fixed orientation references unknown station {station_id!r}")
        finite(orientation, f"fixed_orientations_rad[{station_id}]")
