"""Request and response models for approval records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApprovalDecision, ApprovalTargetType


class ApprovalAppend(BaseModel):
    """Payload for appending an approval record.

    Approval records are append only: there is no update payload on purpose.
    """

    project_id: UUID
    target_type: ApprovalTargetType
    target_id: UUID
    decision: ApprovalDecision
    approver: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=5000)
    #: Optional idempotency key. Together with the target it makes a repeated
    #: submission a no-op instead of a second record.
    idempotency_key: str | None = Field(default=None, max_length=120)


class ApprovalRecordRead(BaseModel):
    """An approval record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    target_type: ApprovalTargetType
    target_id: UUID
    decision: ApprovalDecision
    comment: str | None = None
    approver: str
    sequence: int
    created_at: datetime
