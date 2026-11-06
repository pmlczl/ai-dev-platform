"""Artifact endpoints: upload, download, metadata, versions and review.

The endpoints only orchestrate: every decision about paths, file types and
versions is taken by the service layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.models.enums import ArtifactReviewStatus, ArtifactStage
from app.schemas.artifact import ArtifactRead, ArtifactReviewRequest
from app.schemas.common import Page, PageParams
from app.services import artifacts as artifact_service

router = APIRouter()


async def _iter_upload(upload: UploadFile) -> AsyncIterator[bytes]:
    """Yield the content of an upload in chunks."""

    while True:
        chunk = await upload.read(artifact_service.CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


@router.post(
    "/tasks/{task_id}/artifacts",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
    summary="上传任务文件",
    description=(
        "上传一个文件并保存到独立的 storage 目录，数据库只保存元数据与相对路径。"
        "项目由任务推导，调用方无法伪造归属；重复上传同一相对路径会生成新版本，"
        "历史版本不会被覆盖。"
    ),
)
async def upload_artifact(
    task_id: UUID,
    file: Annotated[UploadFile, File(description="待上传的文件")],
    db: Annotated[AsyncSession, Depends(get_db)],
    relative_path: Annotated[
        str | None,
        Form(description="项目内的相对路径，默认取上传时的文件名"),
    ] = None,
    stage: Annotated[
        ArtifactStage,
        Form(description="文件所属阶段"),
    ] = ArtifactStage.DEVELOPMENT,
    created_by: Annotated[
        str | None,
        Form(max_length=120, description="上传人，仅用于审计"),
    ] = None,
) -> ArtifactRead:
    upload = artifact_service.FileUpload(
        filename=file.filename or "file",
        chunks=_iter_upload(file),
        declared_size=file.size,
    )
    artifact = await artifact_service.upload_artifact(
        db,
        task_id,
        upload,
        relative_path=relative_path,
        stage=stage,
        created_by=created_by,
    )
    return ArtifactRead.model_validate(artifact)


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ArtifactRead,
    summary="查询文件元数据",
    description="返回文件的阶段、版本、SHA256、审核状态和创建时间等全部元信息。",
)
async def get_artifact(
    artifact_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArtifactRead:
    artifact = await artifact_service.get_artifact(db, artifact_id)
    return ArtifactRead.model_validate(artifact)


@router.get(
    "/artifacts/{artifact_id}/download",
    summary="下载文件",
    description="按原始文件名下载文件内容，响应头附带 X-Content-SHA256 便于校验。",
)
async def download_artifact(
    artifact_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    artifact = await artifact_service.get_artifact(db, artifact_id)
    path = artifact_service.resolve_artifact_file(artifact)
    filename = artifact.original_filename or PurePosixPath(artifact.relative_path).name
    return FileResponse(
        path,
        media_type=artifact.file_type,
        filename=filename,
        headers={"X-Content-SHA256": artifact.sha256},
    )


@router.get(
    "/tasks/{task_id}/artifacts",
    response_model=Page[ArtifactRead],
    summary="查询任务文件列表",
    description="分页返回任务下的文件，可按审核状态、阶段过滤并按名称搜索。",
)
async def list_task_artifacts(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[PageParams, Depends(pagination_params)],
    review_status_filter: Annotated[
        ArtifactReviewStatus | None,
        Query(alias="review_status", description="按审核状态过滤"),
    ] = None,
    stage_filter: Annotated[
        ArtifactStage | None,
        Query(alias="stage", description="按阶段过滤"),
    ] = None,
    keyword: Annotated[
        str | None,
        Query(max_length=200, description="按文件路径或原始文件名模糊匹配"),
    ] = None,
) -> Page[ArtifactRead]:
    return await artifact_service.list_task_artifacts(
        db,
        task_id,
        page,
        review_status=review_status_filter,
        stage=stage_filter,
        keyword=keyword,
    )


@router.post(
    "/artifacts/{artifact_id}/revisions",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建文件新版本",
    description="为已有文件追加一个新版本，旧版本自动转为 superseded 且内容保留。",
)
async def create_revision(
    artifact_id: UUID,
    file: Annotated[UploadFile, File(description="新版本的文件内容")],
    db: Annotated[AsyncSession, Depends(get_db)],
    stage: Annotated[
        ArtifactStage | None,
        Form(description="新版本的阶段，默认沿用上一版本"),
    ] = None,
    created_by: Annotated[
        str | None,
        Form(max_length=120, description="上传人，仅用于审计"),
    ] = None,
) -> ArtifactRead:
    upload = artifact_service.FileUpload(
        filename=file.filename or "file",
        chunks=_iter_upload(file),
        declared_size=file.size,
    )
    artifact = await artifact_service.create_revision(
        db,
        artifact_id,
        upload,
        stage=stage,
        created_by=created_by,
    )
    return ArtifactRead.model_validate(artifact)


@router.post(
    "/artifacts/{artifact_id}/review",
    response_model=ArtifactRead,
    summary="审核文件",
    description="把文件状态推进到 approved 或 rejected，并写入审核人与审核时间。",
)
async def review_artifact(
    artifact_id: UUID,
    payload: ArtifactReviewRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArtifactRead:
    artifact = await artifact_service.review_artifact(db, artifact_id, payload)
    return ArtifactRead.model_validate(artifact)
