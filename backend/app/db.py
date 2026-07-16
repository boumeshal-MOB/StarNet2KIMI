"""Persistence adapter for the demo API.

SQLite remains a stand-in for the BTM database. On Vercel the writable database
is created in `/tmp`; production BTM supplies its own `BTM_DATABASE_URL`.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

if os.environ.get("VERCEL"):
    DEFAULT_DB = Path("/tmp/btm_topographic_adjustment.sqlite")
else:
    DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "btm_demo.sqlite"

DATABASE_URL = os.environ.get("BTM_DATABASE_URL", f"sqlite:///{DEFAULT_DB}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
