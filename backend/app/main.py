"""Application entry point.

Run locally with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, dispose_engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import AccessLogMiddleware, RequestContextMiddleware
from app.services.workflow_runtime import WorkflowRuntime
from app.services.workflow_store import reconcile_interrupted_instances

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    errors = settings.runtime_errors()
    if errors:
        for error in errors:
            logger.error("Configuration error: %s", error)
        raise RuntimeError("Invalid configuration: " + "; ".join(errors))

    logger.info(
        "Starting %s v%s (environment=%s)",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    logger.info("Database DSN: %s", settings.masked_database_uri)

    # The runtime belongs to this application instance: the checkpointer
    # opens its connection in the event loop of the application, so it has to
    # be opened and closed together with it.
    runtime = WorkflowRuntime()
    await runtime.startup()
    app.state.workflow_runtime = runtime

    try:
        async with SessionLocal() as session:
            recovered = await reconcile_interrupted_instances(session)
        if recovered:
            logger.info("Recovered %s workflow instance(s) after the restart", len(recovered))
    except Exception:  # pragma: no cover - the schema may not exist yet
        logger.warning("Could not reconcile the workflow instances", exc_info=True)

    try:
        yield
    finally:
        app.state.workflow_runtime = None
        await runtime.shutdown()
        await dispose_engine()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""

    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Backend API of the AI development platform. "
            "Module layout: api / core / models / schemas / services / workflows / agents."
        ),
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )

    # Middleware is executed bottom-up: CORS is the outermost layer.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_method_list,
        allow_headers=settings.cors_header_list,
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": settings.docs_url,
        }

    return app


app = create_app()
