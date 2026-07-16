import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "core"))
sys.path.insert(0, str(BACKEND))

os.environ["BTM_DATABASE_URL"] = "sqlite:////tmp/btm_test_suite.sqlite"
if Path("/tmp/btm_test_suite.sqlite").exists():
    Path("/tmp/btm_test_suite.sqlite").unlink()

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session")
def db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()
