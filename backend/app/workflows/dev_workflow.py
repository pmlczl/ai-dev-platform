"""The development workflow - a deterministic mock of a研发 workflow.

The graph is built with LangGraph. Every node is a simulation: no model is
called, the produced artifact is a template that is filled with the data of
the task. What is *not* simulated is the orchestration itself:

* the state of a run lives in the checkpointer, one thread per instance,
* the approval node calls ``interrupt()`` and therefore pauses the run until
  a human decides,
* a rejected artifact leads back into the generation node, so the rework
  round is a real second run of the graph.

Every side effect that happens before an interrupt is idempotent, because
LangGraph re-executes the node that was interrupted when the run is resumed:

* the artifact of an iteration is stored under a path that is derived from
  the instance and the iteration, and an existing artifact is reused,
* the event log is keyed by an ``event_key``,
* the state of an instance is only ever assigned, never incremented.
"""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

import anyio
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.core.storage import resolve_within_root, sha256_of_file
from app.models.artifact import Artifact
from app.models.enums import TaskStatus, WorkflowStatus
from app.models.task import DevelopmentTask
from app.models.workflow import WorkflowInstance
from app.models.workflow_event import WorkflowEvent
from app.services.artifacts import store_workflow_artifact
from app.services.workflow_store import (
    append_event,
    approval_request_id,
    now,
    update_instance,
)
from app.workflows.base import BaseWorkflow, WorkflowExecutionError

logger = get_logger(__name__)

#: Sections every generated artifact has to contain.
REQUIRED_SECTIONS = ("## 需求描述", "## 实现方案", "## 验收标准")
#: Section that carries the revision comments of the previous round.
REVISION_SECTION = "## 修改意见"
#: Number of characters of the artifact that are shown in the approval panel.
PREVIEW_LENGTH = 500


class DevWorkflowState(TypedDict, total=False):
    """State of one run of the development workflow.

    Every value is a plain JSON type: the state is written to the checkpointer
    and has to survive a round trip through it.
    """

    workflow_id: str
    project_id: str
    task_id: str
    thread_id: str
    iteration: int
    task_title: str
    task_valid: bool
    failure_reason: str | None
    revision_comments: list[str]
    artifact_id: str
    artifact_version: int
    artifact_relative_path: str
    artifact_sha256: str
    validation_passed: bool
    validation_issues: list[str]
    decision: str
    approver: str
    approval_comment: str
    result: str


def _render_artifact(state: DevWorkflowState) -> str:
    """Render the content of the simulated artifact.

    The template is deterministic: the same task and the same revision
    comments always produce the same file.
    """

    comments = list(state.get("revision_comments") or [])
    lines = [
        f"# 模拟研发产物 - {state.get('task_title', '')}",
        "",
        f"- 工作流实例: {state.get('workflow_id', '')}",
        f"- 迭代轮次: {state.get('iteration', 1)}",
        f"- 任务: {state.get('task_id', '')}",
        "",
        REQUIRED_SECTIONS[0],
        "本节由模拟节点生成，未调用任何大模型。",
        "",
        REQUIRED_SECTIONS[1],
        "本节描述实现方案，同样由模拟节点生成。",
        "",
        REQUIRED_SECTIONS[2],
        "本节描述验收标准，同样由模拟节点生成。",
    ]
    if comments:
        lines.append("")
        lines.append(REVISION_SECTION)
        lines.extend(f"- {comment}" for comment in comments)
    return "\n".join(lines) + "\n"


async def _artifact_count(workflow_instance_id: UUID) -> int:
    """Return the number of artifacts the workflow has produced so far."""

    async with SessionLocal() as session:
        total = await session.scalar(
            select(func.count(Artifact.id)).where(
                Artifact.workflow_instance_id == workflow_instance_id,
            )
        )
    return int(total or 0)


async def load_task(state: DevWorkflowState) -> dict[str, Any]:
    """Load the task of the workflow and make sure it can be worked on.

    The node does not raise when the task cannot be worked on: the reason is
    handed to the routing function, which sends the run to ``fail_workflow``.
    A raising node would abort the graph without recording the reason.
    """

    task_id = UUID(state["task_id"])
    workflow_id = UUID(state["workflow_id"])
    iteration = int(state.get("iteration", 1))

    async with SessionLocal() as session:
        task = await session.get(DevelopmentTask, task_id)
        if task is None or task.deleted_at is not None:
            return {"task_valid": False, "failure_reason": "任务不存在或已被删除"}
        if task.status in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
            return {"task_valid": False, "failure_reason": "任务已结束，无法启动工作流"}

        if task.status == TaskStatus.PENDING.value:
            task.status = TaskStatus.IN_PROGRESS.value
            await session.commit()
        title = task.title
        await update_instance(
            session,
            workflow_id,
            status=WorkflowStatus.RUNNING.value,
            current_step="load_task",
        )
        await append_event(
            session,
            workflow_id,
            step="load_task",
            event="node_started",
            event_key=f"node_started:load_task:{iteration}",
            message=f"载入任务 {task.title}",
            payload={"task_id": str(task_id)},
        )
    return {"task_title": title, "task_valid": True, "failure_reason": None}


