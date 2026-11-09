"""Workflow endpoints.

The endpoints are a thin layer over the workflow service: they parse the
request, hand it to the service and render the result. They never touch the
checkpointer, never compose a graph and never expose the internals of
LangGraph.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workflow_runtime, pagination_params
from app.schemas.common import Page, PageParams
from app.schemas.workflow import (
    WorkflowEventRead,
    WorkflowRead,
    WorkflowResumeRequest,
    WorkflowStartRequest,
)
from app.services import workflows as workflow_service
from app.services.workflow_runtime import WorkflowRuntime

router = APIRouter()


@router.post(
    "/tasks/{task_id}/workflow/start",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="启动研发工作流",
    description=(
        "为任务启动一次工作流并同步执行到第一个审批点；"
        "节点均为本地模拟，不会调用任何大模型。"
    ),
)
async def start_workflow(
    task_id: UUID,
    payload: WorkflowStartRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    runtime: Annotated[WorkflowRuntime, Depends(get_workflow_runtime)],
) -> WorkflowRead:
    instance = await workflow_service.start_workflow(db, runtime, task_id, payload)
    return await workflow_service.to_read(db, instance)


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowRead,
    summary="查询工作流详情",
    description="返回服务端整理后的工作流视图，不包含图内部状态。",
)
async def get_workflow(
    workflow_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowRead:
    instance = await workflow_service.get_workflow(db, workflow_id)
    return await workflow_service.to_read(db, instance)


@router.post(
    "/workflows/{workflow_id}/resume",
    response_model=WorkflowRead,
    summary="推进工作流",
    description=(
        "提交人工审批结果，或在无审批时从检查点继续执行；"
        "服务端会先校验工作流状态与 thread_id，审批决定先入库再驱动流程。"
    ),
)
async def resume_workflow(
    workflow_id: UUID,
    payload: WorkflowResumeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    runtime: Annotated[WorkflowRuntime, Depends(get_workflow_runtime)],
) -> WorkflowRead:
    instance = await workflow_service.resume_workflow(db, runtime, workflow_id, payload)
    return await workflow_service.to_read(db, instance)


@router.get(
    "/workflows/{workflow_id}/logs",
    response_model=Page[WorkflowEventRead],
    summary="查询工作流日志",
    description="返回平台自有的事件日志，不是 LangGraph 的内部状态。",
)
async def list_workflow_logs(
    workflow_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[PageParams, Depends(pagination_params)],
) -> Page[WorkflowEventRead]:
    return await workflow_service.list_workflow_logs(db, workflow_id, page)
