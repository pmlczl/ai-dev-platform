"""Request and response models for artifact metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ArtifactReviewStatus, ArtifactStage

#: A SHA256 digest is exactly 64 hexadecimal characters.
SHA256_PATTERN = r"^[0-9a-fA-F]{64}$"


class ArtifactRegister(BaseModel):
    """Payload for registering the metadata of a file.

    Only the relative path inside the project workspace is stored - absolute
    paths would leak the layout of the host and break when the workspace moves.
    """

    project_id: UUID
    relative_path: str = Field(min_length=1, max_length=500, examples=["docs/prd.md"])
    sha256: str = Field(min_length=64, max_length=64, pattern=SHA256_PATTERN)
    file_type: str = Field(min_length=1, max_length=100, examples=["text/markdown"])
    size_bytes: int | None = Field(default=None, ge=0)
    task_id: UUID | None = None
    workflow_instance_id: UUID | None = None
    created_by: str | None = Field(default=None, max_length=120)
    stage: ArtifactStage = ArtifactStage.DEVELOPMENT


class ArtifactReviewRequest(BaseModel):
    """Payload for moving an artifact into a reviewed state.

    ``superseded`` is managed by the platform when a new revision appears and
    therefore cannot be requested here.
    """

    decision: Literal["approved", "rejected"] = Field(
        description="人工审核结论：approved 通过，rejected 驳回",
    )
    reviewed_by: str = Field(
        min_length=1,
        max_length=120,
        description="审核人，会写入审核轨迹",
    )
    comment: str | None = Field(default=None, max_length=2000)


class ArtifactRead(BaseModel):
    """An artifact as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    task_id: UUID | None = None
    workflow_instance_id: UUID | None = None
    relative_path: str
    version: int
    sha256: str
    file_type: str
    size_bytes: int | None = None
    review_status: ArtifactReviewStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_by: str | None = None
    stage: ArtifactStage
    original_filename: str | None = None
    storage_path: str | None = None
    created_at: datetime
    updated_at: datetime
