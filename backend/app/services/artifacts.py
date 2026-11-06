"""Business logic for artifacts - the files a project produces.

Two kinds of artifacts exist:

* **registered** artifacts carry metadata only (see :func:`register_artifact`),
* **stored** artifacts are backed by a real file on disk (see
  :func:`upload_artifact` and :func:`create_revision`).

A new revision of a file is appended as a new row and the previous revision is
marked as ``superseded``, so the history of a document stays traceable. The
physical layout separates the versions by directory, which makes it impossible
to overwrite an existing revision by accident.
"""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    PayloadTooLargeException,
    ValidationException,
)
from app.core.storage import (
    build_storage_path,
    move_into,
    normalize_relative_path,
    remove_empty_parents,
    remove_file,
    resolve_within_root,
    sanitize_filename,
    storage_root,
    temp_dir,
    write_stream_exclusive,
)
from app.models.artifact import Artifact
from app.models.enums import (
    ApprovalDecision,
    ApprovalTargetType,
    ArtifactReviewStatus,
    ArtifactStage,
)
from app.schemas.approval import ApprovalAppend
from app.schemas.artifact import ArtifactRead, ArtifactRegister, ArtifactReviewRequest
from app.schemas.common import Page, PageParams, build_page
from app.services.approvals import append_approval
from app.services.artifact_types import extension_of, resolve_file_type, verify_content
from app.services.projects import get_project
from app.services.tasks import get_task

#: Number of bytes read per chunk while an upload is streamed to disk.
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FileUpload:
    """An uploaded file, decoupled from the web framework.

    The service layer must not depend on FastAPI, so the endpoint converts an
    :class:`fastapi.UploadFile` into this small value object.
    """

    filename: str
    chunks: AsyncIterable[bytes]
    declared_size: int | None = None


async def _next_version(session: AsyncSession, project_id: UUID, relative_path: str) -> int:
    """Return the version number of the next revision of a file."""

    stmt = select(func.max(Artifact.version)).where(
        Artifact.project_id == project_id,
        Artifact.relative_path == relative_path,
    )
    current = await session.scalar(stmt)
    return int(current or 0) + 1


def _resolve_logical_path(filename: str, relative_path: str | None) -> str:
    """Return the logical path of the file inside the project.

    The logical path identifies "the same file" across revisions. When the
    caller does not provide one, the uploaded file name is used.
    """

    if relative_path:
        return normalize_relative_path(relative_path)
    return normalize_relative_path(filename)


def _file_type_of(logical_path: str) -> tuple[str, str]:
    """Return the canonical media type and the extension of a logical path.

    The type is derived from the name the file is stored under, never from the
    ``Content-Type`` header of the request, which is untrusted input.
    """

    stored_name = PurePosixPath(logical_path).name
    allowed = get_settings().allowed_upload_extensions
    return resolve_file_type(stored_name, allowed), extension_of(stored_name)


async def _supersede_previous(
    session: AsyncSession,
    project_id: UUID,
    relative_path: str,
    version: int,
) -> None:
    """Mark every older revision of a file as superseded."""

    await session.execute(
        update(Artifact)
        .where(
            Artifact.project_id == project_id,
            Artifact.relative_path == relative_path,
            Artifact.version < version,
        )
        .values(review_status=ArtifactReviewStatus.SUPERSEDED.value)
    )


def _remove_stored_file(storage_path: str) -> None:
    """Delete a stored file and the directories that became empty."""

    path = resolve_within_root(storage_path)
    remove_file(path)
    remove_empty_parents(path, storage_root())


async def _store_file(
    *,
    upload: FileUpload,
    logical_path: str,
    project_id: UUID,
    task_id: UUID | None,
    version: int,
) -> tuple[str, str, int, str]:
    """Write an upload to disk.

    Returns the storage path, the canonical media type, the size in bytes and
    the SHA256 digest of the stored file.
    """

    settings = get_settings()
    max_bytes = settings.storage_max_upload_size

    # Fast failure on the size the client announced. The real size is checked
    # while the stream is consumed, because the header cannot be trusted.
    if upload.declared_size is not None and upload.declared_size > max_bytes:
        raise PayloadTooLargeException(f"文件超过大小上限（{max_bytes} 字节）")

    file_type, extension = _file_type_of(logical_path)
    storage_path = build_storage_path(
        project_id=str(project_id),
        task_id=str(task_id) if task_id else None,
        relative_path=logical_path,
        version=version,
    )
    destination = resolve_within_root(storage_path)

    # The upload is written into the temporary directory first: a file that
    # fails the content check must never appear under its final name.
    staging = temp_dir() / f"{uuid4().hex}.part"
    try:
        size, digest = await write_stream_exclusive(staging, upload.chunks, max_bytes)
        verify_content(staging, extension)
        move_into(staging, destination)
    except BaseException:
        remove_file(staging)
        remove_empty_parents(staging, temp_dir())
        raise

    return storage_path, file_type, size, digest


async def register_artifact(session: AsyncSession, payload: ArtifactRegister) -> Artifact:
    """Register the metadata of a file and supersede its previous revision."""

    await get_project(session, payload.project_id)

    if payload.task_id is not None:
        task = await get_task(session, payload.task_id)
        if task.project_id != payload.project_id:
            raise ValidationException("任务不属于该项目，无法登记产物")

    version = await _next_version(session, payload.project_id, payload.relative_path)

    await _supersede_previous(session, payload.project_id, payload.relative_path, version)

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
        stage=payload.stage.value,
    )
    session.add(artifact)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictException("该路径的相同版本已存在") from exc

    await session.refresh(artifact)
    return artifact


