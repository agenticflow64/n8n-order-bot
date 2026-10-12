import os
import sys
import tempfile
from pathlib import Path

# DATABASE_PATH должен быть задан до импорта app.*
_TMPDIR = tempfile.mkdtemp(prefix="orderbot-tests-")
os.environ["DATABASE_PATH"] = os.path.join(_TMPDIR, "test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Order  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
    # чистим таблицу между тестами
    s = SessionLocal()
    s.query(Order).delete()
    s.commit()
    s.close()
