"""Development task endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import Page, PageParams
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import tasks as task_service

router = APIRouter()


@router.post(
    "/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建开发任务",
    description="创建一个任务并归属到指定项目，项目不存在时返回 404。",
)
async def create_task(
    payload: TaskCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    task = await task_service.create_task(db, payload)
    return await task_service.to_read(db, task)


@router.get(
    "/tasks",
    response_model=Page[TaskRead],
    summary="分页查询开发任务",
    description="可按项目、状态、优先级过滤，按标题模糊搜索。",
)
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[PageParams, Depends(pagination_params)],
    project_id: Annotated[
        UUID | None,
        Query(description="只返回指定项目下的任务"),
    ] = None,
    status_filter: Annotated[
        TaskStatus | None,
        Query(alias="status", description="按任务状态过滤"),
    ] = None,
    priority_filter: Annotated[
        TaskPriority | None,
        Query(alias="priority", description="按优先级过滤"),
    ] = None,
    keyword: Annotated[
        str | None,
        Query(max_length=200, description="按标题模糊匹配"),
    ] = None,
) -> Page[TaskRead]:
    return await task_service.list_tasks(
        db,
        page,
        project_id=project_id,
        status=status_filter,
        priority=priority_filter,
        keyword=keyword,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskRead,
    summary="查询开发任务详情",
)
async def get_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    task = await task_service.get_task(db, task_id)
    return await task_service.to_read(db, task)


@router.put(
    "/tasks/{task_id}",
    response_model=TaskRead,
    summary="更新开发任务",
    description="部分更新：只有请求体中出现的字段会被写入。",
)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    task = await task_service.update_task(db, task_id, payload)
    return await task_service.to_read(db, task)
