"""Read models for workflow instances."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import WorkflowStatus


class WorkflowInstanceRead(BaseModel):
    """A workflow instance as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    task_id: UUID | None = None
    workflow_key: str
    status: WorkflowStatus
    current_step: str | None = None
    state: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
