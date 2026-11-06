"""Workflow instance table - one run of a registered workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import WorkflowStatus, sql_values


class WorkflowInstance(Base, TimestampMixin):
    """A single execution of a workflow registered in the workflow registry.

    The table is deliberately passive: it stores the bookkeeping of a run
    (status, current step, serialized state) so that the approval flow and the
    operations log have a durable anchor. The workflow graph itself is built by
    the runtime, never here.

    ``task_id`` is nullable: a NULL value marks a project level workflow that
    is not bound to a single task.
    """

    __tablename__ = "workflow_instances"

    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_values(WorkflowStatus)})",
            name="status_valid",
        ),
        Index("ix_workflow_instances_project_id", "project_id"),
        Index("ix_workflow_instances_task_id", "task_id"),
        Index("ix_workflow_instances_status", "status"),
        Index("ix_workflow_instances_project_id_status", "project_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("development_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    workflow_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkflowStatus.PENDING.value,
    )
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(postgresql.JSONB, "postgresql"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
