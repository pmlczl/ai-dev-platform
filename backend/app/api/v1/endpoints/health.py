"""Health endpoints.

``GET /api/v1/health``      - liveness, never touches the database.
``GET /api/v1/health/ready`` - readiness, probes the database connection.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.health import DatabaseHealth, HealthResponse, ReadinessResponse

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns basic service metadata. It does not depend on any downstream service.",
)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Checks that the service can reach its database. Returns 503 when it is down.",
)
async def readiness(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReadinessResponse:
    started_at = time.perf_counter()
    database_status = "ok"
    latency_ms: float | None = None

    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    except (SQLAlchemyError, OSError) as exc:
        # SQLAlchemy errors cover driver/DB problems; OSError covers connection
        # level failures (refused, reset, timeout) that the async drivers raise
        # unwrapped.
        logger.warning("Database readiness probe failed: %s", exc)
        database_status = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ok" if database_status == "ok" else "not_ready",
        database=DatabaseHealth(status=database_status, latency_ms=latency_ms),
        timestamp=datetime.now(UTC),
    )
