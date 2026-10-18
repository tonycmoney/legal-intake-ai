import os
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.public import get_llm  # noqa: E402
from app.security import limiter  # noqa: E402
from tests.fakes import FakeLLM  # noqa: E402

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def settings():
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        anthropic_api_key="test-key",
        staff_password=PASSWORD,
    )


@pytest.fixture()
def fake_llm():
    return FakeLLM([])


@pytest.fixture()
def client(settings, fake_llm):
    Base.metadata.drop_all(engine)
    limiter.reset()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def staff(client):
    assert client.post("/api/staff/login", json={"password": PASSWORD}).status_code == 204
    return client
