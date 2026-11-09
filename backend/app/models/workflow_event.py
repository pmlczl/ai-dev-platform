"""Workflow event log - an append only trail of what a workflow instance did.

The log is the platform's own record; it is *not* a view on the LangGraph
checkpointer. The browser therefore never sees the internal state of the graph,
only the curated events the workflow wrote for it.

``event_key`` makes writing an event idempotent. A node that is replayed after
a restart (LangGraph re-executes the node that called ``interrupt()``) writes
the very same key, and the unique constraint turns the second insert into a
no-op instead of a duplicated entry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkflowEvent(Base):
    """One entry of the event log of a workflow instance."""

    __tablename__ = "workflow_events"

    __table_args__ = (
        UniqueConstraint(
            "workflow_instance_id",
            "event_key",
            name="uq_workflow_events_instance_event_key",
        ),
        UniqueConstraint(
            "workflow_instance_id",
            "sequence",
            name="uq_workflow_events_instance_sequence",
        ),
        Index(
            "ix_workflow_events_workflow_instance_id_created_at",
            "workflow_instance_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_instance_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(postgresql.JSONB, "postgresql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
