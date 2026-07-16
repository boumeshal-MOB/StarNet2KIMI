"""BTM Topographic Adjustment — FastAPI application.

Serves the REST API and the built frontend.  The Python engine computes;
SQLite stands in for the BTM database (raw_data, versioned configs, outputs).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Vendored scientific core (btm_topography).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from .api import analysis, demo, meta, processings, runs  # noqa: E402
from .db import Base, SessionLocal, engine  # noqa: E402
from .seed import seed_if_empty  # noqa: E402

app = FastAPI(title="BTM Topographic Adjustment", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(processings.router)
app.include_router(runs.router)
app.include_router(analysis.router)
app.include_router(demo.router)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "engine": "python-lsq-v1"}


DIST = Path(__file__).resolve().parent.parent.parent / "dist"

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = DIST / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