async def generate_demo_artifact(state: DevWorkflowState) -> dict[str, Any]:
    """Produce the artifact of the current iteration."""

    workflow_id = UUID(state["workflow_id"])
    task_id = UUID(state["task_id"])
    iteration = int(state.get("iteration", 1))
    relative_path = f"workflow/{workflow_id}/iteration-{iteration}/demo-artifact.md"

    async with SessionLocal() as session:
        artifact = await store_workflow_artifact(
            session,
            workflow_instance_id=workflow_id,
            task_id=task_id,
            relative_path=relative_path,
            content=_render_artifact(state),
            created_by="workflow:dev_workflow",
        )
        await append_event(
            session,
            workflow_id,
            step="generate_demo_artifact",
            event="artifact_generated",
            event_key=f"artifact_generated:{iteration}",
            message=f"生成第 {iteration} 轮产物 {artifact.relative_path}",
            payload={
                "artifact_id": str(artifact.id),
                "relative_path": artifact.relative_path,
                "sha256": artifact.sha256,
            },
        )
        await update_instance(
            session,
            workflow_id,
            current_step="generate_demo_artifact",
            iteration=iteration,
        )
    return {
        "artifact_id": str(artifact.id),
        "artifact_version": artifact.version,
        "artifact_relative_path": artifact.relative_path,
        "artifact_sha256": artifact.sha256,
    }


async def validate_artifact(state: DevWorkflowState) -> dict[str, Any]:
    """Check the artifact that was just produced.

    The rules are the ones a reviewer would check by hand: the file has to
    exist, its digest has to match the one in the database, it must not be
    empty, it has to contain the required sections - and a rework has to
    carry the revision comments of the previous round.
    """

    workflow_id = UUID(state["workflow_id"])
    artifact_id = UUID(state["artifact_id"])
    iteration = int(state.get("iteration", 1))
    issues: list[str] = []

    async with SessionLocal() as session:
        artifact = await session.get(Artifact, artifact_id)
        if artifact is None:
            issues.append("产物记录不存在")
        elif not artifact.storage_path:
            issues.append("产物没有对应的文件")
        else:
            path = resolve_within_root(artifact.storage_path)
            if not path.exists():
                issues.append("产物文件缺失")
            else:
                digest = await anyio.to_thread.run_sync(sha256_of_file, path)
                if digest != artifact.sha256:
                    issues.append("产物哈希与记录不一致")
                content = await anyio.to_thread.run_sync(path.read_text, "utf-8")
                if not content.strip():
                    issues.append("产物内容为空")
                for section in REQUIRED_SECTIONS:
                    if section not in content:
                        issues.append(f"产物缺少章节 {section}")
                if state.get("revision_comments") and REVISION_SECTION not in content:
                    issues.append("返工产物未包含上一轮的修改意见")

        passed = not issues
        await append_event(
            session,
            workflow_id,
            step="validate_artifact",
            event="validation_passed" if passed else "validation_failed",
            event_key=f"validation:{iteration}",
            message="产物校验通过" if passed else "产物校验未通过",
            payload={"issues": issues},
        )

    reason = None if passed else "产物校验未通过：" + "；".join(issues)
    return {
        "validation_passed": passed,
        "validation_issues": issues,
        "failure_reason": reason,
    }


