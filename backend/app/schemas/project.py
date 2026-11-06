"""Request and response models for the project endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectStatus

#: Project codes are used in file names and URLs, so they stay restricted.
CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class ProjectCreate(BaseModel):
    """Payload for creating a project."""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=CODE_PATTERN,
        examples=["PRJ-2026-001"],
    )
    name: str = Field(min_length=1, max_length=200, examples=["AI 研发平台"])
    description: str | None = Field(default=None, max_length=5000)
    status: ProjectStatus = Field(default=ProjectStatus.PLANNING)
    owner: str | None = Field(default=None, max_length=120)


class ProjectUpdate(BaseModel):
    """Payload for updating a project.

    Every field is optional; only the fields that are actually present in the
    request body are written.
    """

    code: str | None = Field(default=None, min_length=1, max_length=64, pattern=CODE_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: ProjectStatus | None = None
    owner: str | None = Field(default=None, max_length=120)


class ProjectRead(BaseModel):
    """A project as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None = None
    status: ProjectStatus
    owner: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectListItem(ProjectRead):
    """A project in a list, enriched with the number of its tasks."""

    task_count: int = Field(default=0, ge=0)
