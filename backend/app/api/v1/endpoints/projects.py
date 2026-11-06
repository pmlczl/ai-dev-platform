"""Project management endpoints.

All routes are mounted below ``/api/v1`` by the version router.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.models.enums import ProjectStatus, TaskStatus
from app.schemas.common import Page, PageParams
from app.schemas.project import ProjectCreate, ProjectListItem, ProjectRead, ProjectUpdate
from app.schemas.task import TaskRead
from app.services import projects as project_service
from app.services import tasks as task_service

router = APIRouter()


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建项目",
    description="创建一个项目。项目编号在全局唯一，重复时返回 409。",
)
async def create_project(
    payload: ProjectCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectRead:
    project = await project_service.create_project(db, payload)
    return project_service.to_read(project)


@router.get(
    "/projects",
    response_model=Page[ProjectListItem],
    summary="分页查询项目",
    description="按状态过滤，按名称或编号模糊搜索，默认按创建时间倒序。",
)
async def list_projects(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[PageParams, Depends(pagination_params)],
    status_filter: Annotated[
        ProjectStatus | None,
        Query(alias="status", description="按项目状态过滤"),
    ] = None,
    keyword: Annotated[
        str | None,
        Query(max_length=200, description="按名称或编号模糊匹配"),
    ] = None,
) -> Page[ProjectListItem]:
    return await project_service.list_projects(
        db,
        page,
        status=status_filter,
        keyword=keyword,
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="查询项目详情",
)
async def get_project(
    project_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectRead:
    project = await project_service.get_project(db, project_id)
    return project_service.to_read(project)


@router.put(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="更新项目",
    description="部分更新：只有请求体中出现的字段会被写入。",
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectRead:
    project = await project_service.update_project(db, project_id, payload)
    return project_service.to_read(project)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除项目",
    description="软删除项目，并级联软删其任务；数据与审批记录保留。",
)
async def delete_project(
    project_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await project_service.delete_project(db, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/tasks",
    response_model=Page[TaskRead],
    summary="查询项目下的任务",
)
async def list_project_tasks(
    project_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[PageParams, Depends(pagination_params)],
    status_filter: Annotated[
        TaskStatus | None,
        Query(alias="status", description="按任务状态过滤"),
    ] = None,
) -> Page[TaskRead]:
    await project_service.get_project(db, project_id)
    return await task_service.list_tasks(
        db,
        page,
        project_id=project_id,
        status=status_filter,
    )
