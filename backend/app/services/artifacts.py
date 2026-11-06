"""Business logic for artifact metadata.

Only the metadata of a file is managed here. A new revision of a file is
appended as a new row and the previous revision is marked as superseded, so
the history of a document stays traceable.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ValidationException
from app.models.artifact import Artifact
from app.models.enums import ArtifactReviewStatus
from app.schemas.artifact import ArtifactRegister
from app.services.projects import get_project
from app.services.tasks import get_task


async def _next_version(session: AsyncSession, project_id: UUID, relative_path: str) -> int:
    """Return the version number of the next revision of a file."""

    stmt = select(func.max(Artifact.version)).where(
        Artifact.project_id == project_id,
        Artifact.relative_path == relative_path,
    )
    current = await session.scalar(stmt)
    return int(current or 0) + 1


async def register_artifact(session: AsyncSession, payload: ArtifactRegister) -> Artifact:
    """Register the metadata of a file and supersede its previous revision."""

    await get_project(session, payload.project_id)

    if payload.task_id is not None:
        task = await get_task(session, payload.task_id)
        if task.project_id != payload.project_id:
            raise ValidationException("任务不属于该项目，无法登记产物")

    version = await _next_version(session, payload.project_id, payload.relative_path)

    await session.execute(
        update(Artifact)
        .where(
            Artifact.project_id == payload.project_id,
            Artifact.relative_path == payload.relative_path,
            Artifact.version < version,
        )
        .values(review_status=ArtifactReviewStatus.SUPERSEDED.value)
    )

    artifact = Artifact(
        project_id=payload.project_id,
        task_id=payload.task_id,
        workflow_instance_id=payload.workflow_instance_id,
        relative_path=payload.relative_path,
        version=version,
        sha256=payload.sha256.lower(),
        file_type=payload.file_type,
        size_bytes=payload.size_bytes,
        review_status=ArtifactReviewStatus.PENDING.value,
        created_by=payload.created_by,
    )
    session.add(artifact)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictException("该路径的相同版本已存在") from exc

    await session.refresh(artifact)
    return artifact


async def list_artifacts(
    session: AsyncSession,
    project_id: UUID,
) -> list[Artifact]:
    """Return every revision of the files of a project, newest revision first."""

    stmt = (
        select(Artifact)
        .where(Artifact.project_id == project_id)
        .order_by(Artifact.relative_path, Artifact.version.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
