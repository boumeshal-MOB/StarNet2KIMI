"""Vercel FastAPI entrypoint for the full interactive demo."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "core"))
os.environ.setdefault("VERCEL", "1")

from app.main import app  # noqa: E402,F401