async def human_approval(state: DevWorkflowState) -> dict[str, Any]:
    """Pause the run until a human approved the artifact.

    The decision is read from the database instead of from the interrupt:
    the approval record is written before the graph is driven, so a node that
    is replayed after a restart finds the decision of its round and does not
    have to wait a second time. Only when no decision was taken the node
    interrupts and waits.
    """

    workflow_id = UUID(state["workflow_id"])
    iteration = int(state.get("iteration", 1))
    request_id = approval_request_id(workflow_id, iteration)
    request = {
        "request_id": request_id,
        "workflow_id": str(workflow_id),
        "iteration": iteration,
        "artifact_id": state.get("artifact_id"),
        "artifact_version": state.get("artifact_version"),
        "artifact_relative_path": state.get("artifact_relative_path"),
        "artifact_sha256": state.get("artifact_sha256"),
        "preview": await _preview(state),
        "revision_comments": list(state.get("revision_comments") or []),
        "requested_at": now().isoformat(),
    }

    async with SessionLocal() as session:
        await update_instance(
            session,
            workflow_id,
            status=WorkflowStatus.WAITING_APPROVAL.value,
            current_step="human_approval",
            pending_payload=request,
            pending_since=now(),
        )
        await append_event(
            session,
            workflow_id,
            step="human_approval",
            event="approval_requested",
            event_key=f"approval_requested:{iteration}",
            message=f"等待人工审批（第 {iteration} 轮）",
            payload=request,
        )
        decision = await _take_decision(session, workflow_id, iteration, request_id)

    if decision is None:
        # Nobody decided yet: the run pauses here until a decision arrives.
        decision = interrupt(request)

    outcome = str(decision.get("decision", "")).strip().lower()
    if outcome not in ("approved", "rejected"):
        raise WorkflowExecutionError("审批结果不合法")

    # The event carries the decision, so that a node that is replayed after a
    # crash finds it again instead of waiting a second time.
    async with SessionLocal() as session:
        await append_event(
            session,
            workflow_id,
            step="human_approval",
            event="approval_received",
            event_key=f"approval_received:{iteration}",
            message=f"收到审批结果：{outcome}",
            payload={
                "decision": outcome,
                "approver": decision.get("approver"),
                "comment": decision.get("comment"),
                "request_id": request_id,
            },
        )
        await _clear_pending_decision(session, workflow_id)

    logger.info(
        "Workflow %s got the decision %s in iteration %s",
        workflow_id,
        outcome,
        iteration,
    )
    return {
        "decision": outcome,
        "approver": decision.get("approver"),
        "approval_comment": decision.get("comment"),
    }


async def handle_revision_comments(state: DevWorkflowState) -> dict[str, Any]:
    """Take the revision comments of the reviewer and start the next round.

    The next iteration is derived from the number of artifacts that exist:
    a node that is replayed after a restart computes the same value and does
    not skip a round.
    """

    workflow_id = UUID(state["workflow_id"])
    comments = list(state.get("revision_comments") or [])
    comment = state.get("approval_comment")
    if comment:
        comments.append(comment)

    iteration = await _artifact_count(workflow_id) + 1
    async with SessionLocal() as session:
        await update_instance(
            session,
            workflow_id,
            status=WorkflowStatus.RUNNING.value,
            current_step="handle_revision_comments",
            iteration=iteration,
            last_decision=state.get("decision"),
            pending_payload=None,
            pending_since=None,
        )
        await append_event(
            session,
            workflow_id,
            step="handle_revision_comments",
            event="revision_handled",
            event_key=f"revision_handled:{iteration}",
            message=f"处理修改意见，进入第 {iteration} 轮",
            payload={"iteration": iteration, "comments": comments},
        )
    return {
        "revision_comments": comments,
        "iteration": iteration,
        "failure_reason": None,
        "result": "rework",
    }


async def complete_workflow(state: DevWorkflowState) -> dict[str, Any]:
    """Finish the workflow and mark the task as done."""

    workflow_id = UUID(state["workflow_id"])
    iteration = int(state.get("iteration", 1))
    async with SessionLocal() as session:
        instance = await session.get(WorkflowInstance, workflow_id)
        if instance is not None and instance.task_id is not None:
            task = await session.get(DevelopmentTask, instance.task_id)
            if task is not None and task.deleted_at is None:
                task.status = TaskStatus.COMPLETED.value
        await update_instance(
            session,
            workflow_id,
            status=WorkflowStatus.COMPLETED.value,
            current_step="complete_workflow",
            finished_at=now(),
            pending_payload=None,
            pending_since=None,
            last_decision=state.get("decision"),
        )
        await append_event(
            session,
            workflow_id,
            step="complete_workflow",
            event="workflow_completed",
            event_key=f"workflow_completed:{iteration}",
            message="工作流已完成",
            payload={"task_id": str(instance.task_id) if instance else None},
        )
    return {"result": "completed"}


async def fail_workflow(state: DevWorkflowState) -> dict[str, Any]:
    """Stop the workflow and record why it could not continue."""

    workflow_id = UUID(state["workflow_id"])
    iteration = int(state.get("iteration", 1))
    issues = list(state.get("validation_issues") or [])
    reason = state.get("failure_reason") or "工作流未能完成"
    if not state.get("failure_reason") and issues:
        reason = f"工作流未能完成：{'；'.join(issues)}"
    logger.warning("Workflow %s failed in iteration %s: %s", workflow_id, iteration, reason)
    async with SessionLocal() as session:
        await update_instance(
            session,
            workflow_id,
            status=WorkflowStatus.FAILED.value,
            current_step="fail_workflow",
            finished_at=now(),
            error_message=reason,
        )
        await append_event(
            session,
            workflow_id,
            step="fail_workflow",
            event="workflow_failed",
            event_key=f"workflow_failed:{iteration}",
            message=reason,
            payload={"issues": issues},
        )
    return {"result": "failed"}


