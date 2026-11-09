"""Approval record table - an append only audit trail."""

from __future__ import annotations

from datetime import datetime
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ApprovalDecision, ApprovalTargetType, sql_values


class ApprovalRecord(Base):
    """One approval decision, appended and never modified.

    The table has no ``updated_at`` column on purpose: a record is written
    once and stays exactly as it was written. The order of the decisions for
    one target is given by ``sequence``, which is unique per target.

    ``target_type`` plus ``target_id`` is a polymorphic reference - a record
    can point at a task, an artifact or a workflow instance. It cannot be a
    real foreign key, so the service layer validates that the target exists.
    """

    __tablename__ = "approval_records"

    __table_args__ = (
        CheckConstraint(
            f"target_type IN ({sql_values(ApprovalTargetType)})",
            name="target_type_valid",
        ),
        CheckConstraint(
            f"decision IN ({sql_values(ApprovalDecision)})",
            name="decision_valid",
        ),
        CheckConstraint("sequence >= 1", name="sequence_valid"),
        UniqueConstraint(
            "target_type",
            "target_id",
            "sequence",
            name="uq_approval_records_target_sequence",
        ),
        # A unique index instead of a unique constraint: SQLite cannot add a
        # constraint to an existing table. Rows without an idempotency key
        # carry a NULL, and NULLs never collide in a unique index.
        Index(
            "uq_approval_records_target_idempotency",
            "target_type",
            "target_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_approval_records_project_id", "project_id"),
        Index("ix_approval_records_target_type_target_id", "target_type", "target_id"),
        Index("ix_approval_records_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        # RESTRICT on purpose: an audit trail must not disappear together with
        # the object it describes.
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Optional client supplied key that makes a repeated submission a no-op.
    #: ``NULL`` means "not idempotency guarded" - the column stays part of the
    #: unique index, and SQL treats NULLs as distinct in both PostgreSQL and
    #: SQLite, so records without a key never collide.
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
