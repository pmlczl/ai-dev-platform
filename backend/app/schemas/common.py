"""Shared schema helpers: pagination parameters and the paginated envelope."""

from __future__ import annotations

from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

#: Default number of items returned by a list endpoint.
DEFAULT_PAGE_SIZE = 20
#: Upper bound for ``page_size`` so that a single request cannot load the table.
MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    """Pagination parameters accepted by every list endpoint."""

    page: int = Field(default=1, ge=1, description="1-based page number")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Number of items per page (1-{MAX_PAGE_SIZE})",
    )

    @property
    def offset(self) -> int:
        """Number of rows to skip to reach the requested page."""

        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Maximum number of rows to read."""

        return self.page_size


class Page(BaseModel, Generic[T]):
    """Envelope returned by the paginated list endpoints."""

    items: list[T] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1)
    pages: int = Field(default=0, ge=0)


def build_page(items: list[T], total: int, params: PageParams) -> Page[T]:
    """Wrap a slice of items and the total row count into the page envelope."""

    pages = ceil(total / params.page_size) if params.page_size else 0
    return Page[T](
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=pages,
    )
