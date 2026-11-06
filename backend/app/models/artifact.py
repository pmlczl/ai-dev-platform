"""Artifact table - metadata of the files a project produces."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import ArtifactReviewStatus, ArtifactStage, sql_values


class Artifact(Base, TimestampMixin):
    """Metadata of a file that belongs to a project.

    Only metadata is stored - the platform keeps the relative path inside the
    project workspace, never an absolute path. ``version`` together with
    ``relative_path`` identifies one revision of a file, and ``sha256`` makes
    the content verifiable without opening the file.

    A new revision is appended as a new row; the previous revision is then
    marked as ``superseded`` instead of being overwritten.

    ``storage_path`` is the location of the file on disk, relative to the
    configured storage root. It is ``NULL`` for artifacts that were only
    registered as metadata without a physical file.
    """

    __tablename__ = "artifacts"

    __table_args__ = (
        CheckConstraint(
            f"review_status IN ({sql_values(ArtifactReviewStatus)})",
            name="review_status_valid",
        ),
        CheckConstraint(
            f"stage IN ({sql_values(ArtifactStage)})",
            name="stage_valid",
        ),
        CheckConstraint("version >= 1", name="version_valid"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes_valid"),
        UniqueConstraint(
            "project_id",
            "relative_path",
            "version",
            name="uq_artifacts_project_path_version",
        ),
        UniqueConstraint(
            "storage_path",
            name="uq_artifacts_storage_path",
        ),
        Index("ix_artifacts_project_id", "project_id"),
        Index("ix_artifacts_project_id_task_id", "project_id", "task_id"),
        Index("ix_artifacts_task_id", "task_id"),
        Index("ix_artifacts_workflow_instance_id", "workflow_instance_id"),
        Index("ix_artifacts_sha256", "sha256"),
        Index("ix_artifacts_review_status", "review_status"),
        Index("ix_artifacts_stage", "stage"),
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
    workflow_instance_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workflow_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ArtifactReviewStatus.PENDING.value,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ArtifactStage.DEVELOPMENT.value,
        server_default=ArtifactStage.DEVELOPMENT.value,
    )
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
