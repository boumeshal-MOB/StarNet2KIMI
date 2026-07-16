"""Auditable 3D weighted least-squares adjustment.

The implementation uses scaled trust-region Gauss-Newton through SciPy, an analytic Jacobian,
rank diagnostics from SVD and covariance from the weighted design matrix.  It intentionally
does not call STAR*NET; production comparison is done with exported golden cases.
"""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import chi2

from .contracts import validate_adjustment_input
from .geometry import circular_mean, normalize_face, wrap_pi
from .preparation import prepare_scalar_observations


def adjust_network(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "observations" not in payload and "sights" in payload:
        payload = {**payload, "observations": prepare_scalar_observations(payload["sights"], payload["default_weights"])}
    validate_adjustment_input(payload)
    point_rows = [dict(point) for point in payload["points"]]
    observation_rows = [dict(observation) for observation in payload["observations"] if not observation.get("excluded")]
    constraints = [dict(constraint) for constraint in payload.get("constraints", [])]
    options = dict(payload.get("options", {}))

    point_by_id = {str(point["id"]): point for point in point_rows}
    free_points = [point for point in point_rows if point.get("free", True)]
    coordinate_index: dict[str, int] = {}
    parameter_names: list[str] = []
    x0: list[float] = []
    for point in free_points:
        point_id = str(point["id"])
        coordinate_index[point_id] = len(x0)
        x0.extend([float(point["e"]), float(point["n"]), float(point["h"])])
        parameter_names.extend([f"{point_id}.E", f"{point_id}.N", f"{point_id}.H"])

    fixed_orientations = {str(key): float(value) for key, value in options.get("fixed_orientations_rad", {}).items()}
    hz_stations = sorted({str(observation["station_id"]) for observation in observation_rows if observation["kind"] == "hz"})
    orientation_index: dict[str, int] = {}
    initial_orientations: dict[str, float] = {}
    for station_id in hz_stations:
        if station_id in fixed_orientations:
            initial_orientations[station_id] = fixed_orientations[station_id]
            continue
        station = point_by_id[station_id]
        candidates: list[float] = []
        for observation in observation_rows:
            if observation["kind"] != "hz" or str(observation["station_id"]) != station_id:
                continue
            target = point_by_id[str(observation["target_id"])]
            predicted_azimuth = math.atan2(float(target["e"]) - float(station["e"]), float(target["n"]) - float(station["n"]))
            candidates.append(wrap_pi(predicted_azimuth - float(observation["value"])))
        initial = circular_mean(candidates) if candidates else 0.0
        initial_orientations[station_id] = initial
        orientation_index[station_id] = len(x0)
        x0.append(initial)
        parameter_names.append(f"{station_id}.orientation")

    def coordinates(parameters: np.ndarray, point_id: str) -> tuple[float, float, float]:
        point = point_by_id[point_id]
        index = coordinate_index.get(point_id)
        if index is None:
            return float(point["e"]), float(point["n"]), float(point["h"])
        return float(parameters[index]), float(parameters[index + 1]), float(parameters[index + 2])

    def orientation(parameters: np.ndarray, station_id: str) -> float:
        index = orientation_index.get(station_id)
        return fixed_orientations.get(station_id, float(parameters[index]) if index is not None else initial_orientations.get(station_id, 0.0))

    def system(parameters: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[float], list[str]]:
        weighted: list[float] = []
        jacobian: list[list[float]] = []
        raw: list[float] = []
        row_ids: list[str] = []
        for observation in observation_rows:
            station_id = str(observation["station_id"])
            target_id = str(observation["target_id"])
            station = coordinates(parameters, station_id)
            target = coordinates(parameters, target_id)
            instrument_height = float(observation.get("instrument_height_m", 0.0))
            target_height = float(observation.get("target_height_m", 0.0))
            de = target[0] - station[0]
            dn = target[1] - station[1]
            dh = target[2] + target_height - station[2] - instrument_height
            horizontal2 = de * de + dn * dn
            horizontal = math.sqrt(horizontal2)
            slope2 = horizontal2 + dh * dh
            slope = math.sqrt(slope2)
            if horizontal < 1e-10 or slope < 1e-10:
                raise ValueError(f"Observation {observation['id']} has coincident station and target")
            derivative = np.zeros(len(parameters), dtype=float)
            station_index = coordinate_index.get(station_id)
            target_index = coordinate_index.get(target_id)
            kind = str(observation["kind"])
            observed = float(observation["value"])
            if kind == "hz":
                predicted = wrap_pi(math.atan2(de, dn) - orientation(parameters, station_id))
                d_e = dn / horizontal2
                d_n = -de / horizontal2
                _assign_coordinate_derivative(derivative, target_index, (d_e, d_n, 0.0), 1.0)
                _assign_coordinate_derivative(derivative, station_index, (d_e, d_n, 0.0), -1.0)
                orientation_slot = orientation_index.get(station_id)
                if orientation_slot is not None:
                    derivative[orientation_slot] = -1.0
                residual = wrap_pi(predicted - observed)
            elif kind == "vz":
                predicted = math.atan2(horizontal, dh)
                d_v_h = dh / slope2
                d_v_dh = -horizontal / slope2
                vector = (d_v_h * de / horizontal, d_v_h * dn / horizontal, d_v_dh)
                _assign_coordinate_derivative(derivative, target_index, vector, 1.0)
                _assign_coordinate_derivative(derivative, station_index, vector, -1.0)
                residual = wrap_pi(predicted - observed)
            elif kind == "sd":
                predicted = slope
                vector = (de / slope, dn / slope, dh / slope)
                _assign_coordinate_derivative(derivative, target_index, vector, 1.0)
                _assign_coordinate_derivative(derivative, station_index, vector, -1.0)
                residual = predicted - observed
            else:
                raise ValueError(f"Unsupported observation kind {kind!r}")
            sigma = float(observation["sigma"])
            weighted.append(residual / sigma)
            jacobian.append((derivative / sigma).tolist())
            raw.append(-residual)  # observed minus computed, STAR*NET report convention
            row_ids.append(str(observation["id"]))

        for constraint in constraints:
            point_id = str(constraint["point_id"])
            component = str(constraint["component"])
            component_offset = {"e": 0, "n": 1, "h": 2}[component]
            current = coordinates(parameters, point_id)[component_offset]
            residual = current - float(constraint["value"])
            derivative = np.zeros(len(parameters), dtype=float)
            point_index = coordinate_index.get(point_id)
            if point_index is not None:
                derivative[point_index + component_offset] = 1.0
            sigma = float(constraint["sigma"])
            weighted.append(residual / sigma)
            jacobian.append((derivative / sigma).tolist())
            raw.append(-residual)
            row_ids.append(f"constraint:{point_id}.{component}")
        return np.asarray(weighted), np.asarray(jacobian), raw, row_ids

    x_initial = np.asarray(x0, dtype=float)
    if len(observation_rows) + len(constraints) < len(x_initial):
        return _failure("Under-determined system", parameter_names, len(observation_rows), len(constraints))
    try:
        solution = least_squares(
            lambda values: system(values)[0],
            x_initial,
            jac=lambda values: system(values)[1],
            method="trf",
            x_scale="jac",
            ftol=float(options.get("convergence_threshold_m", 1e-6)),
            xtol=float(options.get("convergence_threshold_m", 1e-6)),
            gtol=1e-12,
            max_nfev=int(options.get("max_iterations", 20)),
        )
        weighted_residuals, design, raw_residuals, row_ids = system(solution.x)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        return _failure(str(exc), parameter_names, len(observation_rows), len(constraints))

    left_vectors, singular_values, right_vectors = np.linalg.svd(design, full_matrices=False)
    tolerance = max(design.shape) * np.finfo(float).eps * (singular_values[0] if singular_values.size else 1.0)
    rank = int(np.sum(singular_values > tolerance))
    deficient = len(solution.x) - rank
    nullspace = right_vectors[rank:, :] if deficient > 0 else np.empty((0, len(solution.x)))
    nullspace_contribution = np.max(np.abs(nullspace), axis=0) if nullspace.size else np.zeros(len(solution.x))
    max_nullspace_contribution = float(np.max(nullspace_contribution)) if nullspace_contribution.size else 0.0
    deficient_unknowns = [
        parameter_names[index]
        for index, contribution in enumerate(nullspace_contribution)
        if max_nullspace_contribution > 0 and contribution >= 0.1 * max_nullspace_contribution
    ]
    dof = len(weighted_residuals) - rank
    weighted_ssr = float(weighted_residuals @ weighted_residuals)
    significance = float(options.get("chi_square_significance", 0.05))
    if dof > 0:
        lower = float(chi2.ppf(significance / 2.0, dof))
        upper = float(chi2.ppf(1.0 - significance / 2.0, dof))
        chi_status = "passed" if lower <= weighted_ssr <= upper else "failed"
        variance_factor = weighted_ssr / dof
    else:
        lower = upper = float("nan")
        chi_status = "not-applicable"
        variance_factor = float("nan")

    # SVD covariance avoids explicitly forming AᵀA, which would square the condition number.
    inverse_squared = np.zeros_like(singular_values)
    inverse_squared[:rank] = 1.0 / singular_values[:rank] ** 2
    normal_inverse = (right_vectors.T * inverse_squared) @ right_vectors
    # STAR*NET-compatible policy: a-priori covariance is kept when the test passes or the
    # variance factor is below one.  A failed upper test may inflate uncertainty, never shrink it.
    covariance_factor = 1.0
    if options.get("error_propagation", True) and chi_status == "failed" and weighted_ssr > upper:
        covariance_factor = max(1.0, variance_factor)
    covariance = normal_inverse * covariance_factor
    hat = left_vectors[:, :rank] @ left_vectors[:, :rank].T
    redundancies = np.clip(1.0 - np.diag(hat), 0.0, 1.0)

    residual_entries: list[dict[str, Any]] = []
    type_aggregates: dict[str, list[tuple[float, float]]] = defaultdict(list)
    observation_count_by_point: dict[str, int] = defaultdict(int)
    for index, (raw, weighted, redundancy, row_id) in enumerate(
        zip(raw_residuals, weighted_residuals.tolist(), redundancies.tolist(), row_ids, strict=True)
    ):
        is_observation = index < len(observation_rows)
        if is_observation:
            source = observation_rows[index]
            kind = str(source["kind"])
            sigma = float(source["sigma"])
            station_id = str(source["station_id"])
            target_id = str(source["target_id"])
            raw_observation_id = str(source.get("raw_observation_id", source["id"]))
            observation_count_by_point[target_id] += 1
        else:
            source = constraints[index - len(observation_rows)]
            kind = "constraint"
            sigma = float(source["sigma"])
            station_id = ""
            target_id = str(source["point_id"])
            raw_observation_id = ""
        # STAR*NET StdRes = absolute residual / a-priori standard error.
        standardized = abs(raw) / sigma
        # Baarda/data-snooping normalized residual includes redundancy and is exposed separately.
        normalized = standardized / math.sqrt(redundancy) if redundancy > 1e-12 else float("nan")
        type_aggregates[kind].append((weighted * weighted, redundancy))
        residual_entries.append(
            {
                "id": row_id,
                "raw_observation_id": raw_observation_id,
                "station_id": station_id,
                "target_id": target_id,
                "kind": kind,
                "residual": raw,
                "sigma": sigma,
                "standardized_residual": standardized,
                "normalized_residual": normalized,
                "redundancy": redundancy,
            }
        )

    confidence = float(options.get("confidence_level", 0.95))
    ellipse_scale = math.sqrt(float(chi2.ppf(confidence, 2)))
    adjusted_points: list[dict[str, Any]] = []
    for point in point_rows:
        point_id = str(point["id"])
        e, n, h = coordinates(solution.x, point_id)
        index = coordinate_index.get(point_id)
        if index is None:
            sigma_e = sigma_n = sigma_h = cov_en = 0.0
        else:
            sigma_e = math.sqrt(max(0.0, covariance[index, index]))
            sigma_n = math.sqrt(max(0.0, covariance[index + 1, index + 1]))
            sigma_h = math.sqrt(max(0.0, covariance[index + 2, index + 2]))
            cov_en = float(covariance[index, index + 1])
        semi_major, semi_minor, orientation_deg = _ellipse(sigma_e**2, sigma_n**2, cov_en)
        adjusted_points.append(
            {
                "id": point_id,
                "role": point.get("role", "monitoring"),
                "e": e,
                "n": n,
                "h": h,
                "sigma_e": sigma_e,
                "sigma_n": sigma_n,
                "sigma_h": sigma_h,
                "cov_en": cov_en,
                "ellipse_semi_major_m": semi_major * ellipse_scale,
                "ellipse_semi_minor_m": semi_minor * ellipse_scale,
                "ellipse_orientation_deg": orientation_deg,
                "observation_count": observation_count_by_point[point_id],
            }
        )

    orientations = []
    for station_id in hz_stations:
        index = orientation_index.get(station_id)
        value = orientation(solution.x, station_id)
        orientations.append(
            {
                "station_id": station_id,
                "value_rad": wrap_pi(value),
                "sigma_rad": math.sqrt(max(0.0, covariance[index, index])) if index is not None else 0.0,
                "fixed": index is None,
            }
        )

    worst = max(
        (entry for entry in residual_entries if entry["kind"] != "constraint"),
        key=lambda entry: entry["standardized_residual"],
        default=None,
    )
    return {
        "model": "euclidean-local-preview-v1",
        "model_scope": "Datum scale, earth curvature and refraction remain certified STAR*NET responsibilities",
        "ok": bool(solution.success and rank == len(solution.x)),
        "converged": bool(solution.success),
        "message": solution.message,
        "iterations": int(solution.nfev),
        "observation_count": len(observation_rows),
        "constraint_count": len(constraints),
        "unknown_count": len(solution.x),
        "rank": rank,
        "rank_deficiency": deficient,
        "deficient_unknowns": deficient_unknowns,
        "rank_nullspace_contribution": {
            parameter_names[index]: float(contribution)
            for index, contribution in enumerate(nullspace_contribution)
            if contribution > 0
        },
        "degrees_of_freedom": dof,
        "weighted_ssr": weighted_ssr,
        "variance_factor": variance_factor,
        "total_error_factor": math.sqrt(variance_factor) if variance_factor >= 0 else float("nan"),
        "covariance_scale_factor": covariance_factor,
        "chi_square_status": chi_status,
        "chi_square_lower": lower,
        "chi_square_upper": upper,
        "points": adjusted_points,
        "orientations": orientations,
        "residuals": residual_entries,
        "max_standardized_residual": worst["standardized_residual"] if worst else 0.0,
        "max_standardized_residual_id": worst["id"] if worst else None,
        "error_factor_by_type": {
            kind: math.sqrt(sum(ssr for ssr, _ in values) / sum(red for _, red in values))
            if sum(red for _, red in values) > 1e-12
            else 0.0
            for kind, values in type_aggregates.items()
        },
    }


def auto_adjust(payload: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Run traceable scalar-observation data snooping without changing raw observations."""

    trial = copy.deepcopy(dict(payload))
    if "observations" not in trial and "sights" in trial:
        trial["observations"] = prepare_scalar_observations(trial["sights"], trial["default_weights"])
    excluded = {str(row["id"]) for row in trial["observations"] if row.get("excluded")}
    protected = {str(row["id"]) for row in trial["observations"] if row.get("protected")}
    attempts: list[dict[str, Any]] = []
    result = adjust_network(trial)
    if not config.get("enabled") or result["chi_square_status"] != "failed":
        return {**result, "auto_adjust_attempts": attempts}
    for attempt in range(1, int(config.get("max_iterations", 5)) + 1):
        candidates = sorted(
            (
                residual
                for residual in result["residuals"]
                if residual["kind"] != "constraint"
                and residual["id"] not in protected
                and residual["id"] not in excluded
                and residual["standardized_residual"] > float(config.get("max_standardized_residual", 3.0))
            ),
            key=lambda residual: residual["standardized_residual"],
            reverse=True,
        )[: max(1, int(config.get("outliers_removed_per_iteration", 1)))]
        if not candidates:
            break
        for candidate in candidates:
            excluded.add(candidate["id"])
        for observation in trial["observations"]:
            observation["excluded"] = str(observation["id"]) in excluded
        result = adjust_network(trial)
        for candidate in candidates:
            attempts.append(
                {
                    "attempt": attempt,
                    "excluded_scalar_observation_id": candidate["id"],
                    "kind": candidate["kind"],
                    "standardized_residual": candidate["standardized_residual"],
                    "chi_square_status_after": result["chi_square_status"],
                }
            )
        if result["chi_square_status"] != "failed":
            break
    return {**result, "auto_adjust_attempts": attempts}


def _assign_coordinate_derivative(row: np.ndarray, index: int | None, vector: tuple[float, float, float], sign: float) -> None:
    if index is not None:
        row[index : index + 3] += sign * np.asarray(vector)


def _ellipse(var_e: float, var_n: float, cov_en: float) -> tuple[float, float, float]:
    covariance = np.asarray([[var_e, cov_en], [cov_en, var_n]], dtype=float)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)[::-1]
    major_vector = vectors[:, order[0]]
    major = math.sqrt(max(0.0, float(values[order[0]])))
    minor = math.sqrt(max(0.0, float(values[order[1]])))
    orientation = math.degrees(math.atan2(float(major_vector[0]), float(major_vector[1]))) % 180.0
    return major, minor, orientation


def _failure(reason: str, parameters: list[str], observation_count: int, constraint_count: int) -> dict[str, Any]:
    return {
        "ok": False,
        "converged": False,
        "failure_reason": reason,
        "observation_count": observation_count,
        "constraint_count": constraint_count,
        "unknown_count": len(parameters),
        "rank": 0,
        "rank_deficiency": len(parameters),
        "deficient_unknowns": parameters,
        "degrees_of_freedom": observation_count + constraint_count - len(parameters),
        "chi_square_status": "not-applicable",
        "points": [],
        "orientations": [],
        "residuals": [],
        "auto_adjust_attempts": [],
    }
