"""Single Vercel FastAPI entrypoint for the interactive BTM demonstration.

Vercel is explicitly configured to deploy this repository as one FastAPI
application. The backend serves the compiled Vite frontend as well as every
``/api`` route, avoiding a separate frontend/function routing table.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "core"))
os.environ.setdefault("VERCEL", "1")

from app.main import app  # noqa: E402,F401
