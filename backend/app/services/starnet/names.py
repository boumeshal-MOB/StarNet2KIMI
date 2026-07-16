"""Deterministic STAR*NET engine names — `^[A-Za-z0-9_]{1,15}$`, unique per run."""

from __future__ import annotations

import re

_VALID = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def engine_name(physical_point_id: str, taken: set[str] | None = None) -> str:
    """Map a BTM physical point id to a stable, valid, collision-free name."""
    base = re.sub(r"[^A-Za-z0-9_]", "", physical_point_id)[:15] or "PT"
    candidate = base
    suffix = 1
    taken = taken if taken is not None else set()
    while candidate in taken or not _VALID.match(candidate):
        tag = f"_{suffix}"
        candidate = f"{base[: 15 - len(tag)]}{tag}"
        suffix += 1
    taken.add(candidate)
    return candidate
