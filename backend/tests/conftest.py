"""Shared pytest fixtures.

The test database is injected into the environment *before* the application is
imported: ``app.core.database`` builds its engine at import time from the
settings, so the DSN has to be known by then.

By default the suite runs against a throw away SQLite file, so the database of
a developer is never touched. Point ``TEST_DATABASE_URL`` at PostgreSQL to run
the very same suite against the real engine::

    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db_test \\
        python -m pytest -q

The schema is created by running the real Alembic migrations in a subprocess,
not by ``metadata.create_all`` - the tests therefore exercise the migration
scripts as well.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: Directory holding the throw away database of the test session.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-dev-platform-tests-"))
#: DSN of the test database; ``TEST_DATABASE_URL`` wins when it is set.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or (
    f"sqlite+aiosqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
)

# The engine is built at import time, so the DSN has to be in the environment
# before the application modules are loaded.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.database import SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402

if engine.dialect.name == "sqlite":
    # Write ahead logging lets the HTTP client write while a service level
    # test still holds a read transaction open.
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Create the schema with the Alembic migrations and tear it down again."""

    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
    )
    try:
        yield
    finally:
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=BACKEND_DIR,
            env=env,
            check=False,
        )
        shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def app():
    """Application instance shared by the test session."""

    return create_app()


@pytest.fixture(scope="session")
def client(app):
    """HTTP client with the application lifespan running."""

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    """Database session for the service level tests."""

    async with SessionLocal() as session:
        yield session


@pytest.fixture()
def unique_code() -> str:
    """A project code that no other test in the session can collide with."""

    return f"PRJ-{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def project_payload(unique_code: str) -> dict[str, object]:
    """A minimal valid project payload."""

    return {
        "code": unique_code,
        "name": "自动化测试项目",
        "description": "由 pytest 创建",
        "owner": "tester",
    }
