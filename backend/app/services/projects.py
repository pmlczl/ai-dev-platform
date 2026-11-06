"""Business logic for projects.

The service layer owns the persistence rules of the project aggregate: soft
deletes, uniqueness of the project code and the task counter. It never touches
the FastAPI request object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import ProjectStatus
from app.models.project import Project
from app.models.task import DevelopmentTask
from app.schemas.common import Page, PageParams, build_page
from app.schemas.project import ProjectCreate, ProjectListItem, ProjectRead, ProjectUpdate


async def _task_counts(session: AsyncSession, project_ids: list[UUID]) -> dict[UUID, int]:
    """Count the live tasks of every given project with a single query."""

    if not project_ids:
        return {}

    stmt = (
        select(DevelopmentTask.project_id, func.count())
        .where(
            DevelopmentTask.project_id.in_(project_ids),
            DevelopmentTask.deleted_at.is_(None),
        )
        .group_by(DevelopmentTask.project_id)
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: int(row[1]) for row in rows}


async def list_projects(
    session: AsyncSession,
    params: PageParams,
    status: ProjectStatus | None = None,
    keyword: str | None = None,
) -> Page[ProjectListItem]:
    """Return one page of projects, newest first."""

    stmt = select(Project).where(Project.deleted_at.is_(None))

    if status is not None:
        stmt = stmt.where(Project.status == status.value)

    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(Project.name.ilike(pattern), Project.code.ilike(pattern)),
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(await session.scalar(count_stmt) or 0)

    stmt = (
        stmt.order_by(Project.created_at.desc(), Project.id)
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    counts = await _task_counts(session, [row.id for row in rows])
    items = [
        ProjectListItem.model_validate(row).model_copy(
            update={"task_count": counts.get(row.id, 0)},
        )
        for row in rows
    ]
    return build_page(items, total, params)


async def get_project(session: AsyncSession, project_id: UUID) -> Project:
    """Load a live project or raise ``NotFoundException``."""

    stmt = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise NotFoundException(f"项目 {project_id} 不存在")
    return project


async def create_project(session: AsyncSession, payload: ProjectCreate) -> Project:
    """Create a project; a duplicated code is reported as a conflict."""

    project = Project(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        status=payload.status.value,
        owner=payload.owner,
    )
    session.add(project)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictException(f"项目编号 {payload.code} 已存在") from exc

    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession,
    project_id: UUID,
    payload: ProjectUpdate,
) -> Project:
    """Apply the fields that are present in the payload to a project."""

    project = await get_project(session, project_id)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return project

    for field, value in changes.items():
        if isinstance(value, ProjectStatus):
            value = value.value
        setattr(project, field, value)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictException(f"项目编号 {payload.code} 已存在") from exc

    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project_id: UUID) -> None:
    """Soft delete a project and, with it, all of its tasks.

    The rows stay in the database so that the approval trail and the artifact
    metadata keep their references.
    """

    project = await get_project(session, project_id)
    deleted_at = datetime.now(UTC)

    project.deleted_at = deleted_at
    await session.execute(
        update(DevelopmentTask)
        .where(
            DevelopmentTask.project_id == project.id,
            DevelopmentTask.deleted_at.is_(None),
        )
        .values(deleted_at=deleted_at)
    )
    await session.commit()


def to_read(project: Project) -> ProjectRead:
    """Convert a project into its API representation."""

    return ProjectRead.model_validate(project)