def route_after_load(state: DevWorkflowState) -> str:
    """Decide where the run goes after the task was loaded."""

    if state.get("task_valid", True):
        return "generate_demo_artifact"
    return "fail_workflow"


def route_after_validation(state: DevWorkflowState) -> str:
    """Decide where the run goes after the artifact was validated."""

    if state.get("validation_passed"):
        return "human_approval"
    if int(state.get("iteration", 1)) >= get_settings().workflow_max_iterations:
        return "fail_workflow"
    return "handle_revision_comments"


def route_after_approval(state: DevWorkflowState) -> str:
    """Decide where the run goes after the approval."""

    if state.get("decision") == "approved":
        return "complete_workflow"
    return "handle_revision_comments"


class DevWorkflow(BaseWorkflow):
    """The development workflow of the platform."""

    name = "dev_workflow"
    description = (
        "载入任务 → 生成模拟产物 → 校验 → 人工审批 → 完成；"
        "审批退回时进入修改意见处理并重新生成。"
    )

    def build_graph(self, checkpointer: Any | None = None) -> Any:
        """Build and compile the graph of the workflow."""

        builder = StateGraph(DevWorkflowState)
        builder.add_node("load_task", load_task)
        builder.add_node("generate_demo_artifact", generate_demo_artifact)
        builder.add_node("validate_artifact", validate_artifact)
        builder.add_node("human_approval", human_approval)
        builder.add_node("handle_revision_comments", handle_revision_comments)
        builder.add_node("complete_workflow", complete_workflow)
        builder.add_node("fail_workflow", fail_workflow)

        builder.add_edge(START, "load_task")
        builder.add_conditional_edges(
            "load_task",
            route_after_load,
            {
                "generate_demo_artifact": "generate_demo_artifact",
                "fail_workflow": "fail_workflow",
            },
        )
        builder.add_edge("generate_demo_artifact", "validate_artifact")
        builder.add_conditional_edges(
            "validate_artifact",
            route_after_validation,
            {
                "human_approval": "human_approval",
                "handle_revision_comments": "handle_revision_comments",
                "fail_workflow": "fail_workflow",
            },
        )
        builder.add_conditional_edges(
            "human_approval",
            route_after_approval,
            {
                "complete_workflow": "complete_workflow",
                "handle_revision_comments": "handle_revision_comments",
            },
        )
        builder.add_edge("handle_revision_comments", "generate_demo_artifact")
        builder.add_edge("complete_workflow", END)
        builder.add_edge("fail_workflow", END)
        return builder.compile(checkpointer=checkpointer)


async def _preview(state: DevWorkflowState) -> str:
    """Return the beginning of the artifact for the approval panel."""

    artifact_id = state.get("artifact_id")
    if not artifact_id:
        return ""
    async with SessionLocal() as session:
        artifact = await session.get(Artifact, UUID(artifact_id))
        if artifact is None or not artifact.storage_path:
            return ""
        path = resolve_within_root(artifact.storage_path)
        if not path.exists():
            return ""
        content = await anyio.to_thread.run_sync(path.read_text, "utf-8")
    return content[:PREVIEW_LENGTH]


async def _take_decision(
    session: Any,
    workflow_id: UUID,
    iteration: int,
    request_id: str,
) -> dict[str, Any] | None:
    """Return the approval decision of the given round.

    Two channels are consulted:

    * ``pending_decision`` of the instance - the fast path. It is written by
      the workflow service before the graph is driven and consumed exactly
      once, so that a replay cannot apply the same decision twice.
    * the ``approval_received`` event of the round - the durable path. The
      event is written before the decision is consumed, so a crash between
      the two does not lose the decision.
    """

    instance = await session.get(WorkflowInstance, workflow_id)
    if instance is not None and instance.pending_decision:
        decision = dict(instance.pending_decision)
        if decision.get("request_id") == request_id:
            return decision

    event = await session.scalar(
        select(WorkflowEvent).where(
            WorkflowEvent.workflow_instance_id == workflow_id,
            WorkflowEvent.event_key == f"approval_received:{iteration}",
        )
    )
    if event is not None and event.payload:
        payload = dict(event.payload)
        if payload.get("decision"):
            return {
                "decision": payload.get("decision"),
                "approver": payload.get("approver"),
                "comment": payload.get("comment"),
                "request_id": request_id,
            }
    return None


async def _clear_pending_decision(session: Any, workflow_id: UUID) -> None:
    """Drop the stored decision once it was applied to the graph."""

    instance = await session.get(WorkflowInstance, workflow_id)
    if instance is None or instance.pending_decision is None:
        return
    instance.pending_decision = None
    await session.commit()
