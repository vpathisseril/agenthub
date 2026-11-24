"""Test fixtures: isolated SQLite DB per test, fake LLM, helpers to sign in."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="agenthub-test-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "ADMIN_EMAIL": "admin@example.com",
        "ADMIN_PASSWORD": "Admin-Pass-2026",
        "LLM_FAKE_MODE": "true",
        "SECRET_KEY": "test-secret-key-not-for-prod",
        "ADMIN_NOTIFY_EMAIL": "owner@example.com",
        "APP_BASE_URL": "https://agenthub.test",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app, bootstrap  # noqa: E402
from app.services import agents, notify  # noqa: E402

STRONG_PW = "Str0ng-Password-1"


@pytest.fixture(autouse=True)
def fresh_db() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    ratelimit.reset()
    agents.clear_cache()
    notify.sent.clear()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def csrf(client: TestClient, path: str = "/login") -> str:
    html = client.get(path).text
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert m, f"no csrf token on {path}"
    return m.group(1)


def login(client: TestClient, email: str, password: str) -> None:
    token = csrf(client)
    r = client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def signup(
    client: TestClient,
    email: str = "pat@example.com",
    password: str = STRONG_PW,
    name: str = "Pat Lee",
) -> object:
    token = csrf(client, "/signup")
    return client.post(
        "/signup",
        data={"full_name": name, "email": email, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


def admin_client(client: TestClient) -> TestClient:
    login(client, "admin@example.com", "Admin-Pass-2026")
    return client
