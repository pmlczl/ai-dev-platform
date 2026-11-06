"""Project table - the root of the project management domain."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ProjectStatus, sql_values

if TYPE_CHECKING:
    # Only needed for the type checker: at runtime SQLAlchemy resolves the
    # annotation through the declarative registry.
    from app.models.task import DevelopmentTask


class Project(Base, TimestampMixin):
    """A managed project.

    Every development task belongs to exactly one project, so the project is
    the aggregate root of the task management domain. Deleting a project is a
    soft delete: ``deleted_at`` is stamped and the row disappears from the API
    while the approval history stays intact.
    """

    __tablename__ = "projects"

    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_values(ProjectStatus)})",
            name="status_valid",
        ),
        CheckConstraint("task_sequence >= 0", name="task_sequence_valid"),
        Index("ix_projects_status", "status"),
        Index("ix_projects_created_at", "created_at"),
        Index("ix_projects_deleted_at", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProjectStatus.PLANNING.value,
    )
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    task_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    tasks: Mapped[list[DevelopmentTask]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
