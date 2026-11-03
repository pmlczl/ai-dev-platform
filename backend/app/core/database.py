"""Database engine, session factory and declarative base.

The engine is created lazily from the environment driven settings; the DSN is
never hard-coded. SQLite is supported as well so that the Alembic wiring can
be smoke tested without a PostgreSQL server.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.base import Base

logger = get_logger(__name__)

__all__ = ["Base", "SessionLocal", "dispose_engine", "engine", "get_db"]

settings = get_settings()


def _engine_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "pool_pre_ping": settings.db_pool_pre_ping,
    }
    if settings.uses_sqlite:
        # SQLite has no server side pool to tune.
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
        )
    return kwargs


engine = create_async_engine(settings.sqlalchemy_database_uri, **_engine_kwargs())

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""

    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    """Close all pooled connections (called on application shutdown)."""

    await engine.dispose()
    logger.info("Database engine disposed")
