"""Parsers for native MicroSurvey STAR*NET text formats.

Supported inputs:
- .pts coordinate files from legacy and current STAR*NET releases;
- .err native error logs and the compact BTM test contract;
- .lst adjustment reports with statistics, coordinates, deviations and residuals;
- .prj/.snproj project files;
- .dat observation files.

The .sbf format is binary and proprietary. It is deliberately not decoded here.
"""

from __future__ import annotations

import math
import re
from typing import Any

_FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
_FLOAT_RE = re.compile(rf"^{_FLOAT}$")


def _finite(value: str, *, context: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{context}: non-numeric value {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{context}: non-finite value")
    return number


def _coerce(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""
    if raw.upper() in {"YES", "TRUE", "ON"}:
        return True
    if raw.upper() in {"NO", "FALSE", "OFF"}:
        return False
    if re.fullmatch(r"[+-]?\d+", raw):
        try:
            return int(raw)
        except ValueError:
            pass
    if _FLOAT_RE.fullmatch(raw):
        try:
            return float(raw)
        except ValueError:
            pass
    return raw


def _dms_to_degrees(value: str) -> float:
    token = value.strip()
    if _FLOAT_RE.fullmatch(token):
        return float(token)
    match = re.fullmatch(r"([+-]?)(\d+)[-:](\d+)[-:](\d+(?:\.\d*)?)", token)
    if not match:
        raise ValueError(f"invalid DMS angle {value!r}")
    sign, degrees, minutes, seconds = match.groups()
    result = int(degrees) + int(minutes) / 60.0 + float(seconds) / 3600.0
    return -result if sign == "-" else result


def parse_pts(content: str) -> list[dict[str, Any]]:
    """Parse native and mock-up STAR*NET coordinate files.

    Native files normally contain ``NAME E N H``. The seven-column
    ``NAME E N H sigmaE sigmaN sigmaH`` shape remains supported.
    """
    points: list[dict[str, Any]] = []
    for lineno, raw in enumerate(content.lstrip("\ufeff").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f".pts line {lineno}: expected at least 4 fields, got {len(parts)}")
        name = parts[0]
        e, n, h = (
            _finite(parts[1], context=f".pts line {lineno}"),
            _finite(parts[2], context=f".pts line {lineno}"),
            _finite(parts[3], context=f".pts line {lineno}"),
        )
        point: dict[str, Any] = {"name": name, "e": e, "n": n, "h": h}
        remainder = parts[4:]
        if len(remainder) >= 3 and all(_FLOAT_RE.fullmatch(value) for value in remainder[:3]):
            point.update(
                sigma_e=_finite(remainder[0], context=f".pts line {lineno}"),
                sigma_n=_finite(remainder[1], context=f".pts line {lineno}"),
                sigma_h=_finite(remainder[2], context=f".pts line {lineno}"),
            )
            remainder = remainder[3:]
        else:
            point.update(sigma_e=None, sigma_n=None, sigma_h=None)
        if remainder:
            point["description"] = " ".join(remainder)
        points.append(point)
    if not points:
        raise ValueError(".pts file contains no coordinate records")
    return points


def parse_err(content: str) -> dict[str, Any]:
    """Parse native STAR*NET error logs and the compact BTM test format."""
    summary: dict[str, Any] = {
        "warnings": [],
        "errors": [],
        "completed": False,
        "converged": False,
    }
    explicit_converged: bool | None = None
    for lineno, raw in enumerate(content.lstrip("\ufeff").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        upper = line.upper()
        if "STAR*NET" in upper and "ERROR LOG" in upper:
            summary["title"] = line
            version = re.search(r"VERSION\s+([\w.\-]+)", line, re.I)
            if version:
                summary["version"] = version.group(1)
            continue
        if upper.startswith("WARNING"):
            summary["warnings"].append(line[7:].strip(" :-"))
            continue
        if upper.startswith(("ERROR", "FATAL")):
            summary["errors"].append(line.split(None, 1)[1] if " " in line else line)
            continue
        completed = re.search(
            r"Network Processing Completed(?:\s+with\s+(\d+)\s+Warnings?)?", line, re.I
        )
        if completed:
            summary["completed"] = True
            if completed.group(1):
                summary["reported_warning_count"] = int(completed.group(1))
            summary["completion_message"] = line
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            summary.setdefault("messages", []).append(line)
            continue
        key, value = parts[0].upper(), parts[1].strip()
        if key == "CONVERGED":
            explicit_converged = value.upper() in {"YES", "TRUE", "1"}
        elif key in {"ITERATIONS", "RANK", "RANK_DEFICIENCY"}:
            summary[key.lower()] = int(value)
        elif key == "CHI2_STATUS":
            normalized = value.lower()
            if normalized not in {"passed", "failed", "not-applicable"}:
                raise ValueError(f".err line {lineno}: invalid CHI2_STATUS {value!r}")
            summary["chi_square_status"] = normalized
        elif key == "VARIANCE_FACTOR":
            summary["variance_factor"] = _finite(value, context=f".err line {lineno}")
        else:
            summary.setdefault("extra", {})[key] = _coerce(value)

    summary["warning_count"] = len(summary["warnings"])
    summary["error_count"] = len(summary["errors"])
    summary["converged"] = (
        explicit_converged
        if explicit_converged is not None
        else bool(summary["completed"] and not summary["errors"])
    )
    return summary


def parse_project(content: str) -> dict[str, Any]:
    """Parse `.prj` and `.snproj` section/key files."""
    result: dict[str, Any] = {"sections": {}, "comments": []}
    section: str | None = None
    for raw in content.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("*STAR*NET"):
            parts = line.split()
            result["format_version"] = int(parts[-1]) if parts[-1].isdigit() else parts[-1]
            continue
        if line.startswith("#"):
            comment = line[1:].strip()
            if comment:
                result["comments"].append(comment)
                if "software_version" not in result and re.fullmatch(r"\d+(?:\.\d+)+", comment):
                    result["software_version"] = comment
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            result["sections"].setdefault(section, {})
            continue
        if section is None:
            result.setdefault("preamble", []).append(line)
            continue
        parts = line.split(None, 1)
        key = parts[0]
        value = parts[1] if len(parts) == 2 else ""
        result["sections"][section][key] = _coerce(value)
    if not result["sections"]:
        raise ValueError("project file contains no sections")
    return result


def parse_dat(content: str) -> dict[str, Any]:
    """Parse the STAR*NET records used by BTM (`C`, `.SCALE`, `DB`, `DM`, `DE`)."""
    result: dict[str, Any] = {
        "coordinates": [],
        "observations": [],
        "comments": [],
        "unknown_records": [],
    }
    station: str | None = None
    for lineno, raw in enumerate(content.lstrip("\ufeff").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            comment = line[1:].strip()
            result["comments"].append(comment)
            lowered = comment.lower()
            if lowered.startswith("run time:"):
                result["run_time"] = comment.split(":", 1)[1].strip()
            elif lowered.startswith("epoch time:"):
                result["epoch_time"] = comment.split(":", 1)[1].strip()
            continue
        upper = line.upper()
        if upper.startswith(".SCALE"):
            parts = line.split()
            if len(parts) < 2:
                raise ValueError(f".dat line {lineno}: .SCALE requires a value")
            result["scale_factor"] = _finite(parts[1], context=f".dat line {lineno}")
            continue
        if upper.startswith("C "):
            parts = line.split()
            if len(parts) < 8:
                raise ValueError(f".dat line {lineno}: coordinate record requires 8 fields")
            result["coordinates"].append(
                {
                    "name": parts[1],
                    "e": _finite(parts[2], context=f".dat line {lineno}"),
                    "n": _finite(parts[3], context=f".dat line {lineno}"),
                    "h": _finite(parts[4], context=f".dat line {lineno}"),
                    "constraint_e": parts[5],
                    "constraint_n": parts[6],
                    "constraint_h": parts[7],
                }
            )
            continue
        if upper.startswith("DB "):
            station = line.split(None, 1)[1].strip()
            continue
        if upper == "DE":
            station = None
            continue
        if upper.startswith("DM "):
            if station is None:
                raise ValueError(f".dat line {lineno}: DM record outside DB/DE block")
            data, _, inline_comment = line.partition("#")
            parts = data.split()
            if len(parts) < 6:
                raise ValueError(
                    f".dat line {lineno}: DM requires target, direction, distance, zenith and HI/HT"
                )
            target, first, second, third = parts[1:5]
            # Native order: direction, distance, zenith. Preserve compatibility
            # with the previous mock-up order: direction, zenith, distance.
            if _FLOAT_RE.fullmatch(second) and not _FLOAT_RE.fullmatch(third):
                direction, distance, zenith = first, second, third
                tail = parts[5:]
            elif not _FLOAT_RE.fullmatch(second) and _FLOAT_RE.fullmatch(third):
                direction, zenith, distance = first, second, third
                tail = parts[5:]
            else:
                direction, distance, zenith = first, second, third
                tail = parts[5:]
            hi = ht = 0.0
            if tail:
                height_token = tail[-1]
                if "/" in height_token:
                    left, right = height_token.split("/", 1)
                    hi = _finite(left or "0", context=f".dat line {lineno}")
                    ht = _finite(right or "0", context=f".dat line {lineno}")
                elif len(tail) >= 2 and _FLOAT_RE.fullmatch(tail[-1]) and _FLOAT_RE.fullmatch(tail[-2]):
                    hi = _finite(tail[-2], context=f".dat line {lineno}")
                    ht = _finite(tail[-1], context=f".dat line {lineno}")
            direction_deg = _dms_to_degrees(direction)
            zenith_deg = _dms_to_degrees(zenith)
            result["observations"].append(
                {
                    "station": station,
                    "target": target,
                    "direction_dms": direction,
                    "direction_deg": direction_deg,
                    "direction_rad": math.radians(direction_deg),
                    "slope_distance_m": _finite(distance, context=f".dat line {lineno}"),
                    "zenith_dms": zenith,
                    "zenith_deg": zenith_deg,
                    "zenith_rad": math.radians(zenith_deg),
                    "instrument_height_m": hi,
                    "target_height_m": ht,
                    "comment": inline_comment.strip() or None,
                }
            )
            continue
        result["unknown_records"].append({"line": lineno, "content": line})
    return result


def parse_lst(content: str) -> dict[str, Any]:
    """Parse statistics, coordinates, uncertainties and residuals from `.lst`."""
    lines = content.lstrip("\ufeff").splitlines()
    result: dict[str, Any] = {
        "metadata": {},
        "settings": {},
        "summary": {},
        "points": [],
        "coordinate_changes": [],
        "residuals": [],
        "error_ellipses": [],
    }
    points: dict[str, dict[str, Any]] = {}
    state: str | None = None
    residual_kind: str | None = None

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue

        version = re.search(r"MicroSurvey\s+STAR\*NET(?:-PRO)?\s+Version\s+([\w.\-]+)", stripped, re.I)
        if version:
            result["metadata"]["version"] = version.group(1)
        run_date = re.match(r"Run Date:\s*(.+)", stripped, re.I)
        if run_date:
            result["metadata"]["run_date"] = run_date.group(1).strip()
        project_name = re.match(r"Project Name\s+(.+)", stripped, re.I)
        if project_name:
            result["metadata"]["project_name"] = project_name.group(1).strip()
        data_file = re.match(r"Data File List\s+\d+\.\s+(.+)", stripped, re.I)
        if data_file:
            result["metadata"].setdefault("data_files", []).append(data_file.group(1).strip())

        setting = re.match(r"(.+?)\s+:\s+(.+)$", stripped)
        if setting and state is None:
            result["settings"][setting.group(1).strip()] = _coerce(setting.group(2).strip())

        if "Adjustment Statistical Summary" in stripped:
            state = "summary"
            continue
        if "Coordinate Changes from Entered Provisionals" in stripped:
            state = "changes"
            continue
        if "Adjusted Coordinates" in stripped and "Observations" not in stripped:
            state = "coordinates"
            continue
        if "Adjusted Observations and Residuals" in stripped or "Adjusted Coordinate Observations" in stripped:
            state = None
            residual_kind = None
            continue
        if "Station Coordinate Standard Deviations" in stripped:
            state = "stddev"
            continue
        if "Station Coordinate Error Ellipses" in stripped:
            state = "ellipses"
            continue
        if "Adjusted Distance Observations" in stripped:
            state, residual_kind = "residuals", "distance"
            continue
        if "Adjusted Zenith Observations" in stripped:
            state, residual_kind = "residuals", "zenith"
            continue
        if "Adjusted Direction Observations" in stripped:
            state, residual_kind = "residuals", "direction"
            continue
        if re.match(r"(Adjusted Bearings|Relative Error Ellipses|End of File)", stripped):
            state = None
            residual_kind = None

        iterations = re.match(r"Iterations\s*=\s*(\d+)", stripped, re.I)
        if iterations:
            result["summary"]["iterations"] = int(iterations.group(1))
        counts = {
            "station_count": r"Number of Stations\s*=\s*(\d+)",
            "observation_count": r"Number of Observations\s*=\s*(\d+)",
            "unknown_count": r"Number of Unknowns\s*=\s*(\d+)",
            "redundant_observation_count": r"Number of Redundant Obs\s*=\s*(\d+)",
        }
        for key, pattern in counts.items():
            match = re.match(pattern, stripped, re.I)
            if match:
                result["summary"][key] = int(match.group(1))
        total = re.match(rf"Total\s+(\d+)\s+({_FLOAT})\s+({_FLOAT})", stripped, re.I)
        if total:
            result["summary"].update(
                total_observation_count=int(total.group(1)),
                sum_squared_standardized_residuals=float(total.group(2)),
                error_factor=float(total.group(3)),
            )
        chi = re.search(r"Chi-Square Test at\s+([0-9.]+)%\s+Level\s+(Passed|Failed)", stripped, re.I)
        if chi:
            result["summary"]["chi_square_significance_percent"] = float(chi.group(1))
            result["summary"]["chi_square_status"] = chi.group(2).lower()
        bounds = re.search(r"Lower/Upper Bounds\s*\(\s*([0-9.]+)\s*/\s*([0-9.]+)\s*\)", stripped, re.I)
        if bounds:
            result["summary"]["chi_square_lower_factor"] = float(bounds.group(1))
            result["summary"]["chi_square_upper_factor"] = float(bounds.group(2))

        if state == "changes":
            match = re.match(rf"(\S+)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})$", stripped)
            if match and match.group(1).lower() != "station":
                result["coordinate_changes"].append(
                    {
                        "name": match.group(1),
                        "delta_e": float(match.group(2)),
                        "delta_n": float(match.group(3)),
                        "delta_h": float(match.group(4)),
                    }
                )
        elif state == "coordinates":
            match = re.match(rf"(\S+)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})(?:\s+(.*))?$", stripped)
            if match and match.group(1).lower() != "station":
                point = points.setdefault(match.group(1), {"name": match.group(1)})
                point.update(e=float(match.group(2)), n=float(match.group(3)), h=float(match.group(4)))
                if match.group(5):
                    point["description"] = match.group(5).strip()
        elif state == "stddev":
            match = re.match(rf"(\S+)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})$", stripped)
            if match and match.group(1).lower() != "station":
                point = points.setdefault(match.group(1), {"name": match.group(1)})
                point.update(
                    sigma_e=float(match.group(2)),
                    sigma_n=float(match.group(3)),
                    sigma_h=float(match.group(4)),
                )
        elif state == "ellipses":
            match = re.match(rf"(\S+)\s+({_FLOAT})\s+({_FLOAT})\s+(\S+)\s+({_FLOAT})$", stripped)
            if match and match.group(1).lower() != "station":
                ellipse = {
                    "name": match.group(1),
                    "semi_major": float(match.group(2)),
                    "semi_minor": float(match.group(3)),
                    "azimuth": match.group(4),
                    "elevation_confidence": float(match.group(5)),
                }
                result["error_ellipses"].append(ellipse)
                points.setdefault(match.group(1), {"name": match.group(1)})["error_ellipse"] = ellipse
        elif state == "residuals" and residual_kind and not stripped.lower().startswith(("from ", "station ", "set ")):
            parts = stripped.split()
            if len(parts) >= 6 and _FLOAT_RE.fullmatch(parts[-1]) and _FLOAT_RE.fullmatch(parts[-2]):
                residual: dict[str, Any] = {
                    "kind": residual_kind,
                    "from": parts[0],
                    "to": parts[1],
                    "adjusted": parts[2],
                    "residual": parts[3],
                    "standard_error": float(parts[-2]),
                    "standardized_residual": float(parts[-1]),
                }
                if residual_kind == "distance":
                    residual["adjusted_value"] = float(parts[2])
                    residual["residual_value"] = float(parts[3])
                result["residuals"].append(residual)

    result["points"] = [point for point in points.values() if {"e", "n", "h"} <= point.keys()]
    if "chi_square_status" not in result["summary"]:
        result["summary"]["chi_square_status"] = "not-applicable"
    result["summary"]["converged"] = bool(result["summary"].get("iterations") is not None)
    if result["residuals"]:
        result["summary"]["max_standardized_residual"] = max(
            abs(float(row["standardized_residual"])) for row in result["residuals"]
        )
    return result
