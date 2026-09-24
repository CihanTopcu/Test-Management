"""Test fixtures.

The suite runs against its own database, whose schema is dropped and rebuilt
at the start of the session. Running it against the real one is not an
option: that holds five years of migrated history, and half of these tests
exist precisely to check how far a delete reaches.
"""
import os
import secrets
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


# A guard, not a convenience: these tests drop the public schema, and the
# real database is one typo away in the same .env.
TEST_DATABASE_NAMES = {"testmgmt_test", "testmgmt_ci"}


def _configured_url() -> str:
    """The database URL, wherever it is configured.

    pytest usually runs from backend/, and the .env that holds the real
    credentials sits one level up next to docker-compose.yml, so
    pydantic-settings never finds it and falls back to the placeholder.
    """
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]

    for candidate in (BACKEND / ".env.test", BACKEND.parent / ".env.test",
                      BACKEND / ".env", BACKEND.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL" and value.strip():
                return value.strip()

    from app.config import get_settings
    return get_settings().database_url


@pytest.fixture(scope="session")
def database_url() -> str:
    """The test database, wiped clean before the session runs.

    It is a separate database (testmgmt_test by default) rather than a
    per-session one: the application role has no CREATEDB, which is the right
    privilege for it to have, so the suite resets the schema it owns instead.
    ops/mktestdb creates the database once.
    """
    url = _configured_url()
    if url.rsplit("/", 1)[-1] not in TEST_DATABASE_NAMES:
        raise RuntimeError(
            f"{url!r} bir test veritabani degil. TEST_DATABASE_URL ile"
            f" {TEST_DATABASE_NAMES} adlarindan birini gosterin -- bu testler"
            " semayi silip yeniden kuruyor.")

    engine = create_engine(url, isolation_level="AUTOCOMMIT", future=True)
    with engine.connect() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return url


@pytest.fixture(scope="session")
def app_client(database_url):
    """The application, wired to the test database.

    The environment is set before app.config is imported anywhere, because
    get_settings() is cached for the life of the process.
    """
    storage = tempfile.mkdtemp(prefix="tm-test-attachments-")
    os.environ["DATABASE_URL"] = database_url
    os.environ["STORAGE_DIR"] = storage
    os.environ["BOOTSTRAP_EMAIL"] = "admin@test.local"
    os.environ["BOOTSTRAP_PASSWORD"] = "test-parola-123"
    os.environ["SECRET_KEY"] = secrets.token_hex(16)
    # the suite drives the same endpoints far harder than a person would
    os.environ["RATE_LIMIT_ENABLED"] = "false"

    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def admin(app_client) -> dict:
    """Authorization header for the bootstrapped administrator."""
    response = app_client.post("/api/auth/token", data={
        "username": "admin@test.local", "password": "test-parola-123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def project(app_client, admin) -> dict:
    """A fresh project per test, so nothing leaks between them."""
    name = f"Test projesi {secrets.token_hex(3)}"
    response = app_client.post("/api/projects", headers=admin,
                               json={"name": name, "suite_mode": 3})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def suite(app_client, admin, project) -> dict:
    response = app_client.post(f"/api/projects/{project['id']}/suites",
                               headers=admin, json={"name": "Suite"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def section(app_client, admin, suite) -> dict:
    response = app_client.post("/api/sections", headers=admin,
                               json={"suite_id": suite["id"], "name": "Bölüm"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def db(app_client):
    """A session on the same database, for the few tests that need to set up
    something the API deliberately will not -- a result dated last year, for
    instance, when created_on is always now()."""
    from sqlalchemy.orm import Session

    from app.db import engine
    with Session(engine) as session:
        yield session


@pytest.fixture
def make_case(app_client, admin, section):
    def _make(title="Örnek case", **extra):
        response = app_client.post("/api/cases", headers=admin, json={
            "section_id": section["id"], "title": title, **extra})
        assert response.status_code == 201, response.text
        return response.json()
    return _make
