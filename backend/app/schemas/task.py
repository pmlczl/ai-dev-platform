"""Request and response models for the task endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    """Payload for creating a development task.

    ``project_id`` is mandatory: a task always belongs to a project.
    """

    project_id: UUID
    title: str = Field(min_length=1, max_length=300, examples=["实现项目列表分页接口"])
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    assignee: str | None = Field(default=None, max_length=120)


class TaskUpdate(BaseModel):
    """Payload for updating a task.

    The project a task belongs to cannot be changed here - moving a task to
    another project would change its ``seq`` and its history.
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee: str | None = Field(default=None, max_length=120)


class TaskRead(BaseModel):
    """A development task as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    seq: int
    title: str
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority
    assignee: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    created_at: datetime
    updated_at: datetime
