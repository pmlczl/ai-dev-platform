"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query

from app.core.database import get_db
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PageParams

__all__ = ["get_db", "pagination_params"]


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