async def upload_artifact(
    session: AsyncSession,
    task_id: UUID,
    upload: FileUpload,
    *,
    relative_path: str | None = None,
    stage: ArtifactStage = ArtifactStage.DEVELOPMENT,
    created_by: str | None = None,
) -> Artifact:
    """Store an uploaded file below a task and register its metadata.

    The project is derived from the task, so a client cannot attribute a file
    to a project it does not belong to.
    """

    task = await get_task(session, task_id)
    project_id = task.project_id

    safe_name = sanitize_filename(upload.filename)
    logical_path = _resolve_logical_path(safe_name, relative_path)
    version = await _next_version(session, project_id, logical_path)

    storage_path, file_type, size, digest = await _store_file(
        upload=upload,
        logical_path=logical_path,
        project_id=project_id,
        task_id=task_id,
        version=version,
    )

    artifact = Artifact(
        project_id=project_id,
        task_id=task_id,
        relative_path=logical_path,
        version=version,
        sha256=digest,
        file_type=file_type,
        size_bytes=size,
        review_status=ArtifactReviewStatus.PENDING.value,
        stage=stage.value,
        original_filename=safe_name,
        storage_path=storage_path,
        created_by=created_by,
    )
    session.add(artifact)
    try:
        await _supersede_previous(session, project_id, logical_path, version)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _remove_stored_file(storage_path)
        raise ConflictException("该路径的相同版本已存在") from exc

    await session.refresh(artifact)
    return artifact


async def create_revision(
    session: AsyncSession,
    artifact_id: UUID,
    upload: FileUpload,
    *,
    stage: ArtifactStage | None = None,
    created_by: str | None = None,
) -> Artifact:
    """Append a new revision of an existing file.

    The new revision lives in its own directory, so the previous one keeps its
    content on disk and in the database.
    """

    previous = await get_artifact(session, artifact_id)
    project_id = previous.project_id
    logical_path = previous.relative_path
    safe_name = sanitize_filename(upload.filename)
    version = await _next_version(session, project_id, logical_path)

    storage_path, file_type, size, digest = await _store_file(
        upload=upload,
        logical_path=logical_path,
        project_id=project_id,
        task_id=previous.task_id,
        version=version,
    )

    artifact = Artifact(
        project_id=project_id,
        task_id=previous.task_id,
        workflow_instance_id=previous.workflow_instance_id,
        relative_path=logical_path,
        version=version,
        sha256=digest,
        file_type=file_type,
        size_bytes=size,
        review_status=ArtifactReviewStatus.PENDING.value,
        stage=(stage.value if stage is not None else previous.stage),
        original_filename=safe_name,
        storage_path=storage_path,
        created_by=created_by,
    )
    session.add(artifact)
    try:
        await _supersede_previous(session, project_id, logical_path, version)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _remove_stored_file(storage_path)
        raise ConflictException("该路径的相同版本已存在") from exc

    await session.refresh(artifact)
    return artifact


async def get_artifact(session: AsyncSession, artifact_id: UUID) -> Artifact:
    """Load an artifact or raise ``NotFoundException``."""

    stmt = select(Artifact).where(Artifact.id == artifact_id)
    artifact = (await session.execute(stmt)).scalar_one_or_none()
    if artifact is None:
        raise NotFoundException(f"文件 {artifact_id} 不存在")
    return artifact


def resolve_artifact_file(artifact: Artifact) -> Path:
    """Return the path of the stored file of an artifact.

    Raises ``NotFoundException`` when the artifact only carries metadata or
    when the file was removed from the disk behind the back of the platform.
    """

    if not artifact.storage_path:
        raise NotFoundException(f"文件 {artifact.id} 没有可下载的内容")

    path = resolve_within_root(artifact.storage_path)
    if not path.is_file():
        raise NotFoundException(f"文件 {artifact.id} 的内容已不存在")
    return path


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


async def list_task_artifacts(
    session: AsyncSession,
    task_id: UUID,
    params: PageParams,
    review_status: ArtifactReviewStatus | None = None,
    stage: ArtifactStage | None = None,
    keyword: str | None = None,
) -> Page[ArtifactRead]:
    """Return one page of the files that belong to a task."""

    task = await get_task(session, task_id)

    stmt = select(Artifact).where(
        Artifact.task_id == task_id,
        Artifact.project_id == task.project_id,
    )

    if review_status is not None:
        stmt = stmt.where(Artifact.review_status == review_status.value)

    if stage is not None:
        stmt = stmt.where(Artifact.stage == stage.value)

    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Artifact.relative_path.ilike(pattern),
                Artifact.original_filename.ilike(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(await session.scalar(count_stmt) or 0)

    stmt = (
        stmt.order_by(Artifact.created_at.desc(), Artifact.id)
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    items = [ArtifactRead.model_validate(row) for row in rows]
    return build_page(items, total, params)


async def review_artifact(
    session: AsyncSession,
    artifact_id: UUID,
    payload: ArtifactReviewRequest,
) -> Artifact:
    """Move an artifact into a reviewed state and record the decision.

    The decision is additionally appended to the approval trail, so the
    comment and the reviewer stay traceable even if the artifact is replaced
    by a newer revision later on.
    """

    artifact = await get_artifact(session, artifact_id)

    if artifact.review_status == ArtifactReviewStatus.SUPERSEDED.value:
        raise ValidationException("该文件已被新版本取代，不能再审核")

    await append_approval(
        session,
        ApprovalAppend(
            project_id=artifact.project_id,
            target_type=ApprovalTargetType.ARTIFACT,
            target_id=artifact.id,
            decision=ApprovalDecision(payload.decision),
            approver=payload.reviewed_by,
            comment=payload.comment,
        ),
    )

    artifact.review_status = payload.decision
    artifact.reviewed_by = payload.reviewed_by
    artifact.reviewed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(artifact)
    return artifact
