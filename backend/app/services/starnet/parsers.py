"""Parse native STAR*NET outputs.

``.pts`` — adjusted coordinates with component standard deviations;
``.err`` — station error summary lines (non-fatal convergence flags).

The production worker feeds real files; the demo engine emits the same shapes
so the ingestion path is identical and tested.
"""

from __future__ import annotations

import math
from typing import Any


def parse_pts(content: str) -> list[dict[str, Any]]:
    """Parse ``NAME E N H sigmaE sigmaN sigmaH`` lines (``#`` = comment)."""
    points: list[dict[str, Any]] = []
    for lineno, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 7:
            raise ValueError(f".pts line {lineno}: expected 7 fields, got {len(parts)}")
        name = parts[0]
        try:
            e, n, h, se, sn, sh = (float(value) for value in parts[1:])
        except ValueError as exc:
            raise ValueError(f".pts line {lineno}: non-numeric coordinate or sigma") from exc
        if not all(math.isfinite(v) for v in (e, n, h, se, sn, sh)):
            raise ValueError(f".pts line {lineno}: non-finite value")
        points.append({"name": name, "e": e, "n": n, "h": h, "sigma_e": se, "sigma_n": sn, "sigma_h": sh})
    if not points:
        raise ValueError(".pts file contains no coordinate records")
    return points


def parse_err(content: str) -> dict[str, Any]:
    """Parse the ``.err`` summary: ``KEY VALUE`` lines.

    Recognised keys: CONVERGED, ITERATIONS, CHI2_STATUS, VARIANCE_FACTOR,
    RANK, RANK_DEFICIENCY, WARNING (repeatable).
    """
    summary: dict[str, Any] = {"warnings": []}
    for lineno, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f".err line {lineno}: expected KEY VALUE")
        key, value = parts[0].upper(), parts[1].strip()
        if key == "WARNING":
            summary["warnings"].append(value)
        elif key in {"CONVERGED"}:
            summary[key.lower()] = value.upper() in {"YES", "TRUE", "1"}
        elif key in {"ITERATIONS", "RANK", "RANK_DEFICIENCY"}:
            summary[key.lower()] = int(value)
        elif key == "CHI2_STATUS":
            if value not in {"passed", "failed", "not-applicable"}:
                raise ValueError(f".err line {lineno}: invalid CHI2_STATUS {value!r}")
            summary["chi_square_status"] = value
        elif key == "VARIANCE_FACTOR":
            summary["variance_factor"] = float(value)
        else:
            summary.setdefault("extra", {})[key] = value
    return summary
