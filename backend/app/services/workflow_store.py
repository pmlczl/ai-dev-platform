"""Persistence of workflow instances and their event log.

The module is the single place that writes to ``workflow_instances`` and
``workflow_events``. The workflow nodes use it, and so does the workflow
service - both need the same guarantees:

* an event is written at most once, even when the node that writes it is
  replayed after a restart (the ``event_key`` is the idempotency key),
* the state of an instance is only ever assigned, never incremented, so a
  replay cannot shift a counter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.enums import WorkflowStatus
from app.models.workflow import WorkflowInstance
from app.models.workflow_event import WorkflowEvent
from app.schemas.common import PageParams

#: Statuses of an instance that will not run any more.
TERMINAL_STATUSES = (
    WorkflowStatus.COMPLETED.value,
    WorkflowStatus.FAILED.value,
    WorkflowStatus.CANCELLED.value,
)

#: Prefix of the idempotency key of an approval record that belongs to a
#: round of a workflow instance.
REQUEST_KEY_PREFIX = "req:"
#: Prefix of the idempotency key of an approval record that was requested
#: with a client supplied key.
CLIENT_KEY_PREFIX = "client:"


def approval_request_id(workflow_id: UUID, iteration: int) -> str:
    """Return the deterministic id of one approval round.

    The id only depends on the instance and the iteration, so a node that is
    replayed after a restart computes the very same value and finds the
    approval record of that round again.
    """

    return f"{workflow_id}:{iteration}"


def approval_request_key(request_id: str) -> str:
    """Return the idempotency key of the approval record of a round."""

    return f"{REQUEST_KEY_PREFIX}{request_id}"


def client_idempotency_key(key: str) -> str:
    """Return the idempotency key of a record requested with a client key."""

    return f"{CLIENT_KEY_PREFIX}{key}"


def now() -> datetime:
    """Return the current time in UTC."""

    return datetime.now(UTC)


async def get_instance(session: AsyncSession, workflow_id: UUID) -> WorkflowInstance:
    """Return a workflow instance or raise a not found error."""

    instance = await session.get(WorkflowInstance, workflow_id)
    if instance is None:
        raise NotFoundException(f"工作流 {workflow_id} 不存在")
    return instance


async def find_active_instance(
    session: AsyncSession,
    task_id: UUID,
) -> WorkflowInstance | None:
    """Return the instance of a task that has not finished yet."""

    stmt = select(WorkflowInstance).where(
        WorkflowInstance.task_id == task_id,
        WorkflowInstance.status.not_in(TERMINAL_STATUSES),
    )
    return (await session.execute(stmt)).scalars().first()


async def update_instance(
    session: AsyncSession,
    workflow_id: UUID,
    **fields: Any,
) -> WorkflowInstance:
    """Assign the given fields to an instance and store them.

    Only absolute values are written: a replayed node assigns the same value
    again and the result does not change.
    """

    instance = await get_instance(session, workflow_id)
    for name, value in fields.items():
        setattr(instance, name, value)
    await session.commit()
    await session.refresh(instance)
    return instance


async def append_event(
    session: AsyncSession,
    workflow_instance_id: UUID,
    *,
    step: str,
    event: str,
    event_key: str,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> WorkflowEvent | None:
    """Append an entry to the event log of an instance.

    The ``event_key`` makes the call idempotent: a node that is replayed
    after a restart writes the same key and the entry that is already there
    is returned instead of a second one being written.
    """

    existing = await session.scalar(
        select(WorkflowEvent).where(
            WorkflowEvent.workflow_instance_id == workflow_instance_id,
            WorkflowEvent.event_key == event_key,
        )
    )
    if existing is not None:
        return existing

    sequence = int(
        await session.scalar(
            select(func.max(WorkflowEvent.sequence)).where(
                WorkflowEvent.workflow_instance_id == workflow_instance_id,
            )
        )
        or 0
    ) + 1

    record = WorkflowEvent(
        workflow_instance_id=workflow_instance_id,
        sequence=sequence,
        event_key=event_key,
        step=step,
        event=event,
        message=message,
        payload=payload,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent run wrote the same event or the same sequence.
        await session.rollback()
        return None
    await session.refresh(record)
    return record


async def list_events(
    session: AsyncSession,
    workflow_instance_id: UUID,
    params: PageParams,
) -> tuple[list[WorkflowEvent], int]:
    """Return one page of the event log and the total number of entries."""

    total = int(
        await session.scalar(
            select(func.count(WorkflowEvent.id)).where(
                WorkflowEvent.workflow_instance_id == workflow_instance_id,
            )
        )
        or 0
    )
    stmt = (
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_instance_id == workflow_instance_id)
        .order_by(WorkflowEvent.sequence)
        .offset(params.offset)
        .limit(params.limit)
    )
    events = list((await session.execute(stmt)).scalars().all())
    return events, total


async def reconcile_interrupted_instances(session: AsyncSession) -> list[UUID]:
    """Recover the instances that were left behind by a restart.

    An instance that was ``running`` when the process died cannot be resumed
    automatically - the graph may have been interrupted in the middle of a
    node. It is therefore moved into a state a human can act on:

    * an instance that already carries the summary of an approval request
      waits for the approval again,
    * every other instance is paused and can be continued with ``resume``.

    The instances are not revived automatically: a restart storm must not
    push the platform into a loop of approval requests.
    """

    stmt = select(WorkflowInstance).where(
        WorkflowInstance.status == WorkflowStatus.RUNNING.value,
    )
    instances = list((await session.execute(stmt)).scalars().all())

    recovered: list[UUID] = []
    for instance in instances:
        waiting = instance.pending_payload is not None
        instance.status = (
            WorkflowStatus.WAITING_APPROVAL.value
            if waiting
            else WorkflowStatus.PAUSED.value
        )
        await session.commit()
        await append_event(
            session,
            instance.id,
            step="recover",
            event="workflow_recovered",
            event_key=f"workflow_recovered:{instance.iteration}",
            message=(
                "服务重启后恢复为等待审批状态"
                if waiting
                else "服务重启后恢复为暂停状态，可继续执行"
            ),
            payload={"status": instance.status},
        )
        recovered.append(instance.id)
    return recovered
