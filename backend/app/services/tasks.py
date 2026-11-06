"""Business logic for development tasks.

A task always belongs to a project. The position of the task inside its
project is allocated by an atomic counter kept on the project row, so two
concurrent creations can never receive the same sequence number.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import TaskPriority, TaskStatus
from app.models.project import Project
from app.models.task import DevelopmentTask
from app.schemas.common import Page, PageParams, build_page
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.projects import get_project


async def _next_task_seq(session: AsyncSession, project_id: UUID) -> int:
    """Atomically reserve the next sequence number inside a project.

    The counter is incremented with a single ``UPDATE ... RETURNING`` statement,
    which makes the row lock of the project serialize concurrent creations.
    """

    stmt = (
        update(Project)
        .where(Project.id == project_id, Project.deleted_at.is_(None))
        .values(task_sequence=Project.task_sequence + 1)
        .returning(Project.task_sequence)
    )
    seq = (await session.execute(stmt)).scalar_one_or_none()
    if seq is None:
        raise NotFoundException(f"项目 {project_id} 不存在")
    return int(seq)


async def list_tasks(
    session: AsyncSession,
    params: PageParams,
    project_id: UUID | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    keyword: str | None = None,
) -> Page[TaskRead]:
    """Return one page of tasks together with the code and name of the project."""

    stmt = (
        select(DevelopmentTask, Project.code, Project.name)
        .join(Project, DevelopmentTask.project_id == Project.id)
        .where(
            DevelopmentTask.deleted_at.is_(None),
            Project.deleted_at.is_(None),
        )
    )

    if project_id is not None:
        stmt = stmt.where(DevelopmentTask.project_id == project_id)

    if status is not None:
        stmt = stmt.where(DevelopmentTask.status == status.value)

    if priority is not None:
        stmt = stmt.where(DevelopmentTask.priority == priority.value)

    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(DevelopmentTask.title.ilike(pattern))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(await session.scalar(count_stmt) or 0)

    stmt = (
        stmt.order_by(DevelopmentTask.created_at.desc(), DevelopmentTask.id)
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = (await session.execute(stmt)).all()

    items = [
        TaskRead.model_validate(row[0]).model_copy(
            update={"project_code": row[1], "project_name": row[2]},
        )
        for row in rows
    ]
    return build_page(items, total, params)


async def get_task(session: AsyncSession, task_id: UUID) -> DevelopmentTask:
    """Load a live task or raise ``NotFoundException``."""

    stmt = select(DevelopmentTask).where(
        DevelopmentTask.id == task_id,
        DevelopmentTask.deleted_at.is_(None),
    )
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        raise NotFoundException(f"任务 {task_id} 不存在")
    return task


async def create_task(session: AsyncSession, payload: TaskCreate) -> DevelopmentTask:
    """Create a task inside an existing project."""

    project = await get_project(session, payload.project_id)
    seq = await _next_task_seq(session, project.id)

    task = DevelopmentTask(
        project_id=project.id,
        seq=seq,
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        priority=payload.priority.value,
        assignee=payload.assignee,
    )
    session.add(task)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictException("任务序号冲突，请重试") from exc

    await session.refresh(task)
    return task


async def update_task(
    session: AsyncSession,
    task_id: UUID,
    payload: TaskUpdate,
) -> DevelopmentTask:
    """Apply the fields that are present in the payload to a task."""

    task = await get_task(session, task_id)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return task

    for field, value in changes.items():
        if isinstance(value, TaskStatus):
            value = value.value
        elif isinstance(value, TaskPriority):
            value = value.value
        setattr(task, field, value)

    await session.commit()
    await session.refresh(task)
    return task


async def to_read(session: AsyncSession, task: DevelopmentTask) -> TaskRead:
    """Convert a task into its API representation, including project hints."""

    project = await get_project(session, task.project_id)
    return TaskRead.model_validate(task).model_copy(
        update={"project_code": project.code, "project_name": project.name},
    )
