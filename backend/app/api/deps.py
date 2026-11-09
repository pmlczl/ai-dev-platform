"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query, Request

from app.core.database import get_db
from app.core.exceptions import ServiceUnavailableException
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PageParams
from app.services.workflow_runtime import WorkflowRuntime

__all__ = ["get_db", "get_workflow_runtime", "pagination_params"]


def get_workflow_runtime(request: Request) -> WorkflowRuntime:
    """Return the workflow runtime of the running application.

    The runtime is owned by the application instance, because the checkpointer
    holds a connection that belongs to the event loop of the application. The
    dependency therefore reads it from the state of the app and never from a
    process wide singleton.
    """

    runtime = getattr(request.app.state, "workflow_runtime", None)
    if runtime is None:
        raise ServiceUnavailableException("工作流运行时尚未就绪")
    return runtime


def pagination_params(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Number of items per page (1-{MAX_PAGE_SIZE})",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    """Build the pagination parameters from the query string.

    The bounds are declared here so that an out of range value is rejected by
    FastAPI and rendered with the unified error envelope.
    """

    return PageParams(page=page, page_size=page_size)
