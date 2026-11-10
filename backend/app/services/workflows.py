"""Business logic of the workflow engine.

The service owns the semantics of a run:

* it creates the instance and derives its ``thread_id`` - a client never
  chooses the thread a run lives in,
* it validates every request against the state of the instance before the
  graph is touched,
* it records the approval decision in the database **before** the graph is
  driven, so a crash can never swallow a decision,
* it turns the graph state into a view that does not expose the internals of
  LangGraph to the browser.

The graph itself lives in ``app/workflows``; the checkpointer lives in
``app/services/workflow_runtime.py``. Neither of them knows about HTTP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ValidationException
from app.models.approval import ApprovalRecord
from app.models.artifact import Artifact
from app.models.enums import (
    ApprovalDecision,
    ApprovalTargetType,
    ArtifactReviewStatus,
    TaskStatus,
    WorkflowStatus,
)
from app.models.workflow import WorkflowInstance
from app.models.workflow_event import WorkflowEvent
from app.schemas.approval import ApprovalAppend
from app.schemas.common import Page, PageParams, build_page
from app.schemas.workflow import (
    WorkflowApprovalRead,
    WorkflowArtifactRead,
    WorkflowEventRead,
    WorkflowPendingApprovalRead,
    WorkflowRead,
    WorkflowResumeRequest,
    WorkflowStartRequest,
)
from app.services.approvals import (
    append_approval,
    find_approval_by_idempotency_key,
    list_approvals,
)
from app.services.tasks import get_task
from app.services.workflow_store import (
    TERMINAL_STATUSES,
    approval_request_id,
    approval_request_key,
    client_idempotency_key,
    find_active_instance,
    get_instance,
    list_events,
    list_instances,
    now,
    update_instance,
)
from app.workflows.registry import get_workflow as get_registered_workflow

if TYPE_CHECKING:  # pragma: no cover
    from app.services.workflow_runtime import WorkflowRuntime

#: Name of the workflow that is started when the caller does not name one.
DEFAULT_WORKFLOW_KEY = "dev_workflow"


def _artifact_relative_path(workflow_id: UUID, iteration: int) -> str:
    """Return the logical path of the artifact of one round."""

    return f"workflow/{workflow_id}/iteration-{iteration}/demo-artifact.md"


async def _current_artifact(
    session: AsyncSession,
    instance: WorkflowInstance,
) -> Artifact | None:
    """Return the artifact of the current round of an instance."""

    stmt = select(Artifact).where(
        Artifact.workflow_instance_id == instance.id,
        Artifact.relative_path == _artifact_relative_path(instance.id, instance.iteration),
    )
    return (await session.execute(stmt)).scalars().first()


async def _round_record(
    session: AsyncSession,
    instance: WorkflowInstance,
) -> ApprovalRecord | None:
    """Return the approval record of the current round, if it was decided.

    Every round produces exactly one approval record and the records of an
    instance are numbered in the order they were taken. The record of the
    current round is therefore the last one, and it exists as soon as the
    number of records reached the current iteration.
    """

    records = await list_approvals(
        session,
        instance.project_id,
        ApprovalTargetType.WORKFLOW_INSTANCE,
        instance.id,
    )
    if len(records) < instance.iteration:
        return None
    return records[-1]


async def _round_applied(
    session: AsyncSession,
    instance: WorkflowInstance,
) -> bool:
    """True when the decision of the current round was applied to the graph."""

    event = await session.scalar(
        select(WorkflowEvent).where(
            WorkflowEvent.workflow_instance_id == instance.id,
            WorkflowEvent.event_key == f"approval_received:{instance.iteration}",
        )
    )
    return event is not None


async def _mark_artifact_reviewed(
    session: AsyncSession,
    instance: WorkflowInstance,
    decision: str,
    approver: str,
) -> None:
    """Write the outcome of the approval into the review state of the artifact."""

    artifact = await _current_artifact(session, instance)
    if artifact is None:
        return
    artifact.review_status = (
        ArtifactReviewStatus.APPROVED.value
        if decision == "approved"
        else ArtifactReviewStatus.REJECTED.value
    )
    artifact.reviewed_by = approver
    artifact.reviewed_at = now()
    await session.commit()


async def _drive(
    runtime: WorkflowRuntime,
    instance: WorkflowInstance,
    resume_value: dict[str, Any] | None = None,
    *,
    initial: bool = False,
) -> dict[str, Any]:
    """Run the graph of an instance until it pauses or ends.

    The run is addressed by the ``thread_id`` of the instance, which is
    derived from the instance id on the server side.

    Three modes exist:

    * ``initial`` - the graph is started with the state of the instance,
    * a ``resume_value`` - the graph continues with the decision of a human
      approval,
    * neither - the graph continues from its checkpoint without changing the
      state. Passing the state again would overwrite the checkpointed values.
    """

    graph = runtime.graph(instance.workflow_key)
    config = {"configurable": {"thread_id": instance.thread_id}}

    if initial:
        result = await graph.ainvoke(
            {
                "workflow_id": str(instance.id),
                "project_id": str(instance.project_id),
                "task_id": str(instance.task_id) if instance.task_id else "",
                "thread_id": instance.thread_id,
                "iteration": instance.iteration,
            },
            config,
        )
    elif resume_value is not None:
        result = await graph.ainvoke(Command(resume=resume_value), config)
    else:
        result = await graph.ainvoke(None, config)
    return result if isinstance(result, dict) else {}


async def _store_snapshot(
    session: AsyncSession,
    runtime: WorkflowRuntime,
    instance: WorkflowInstance,
) -> None:
    """Store a short summary of the graph state on the instance.

    The summary is never handed to the browser - it exists so that an
    operator can see how far a run got.
    """

    graph = runtime.graph(instance.workflow_key)
    config = {"configurable": {"thread_id": instance.thread_id}}
    snapshot = await graph.aget_state(config)
    values = {
        key: value
        for key, value in dict(snapshot.values or {}).items()
        if isinstance(value, (str, int, float, bool, list, dict, type(None)))
    }
    await update_instance(
        session,
        instance.id,
        state={"values": values, "next": list(snapshot.next or ())},
    )


async def start_workflow(
    session: AsyncSession,
    runtime: WorkflowRuntime,
    task_id: UUID,
    payload: WorkflowStartRequest,
) -> WorkflowInstance:
    """Start a workflow for a task and run it until the first approval.

    The graph is executed synchronously: every node is a local simulation,
    so the run returns as soon as the workflow waits for a human decision.
    """

    task = await get_task(session, task_id)

    if task.status in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
        raise ConflictException("任务已结束，无法启动工作流")

    active = await find_active_instance(session, task_id)
    if active is not None:
        raise ConflictException(
            "该任务已有进行中的工作流",
            detail={"existing_workflow_id": str(active.id)},
        )

    workflow_key = payload.workflow_key or DEFAULT_WORKFLOW_KEY
    workflow = get_registered_workflow(workflow_key)

    instance_id = uuid4()
    instance = WorkflowInstance(
        id=instance_id,
        # The thread is derived from the instance: a client can neither
        # choose it nor address the thread of another instance.
        thread_id=f"wf-{instance_id}",
        project_id=task.project_id,
        task_id=task.id,
        workflow_key=workflow.name,
        status=WorkflowStatus.PENDING.value,
        iteration=1,
        started_at=now(),
    )
    session.add(instance)
    await session.commit()
    await session.refresh(instance)

    await _drive(runtime, instance, None, initial=True)
    await _store_snapshot(session, runtime, instance)
    return await get_instance(session, instance.id)


async def get_workflow(session: AsyncSession, workflow_id: UUID) -> WorkflowInstance:
    """Return a workflow instance or raise a not found error."""

    return await get_instance(session, workflow_id)


async def resume_workflow(
    session: AsyncSession,
    runtime: WorkflowRuntime,
    workflow_id: UUID,
    payload: WorkflowResumeRequest,
) -> WorkflowInstance:
    """Advance a workflow: submit an approval or continue from the checkpoint.

    The order of the checks matters. A repeated client key is a replay and
    is answered with the current state, no matter which state that is. Only
    a request that is really new is validated against the state of the
    instance.
    """

    instance = await get_instance(session, workflow_id)

    # The thread id of the request is only an assertion: the server always
    # addresses the checkpoint with the thread it derived itself.
    if payload.thread_id != instance.thread_id:
        raise ConflictException("thread_id 与工作流实例不一致")

    if payload.idempotency_key:
        replay = await find_approval_by_idempotency_key(
            session,
            ApprovalTargetType.WORKFLOW_INSTANCE,
            instance.id,
            client_idempotency_key(payload.idempotency_key),
        )
        if replay is not None:
            return await _replay(session, runtime, instance, replay)

    if instance.status in TERMINAL_STATUSES:
        raise ConflictException("工作流已结束，无法继续")
    if instance.status == WorkflowStatus.PENDING.value:
        raise ConflictException("工作流尚未启动")
    if instance.status == WorkflowStatus.RUNNING.value:
        raise ConflictException("工作流正在执行中，请稍后重试")

    if (
        instance.status == WorkflowStatus.WAITING_APPROVAL.value
        and payload.decision is None
    ):
        raise ConflictException("工作流正在等待审批，必须提交审批结果")

    decided = await _round_record(session, instance)
    if decided is not None:
        if await _round_applied(session, instance):
            raise ConflictException("该审批请求已处理，请勿重复提交")
        # The decision was taken but never reached the graph - the process
        # died in between. It is applied now, without a second record.
        return await _apply_decision(session, runtime, instance, decided)

    if payload.decision is None:
        # A paused instance is continued from its checkpoint.
        await _drive(runtime, instance, None)
        await _store_snapshot(session, runtime, instance)
        return await get_instance(session, instance.id)

    record = await _record_decision(session, instance, payload)
    return await _apply_decision(session, runtime, instance, record)


async def _record_decision(
    session: AsyncSession,
    instance: WorkflowInstance,
    payload: WorkflowResumeRequest,
) -> ApprovalRecord:
    """Store the decision of a human approval.

    The record is written before the graph is driven. The decision is
    therefore durable even when the process dies between the two steps.
    """

    decision = payload.decision
    if decision is None:
        raise ValidationException("缺少审批结果")
    approver = (payload.approver or "").strip()
    if not approver:
        raise ValidationException("缺少审批人")

    request_id = approval_request_id(instance.id, instance.iteration)
    idempotency_key = (
        client_idempotency_key(payload.idempotency_key)
        if payload.idempotency_key
        else approval_request_key(request_id)
    )
    return await append_approval(
        session,
        ApprovalAppend(
            project_id=instance.project_id,
            target_type=ApprovalTargetType.WORKFLOW_INSTANCE,
            target_id=instance.id,
            decision=ApprovalDecision(decision.value),
            approver=approver,
            comment=payload.comment,
            idempotency_key=idempotency_key,
        ),
    )


async def _apply_decision(
    session: AsyncSession,
    runtime: WorkflowRuntime,
    instance: WorkflowInstance,
    record: ApprovalRecord,
) -> WorkflowInstance:
    """Hand a stored decision to the graph and let it continue."""

    request_id = approval_request_id(instance.id, instance.iteration)
    decision = {
        "decision": record.decision,
        "approver": record.approver,
        "comment": record.comment,
        "request_id": request_id,
    }
    await update_instance(
        session,
        instance.id,
        pending_decision=decision,
        last_decision=record.decision,
    )
    await _drive(runtime, instance, decision)
    await _mark_artifact_reviewed(session, instance, record.decision, record.approver)
    await _store_snapshot(session, runtime, instance)
    return await get_instance(session, instance.id)


async def _replay(
    session: AsyncSession,
    runtime: WorkflowRuntime,
    instance: WorkflowInstance,
    record: ApprovalRecord,
) -> WorkflowInstance:
    """Answer a repeated submission with the same idempotency key.

    No second approval record is written. The graph is only driven again
    when the decision was never applied to it - that is the case when the
    process died between writing the record and driving the graph.
    """

    if instance.status in TERMINAL_STATUSES:
        return instance
    if await _round_applied(session, instance):
        return instance
    return await _apply_decision(session, runtime, instance, record)


async def list_workflow_logs(
    session: AsyncSession,
    workflow_id: UUID,
    params: PageParams,
) -> Page[WorkflowEventRead]:
    """Return one page of the event log of a workflow instance."""

    await get_instance(session, workflow_id)
    events, total = await list_events(session, workflow_id, params)
    items = [WorkflowEventRead.model_validate(event) for event in events]
    return build_page(items, total, params)


async def list_workflows(
    session: AsyncSession,
    params: PageParams,
    status: WorkflowStatus | None = None,
    project_id: UUID | None = None,
    task_id: UUID | None = None,
) -> Page[WorkflowRead]:
    """Return one page of the workflow instances.

    The filters can be combined freely - the caller may ask for the runs of
    one project, of one task or for the runs that wait for an approval. The
    view of every row is the same view the detail endpoint returns; the state
    of the graph is never part of it.
    """

    instances, total = await list_instances(
        session,
        params,
        status=status,
        project_id=project_id,
        task_id=task_id,
    )
    items = await _to_read_many(session, instances)
    return build_page(items, total, params)


async def list_task_workflows(
    session: AsyncSession,
    task_id: UUID,
    params: PageParams,
) -> Page[WorkflowRead]:
    """Return one page of the workflow instances of one task.

    Every run of the task is listed, including the ones that already reached
    a terminal state - the history is part of the answer. A task that does
    not exist (or was deleted) is reported as not found, exactly like the
    detail endpoint of a task does.
    """

    await get_task(session, task_id)
    instances, total = await list_instances(session, params, task_id=task_id)
    items = await _to_read_many(session, instances)
    return build_page(items, total, params)


async def to_read(
    session: AsyncSession,
    instance: WorkflowInstance,
) -> WorkflowRead:
    """Build the view of a workflow instance.

    The view contains the fields of the platform and nothing of the
    internals of LangGraph: no checkpoint id, no channel values.
    """

    artifact = await _current_artifact(session, instance)
    approvals = await list_approvals(
        session,
        instance.project_id,
        ApprovalTargetType.WORKFLOW_INSTANCE,
        instance.id,
    )
    return _build_view(instance, artifact, approvals)


async def _to_read_many(
    session: AsyncSession,
    instances: list[WorkflowInstance],
) -> list[WorkflowRead]:
    """Build the views of several instances with a constant number of queries.

    A list endpoint is polled by the browser, so the rows are loaded with two
    queries instead of two per instance.
    """

    if not instances:
        return []

    ids = [instance.id for instance in instances]
    iterations = {instance.id: instance.iteration for instance in instances}

    artifact_rows = (
        await session.execute(
            select(Artifact).where(Artifact.workflow_instance_id.in_(ids)),
        )
    ).scalars().all()
    artifacts: dict[UUID, Artifact] = {}
    for artifact in artifact_rows:
        if artifact.workflow_instance_id is None:
            continue
        expected = _artifact_relative_path(
            artifact.workflow_instance_id,
            iterations.get(artifact.workflow_instance_id, 1),
        )
        if artifact.relative_path == expected:
            artifacts[artifact.workflow_instance_id] = artifact

    approval_rows = (
        await session.execute(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.target_type == ApprovalTargetType.WORKFLOW_INSTANCE.value,
                ApprovalRecord.target_id.in_(ids),
            )
            .order_by(ApprovalRecord.created_at, ApprovalRecord.sequence),
        )
    ).scalars().all()
    approvals: dict[UUID, list[ApprovalRecord]] = {}
    for record in approval_rows:
        approvals.setdefault(record.target_id, []).append(record)

    return [
        _build_view(instance, artifacts.get(instance.id), approvals.get(instance.id, []))
        for instance in instances
    ]


def _build_view(
    instance: WorkflowInstance,
    artifact: Artifact | None,
    approvals: list[ApprovalRecord],
) -> WorkflowRead:
    """Assemble the view of one instance from the data that was loaded."""

    return WorkflowRead(
        id=instance.id,
        project_id=instance.project_id,
        task_id=instance.task_id,
        workflow_key=instance.workflow_key,
        thread_id=instance.thread_id,
        status=instance.status,
        current_step=instance.current_step,
        iteration=instance.iteration,
        current_artifact=(
            WorkflowArtifactRead(
                id=artifact.id,
                relative_path=artifact.relative_path,
                version=artifact.version,
                sha256=artifact.sha256,
                size_bytes=artifact.size_bytes,
                review_status=artifact.review_status,
            )
            if artifact is not None
            else None
        ),
        pending_approval=_pending_approval(instance),
        approvals=[
            WorkflowApprovalRead.model_validate(record) for record in approvals
        ],
        started_at=instance.started_at,
        finished_at=instance.finished_at,
        error_message=instance.error_message,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


def _pending_approval(
    instance: WorkflowInstance,
) -> WorkflowPendingApprovalRead | None:
    """Build the summary of the approval an instance is waiting for."""

    payload = instance.pending_payload
    if not payload:
        return None
    return WorkflowPendingApprovalRead(
        request_id=str(payload.get("request_id", "")),
        iteration=int(payload.get("iteration", instance.iteration)),
        artifact_id=payload.get("artifact_id"),
        artifact_version=payload.get("artifact_version"),
        preview=str(payload.get("preview", "")),
        revision_comments=list(payload.get("revision_comments") or []),
        requested_at=payload.get("requested_at"),
    )
