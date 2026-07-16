"""SQLite persistence — the demo stand-in for the BTM database.

Everything the spec calls "the BTM database is the source of truth" lives here:
raw observations, environment readings, versioned configurations, runs and
published output values.  STAR*NET files never persist as truth.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "btm_demo.sqlite"
DATABASE_URL = os.environ.get("BTM_DATABASE_URL", f"sqlite:///{DEFAULT_DB}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
