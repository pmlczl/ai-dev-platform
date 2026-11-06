"""Business logic for approval records.

Approval records are append only. The service offers exactly one write
operation - appending a decision - and deliberately no update or delete, so
that the audit trail can only grow.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.approval import ApprovalRecord
from app.models.artifact import Artifact
from app.models.enums import ApprovalTargetType
from app.models.task import DevelopmentTask
from app.models.workflow import WorkflowInstance
from app.schemas.approval import ApprovalAppend
from app.services.projects import get_project


async def _ensure_target_exists(
    session: AsyncSession,
    target_type: ApprovalTargetType,
    target_id: UUID,
    project_id: UUID,
) -> None:
    """Check that the approved object exists and belongs to the project.

    ``target_id`` is a polymorphic reference, so it cannot be a real foreign
    key; the check lives here instead.
    """

    if target_type is ApprovalTargetType.TASK:
        stmt = select(DevelopmentTask).where(
            DevelopmentTask.id == target_id,
            DevelopmentTask.deleted_at.is_(None),
        )
    elif target_type is ApprovalTargetType.ARTIFACT:
        stmt = select(Artifact).where(Artifact.id == target_id)
    else:
        stmt = select(WorkflowInstance).where(WorkflowInstance.id == target_id)

    target = (await session.execute(stmt)).scalar_one_or_none()
    if target is None:
        raise NotFoundException(f"审批对象 {target_id} 不存在")
    if target.project_id != project_id:
        raise ValidationException("审批对象不属于该项目")


async def append_approval(session: AsyncSession, payload: ApprovalAppend) -> ApprovalRecord:
    """Append an approval decision for a task, an artifact or a workflow."""

    await get_project(session, payload.project_id)
    await _ensure_target_exists(
        session,
        payload.target_type,
        payload.target_id,
        payload.project_id,
    )

    stmt = select(func.max(ApprovalRecord.sequence)).where(
        ApprovalRecord.target_type == payload.target_type.value,
        ApprovalRecord.target_id == payload.target_id,
    )
    sequence = int(await session.scalar(stmt) or 0) + 1

    record = ApprovalRecord(
        project_id=payload.project_id,
        target_type=payload.target_type.value,
        target_id=payload.target_id,
        decision=payload.decision.value,
        comment=payload.comment,
        approver=payload.approver,
        sequence=sequence,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictException("审批记录顺序冲突，请重试") from exc

    await session.refresh(record)
    return record


async def list_approvals(
    session: AsyncSession,
    project_id: UUID,
    target_type: ApprovalTargetType | None = None,
    target_id: UUID | None = None,
) -> list[ApprovalRecord]:
    """Return the approval trail, oldest decision first."""

    stmt = select(ApprovalRecord).where(ApprovalRecord.project_id == project_id)
    if target_type is not None:
        stmt = stmt.where(ApprovalRecord.target_type == target_type.value)
    if target_id is not None:
        stmt = stmt.where(ApprovalRecord.target_id == target_id)

    stmt = stmt.order_by(ApprovalRecord.created_at, ApprovalRecord.sequence)
    return list((await session.execute(stmt)).scalars().all())
