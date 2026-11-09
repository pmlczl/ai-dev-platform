"""Request and response models of the workflow endpoints.

The models are a strict whitelist: a request cannot carry graph state, a
checkpoint id or any other internal value. The browser only ever sends the
decision of a human approval and the thread it believes it is talking to.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ApprovalDecision, ArtifactReviewStatus, WorkflowStatus


class WorkflowDecision(StrEnum):
    """Outcome of a human approval of a workflow run.

    Only the two outcomes the workflow can act on are allowed - a request
    with any other value is rejected by the schema itself.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class WorkflowStartRequest(BaseModel):
    """Payload for starting a workflow for a task."""

    workflow_key: str | None = Field(default=None, max_length=100)
    started_by: str | None = Field(default=None, max_length=120)


class WorkflowResumeRequest(BaseModel):
    """Payload for advancing a workflow.

    ``thread_id`` is only an assertion: the server compares it with the
    thread it derived from the workflow id and never uses the value of the
    request to address a checkpoint.
    """

    thread_id: str = Field(min_length=1, max_length=120)
    decision: WorkflowDecision | None = None
    approver: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=5000)
    idempotency_key: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="客户端幂等键；重复提交同一个键不会产生第二条审批记录",
    )

    @model_validator(mode="after")
    def _approver_is_required_with_a_decision(self) -> WorkflowResumeRequest:
        if self.decision is not None and not (self.approver or "").strip():
            raise ValueError("提交审批结果时必须提供审批人")
        return self


class WorkflowArtifactRead(BaseModel):
    """The artifact of the current round of a workflow."""

    id: UUID
    relative_path: str
    version: int
    sha256: str
    size_bytes: int | None = None
    review_status: ArtifactReviewStatus


class WorkflowPendingApprovalRead(BaseModel):
    """Summary of the approval a workflow is waiting for."""

    request_id: str
    iteration: int
    artifact_id: UUID | None = None
    artifact_version: int | None = None
    preview: str = ""
    revision_comments: list[str] = Field(default_factory=list)
    requested_at: datetime | None = None


class WorkflowApprovalRead(BaseModel):
    """One decision of the approval trail of a workflow."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision: ApprovalDecision
    approver: str
    comment: str | None = None
    sequence: int
    created_at: datetime


class WorkflowRead(BaseModel):
    """The view of a workflow instance.

    The view holds the bookkeeping of the platform. The state of the graph
    itself is never exposed.
    """

    id: UUID
    project_id: UUID
    task_id: UUID | None = None
    workflow_key: str
    thread_id: str
    status: WorkflowStatus
    current_step: str | None = None
    iteration: int
    current_artifact: WorkflowArtifactRead | None = None
    pending_approval: WorkflowPendingApprovalRead | None = None
    approvals: list[WorkflowApprovalRead] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowEventRead(BaseModel):
    """One entry of the event log of a workflow."""

    model_config = ConfigDict(from_attributes=True)

    sequence: int
    step: str
    event: str
    message: str | None = None
    payload: dict | None = None
    created_at: datetime
