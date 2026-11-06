"""Development task table - the unit of work inside a project."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import TaskPriority, TaskStatus, sql_values

if TYPE_CHECKING:
    # Only needed for the type checker: at runtime SQLAlchemy resolves the
    # annotation through the declarative registry.
    from app.models.project import Project


class DevelopmentTask(Base, TimestampMixin):
    """A development task that always belongs to a project.

    ``seq`` is the position of the task inside its project (``1``, ``2``, ...).
    It is allocated by the atomic counter kept on ``projects.task_sequence``
    and is unique per project, so a task can be addressed as ``PRJ-1-3``.
    """

    __tablename__ = "development_tasks"

    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_values(TaskStatus)})",
            name="status_valid",
        ),
        CheckConstraint(
            f"priority IN ({sql_values(TaskPriority)})",
            name="priority_valid",
        ),
        CheckConstraint("seq >= 1", name="seq_valid"),
        UniqueConstraint("project_id", "seq", name="uq_development_tasks_project_seq"),
        Index("ix_development_tasks_project_id", "project_id"),
        Index("ix_development_tasks_status", "status"),
        Index("ix_development_tasks_project_id_status", "project_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskStatus.PENDING.value,
    )
    priority: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TaskPriority.MEDIUM.value,
    )
    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    project: Mapped[Project] = relationship(
        back_populates="tasks",
    )
