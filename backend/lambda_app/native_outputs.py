"""Ingest native STAR*NET worker artifacts into the BTM Lambda contract."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

try:  # Lambda image copies the adapter package to /var/task/starnet.
    from starnet import parse_dat, parse_err, parse_lst, parse_project, parse_pts
except ImportError:  # Local repository/tests.
    from app.services.starnet import parse_dat, parse_err, parse_lst, parse_project, parse_pts

from .contracts import ContractError, require_mapping


def parse_native_outputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Parse and reconcile STAR*NET files returned by the licensed worker.

    `.PTS` remains the preferred source for full-precision coordinates. `.LST`
    enriches those coordinates with standard deviations, ellipses, residuals and
    the Chi-square result. `.ERR` contributes warnings and fatal errors.
    """
    pts_text = payload.get("pts")
    lst_text = payload.get("lst")
    err_text = payload.get("err")
    if not isinstance(pts_text, str) and not isinstance(lst_text, str):
        raise ContractError("payload.pts or payload.lst must be provided as text")

    listing = parse_lst(lst_text) if isinstance(lst_text, str) and lst_text.strip() else None
    if isinstance(pts_text, str) and pts_text.strip():
        points = parse_pts(pts_text)
    elif listing is not None:
        points = [dict(point) for point in listing["points"]]
    else:  # guarded above
        points = []

    if listing is not None:
        listed_by_name = {str(point["name"]): point for point in listing["points"]}
        for point in points:
            listed = listed_by_name.get(str(point["name"]))
            if listed is None:
                continue
            for key in ("sigma_e", "sigma_n", "sigma_h", "error_ellipse", "description"):
                if point.get(key) is None and listed.get(key) is not None:
                    point[key] = listed[key]

    error_log = parse_err(err_text) if isinstance(err_text, str) and err_text.strip() else None
    summary: dict[str, Any] = {}
    if error_log is not None:
        summary.update(error_log)
    if listing is not None:
        listing_summary = listing["summary"]
        summary.update({key: value for key, value in listing_summary.items() if value is not None})
        if error_log is not None:
            summary["warnings"] = error_log.get("warnings", [])
            summary["errors"] = error_log.get("errors", [])
            summary["warning_count"] = error_log.get("warning_count", 0)
            summary["error_count"] = error_log.get("error_count", 0)
            summary["completed"] = error_log.get("completed", False)
            if error_log.get("errors"):
                summary["converged"] = False
    summary.setdefault("warnings", [])
    summary.setdefault("errors", [])
    summary.setdefault("chi_square_status", "not-applicable")
    summary.setdefault("converged", not summary["errors"] and bool(points))

    names = require_mapping(payload.get("engine_names", {}), "payload.engine_names")
    inverse = {str(engine_name): str(point_id) for point_id, engine_name in names.items()}
    for point in points:
        point["physical_point_id"] = inverse.get(str(point["name"]), str(point["name"]))

    project_text = payload.get("snproj") if isinstance(payload.get("snproj"), str) else payload.get("prj")
    project = parse_project(project_text) if isinstance(project_text, str) and project_text.strip() else None
    data_file = parse_dat(payload["dat"]) if isinstance(payload.get("dat"), str) and payload["dat"].strip() else None

    sbf: dict[str, Any] | None = None
    if isinstance(payload.get("sbf_base64"), str) and payload["sbf_base64"]:
        try:
            raw = base64.b64decode(payload["sbf_base64"], validate=True)
        except ValueError as exc:
            raise ContractError("payload.sbf_base64 is not valid base64") from exc
        sbf = {
            "present": True,
            "size_bytes": len(raw),
            "parsed": False,
            "reason": "SBF is a proprietary binary support file; BTM stores it as an artifact.",
        }

    return {
        "points": points,
        "summary": summary,
        "listing": listing,
        "error_log": error_log,
        "project": project,
        "input_data": data_file,
        "sbf": sbf,
        "artifacts": {
            "pts": isinstance(pts_text, str) and bool(pts_text.strip()),
            "lst": listing is not None,
            "err": error_log is not None,
            "prj_or_snproj": project is not None,
            "dat": data_file is not None,
            "sbf": sbf is not None,
        },
    }
