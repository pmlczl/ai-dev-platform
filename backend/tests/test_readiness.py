"""Tests for the readiness probe (database connectivity)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import get_db
from app.main import create_app


@pytest.fixture()
def sqlite_client(tmp_path):
    """Application whose database dependency points at a local SQLite file."""

    db_path = (tmp_path / "readiness.db").as_posix()
    # NullPool keeps no connection open, so the temporary file stays unlocked.
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class _BrokenSession:
    """Session double that always fails, simulating an unreachable database."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self, *args, **kwargs):
        raise self._error


def test_readiness_reports_a_reachable_database(sqlite_client):
    response = sqlite_client.get("/api/v1/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["status"] == "ok"
    assert payload["database"]["latency_ms"] is not None


@pytest.mark.parametrize(
    "error",
    [
        SQLAlchemyError("database is down"),
        ConnectionRefusedError("connection refused"),
    ],
    ids=["driver_error", "connection_error"],
)
def test_readiness_returns_503_when_the_database_is_unreachable(error):
    app = create_app()

    async def override_get_db():
        yield _BrokenSession(error)

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["database"]["status"] == "unavailable"
