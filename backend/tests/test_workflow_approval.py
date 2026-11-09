"""Tests for the LangGraph workflow and the human approval.

The suite drives the real endpoints against the migrated database and the
real SQLite checkpointer, so the interrupt, the resume and the restart
behaviour are exercised the way the service uses them.

Every scenario of the design document is covered:

1. approval completes the workflow,
2. a rejection starts a rework round,
3. the rework round can be approved as well,
4. a workflow survives a restart of the service,
5. a repeated approval is rejected,
6. two workflows of the same project stay isolated,
7. invalid requests are rejected with the right status code,
8. the side effects before an interrupt are idempotent.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.storage import resolve_within_root, sha256_of_file
from app.main import create_app
from app.models.approval import ApprovalRecord
from app.models.artifact import Artifact
from app.models.enums import ApprovalDecision, ApprovalTargetType, WorkflowStatus
from app.models.workflow import WorkflowInstance
from app.models.workflow_event import WorkflowEvent
from app.schemas.approval import ApprovalAppend
from app.services.approvals import append_approval, list_approvals
from app.services.artifacts import store_workflow_artifact
from app.services.workflow_store import approval_request_key
from app.workflows.dev_workflow import generate_demo_artifact

APPROVER = "alice"


def _create_project(client, payload) -> dict:
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_task(client, project_id: str, title: str = "工作流测试任务") -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start(client, task_id: str, **payload) -> dict:
    response = client.post(f"/api/v1/tasks/{task_id}/workflow/start", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _resume(client, workflow_id: str, thread_id: str, **payload):
    body = {"thread_id": thread_id, **payload}
    return client.post(f"/api/v1/workflows/{workflow_id}/resume", json=body)


def _events(client, workflow_id: str) -> list[dict]:
    response = client.get(f"/api/v1/workflows/{workflow_id}/logs")
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _artifact_count(db_session, workflow_id: str) -> int:
    await db_session.rollback()
    total = await db_session.scalar(
        select(func.count(Artifact.id)).where(
            Artifact.workflow_instance_id == UUID(workflow_id),
        )
    )
    return int(total or 0)


async def _event_count(db_session, workflow_id: str, event_key: str) -> int:
    await db_session.rollback()
    total = await db_session.scalar(
        select(func.count(WorkflowEvent.id)).where(
            WorkflowEvent.workflow_instance_id == UUID(workflow_id),
            WorkflowEvent.event_key == event_key,
        )
    )
    return int(total or 0)


async def _approvals(db_session, project_id: str, workflow_id: str) -> list[ApprovalRecord]:
    await db_session.rollback()
    return await list_approvals(
        db_session,
        UUID(project_id),
        ApprovalTargetType.WORKFLOW_INSTANCE,
        UUID(workflow_id),
    )


async def test_approval_completes_the_workflow(client, db_session, project_payload):
    """Scenario 1: the artifact is approved, the workflow and the task end."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    assert started["status"] == WorkflowStatus.WAITING_APPROVAL.value
    assert started["current_step"] == "human_approval"
    assert started["iteration"] == 1
    # The thread is derived from the instance on the server side.
    assert started["thread_id"] == f"wf-{started['id']}"
    assert started["approvals"] == []
    assert started["pending_approval"]["request_id"] == f"{started['id']}:1"
    assert started["current_artifact"]["relative_path"].endswith(
        "iteration-1/demo-artifact.md",
    )

    response = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
        comment="可以，进入下一阶段",
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == WorkflowStatus.COMPLETED.value
    assert body["current_step"] == "complete_workflow"
    assert len(body["approvals"]) == 1
    assert body["approvals"][0]["decision"] == ApprovalDecision.APPROVED.value
    assert body["approvals"][0]["approver"] == APPROVER
    assert body["approvals"][0]["sequence"] == 1
    assert body["current_artifact"]["review_status"] == "approved"

    # The task is done as well.
    task_view = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert task_view["status"] == "completed"

    # The file of the artifact exists and its digest matches the database.
    await db_session.rollback()
    artifact = await db_session.get(Artifact, UUID(body["current_artifact"]["id"]))
    assert artifact is not None
    path = resolve_within_root(artifact.storage_path)
    assert path.is_file()
    assert sha256_of_file(path) == artifact.sha256

    records = await _approvals(db_session, project["id"], started["id"])
    assert len(records) == 1
    assert records[0].decision == ApprovalDecision.APPROVED.value


async def test_rejection_starts_a_rework_round(client, db_session, project_payload):
    """Scenario 2: a rejected artifact is regenerated with the comments."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    response = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="rejected",
        approver=APPROVER,
        comment="请补充异常处理",
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # The workflow waits for the approval of the second round.
    assert body["status"] == WorkflowStatus.WAITING_APPROVAL.value
    assert body["iteration"] == 2
    assert body["current_artifact"]["relative_path"].endswith(
        "iteration-2/demo-artifact.md",
    )
    assert body["pending_approval"]["revision_comments"] == ["请补充异常处理"]
    assert body["approvals"][0]["decision"] == ApprovalDecision.REJECTED.value
    assert body["approvals"][0]["comment"] == "请补充异常处理"

    # The new artifact really carries the comments of the reviewer.
    await db_session.rollback()
    artifact = await db_session.get(Artifact, UUID(body["current_artifact"]["id"]))
    path = resolve_within_root(artifact.storage_path)
    content = path.read_text("utf-8")
    assert "请补充异常处理" in content
    assert "## 修改意见" in content

    # The first artifact is still there - a rework never overwrites it.
    assert await _artifact_count(db_session, started["id"]) == 2

    events = [event["event"] for event in _events(client, started["id"])]
    assert "revision_handled" in events
    assert events.count("artifact_generated") == 2


async def test_the_rework_round_can_be_approved(client, db_session, project_payload):
    """Scenario 3: the second approval completes the workflow."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    rejected = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="rejected",
        approver=APPROVER,
        comment="请补充异常处理",
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["iteration"] == 2

    approved = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver="bob",
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()

    assert body["status"] == WorkflowStatus.COMPLETED.value
    assert len(body["approvals"]) == 2
    assert [record["sequence"] for record in body["approvals"]] == [1, 2]
    assert [record["decision"] for record in body["approvals"]] == ["rejected", "approved"]

    records = await _approvals(db_session, project["id"], started["id"])
    assert len(records) == 2


async def test_a_workflow_survives_a_restart(client, db_session, project_payload):
    """Scenario 4: the state of a run survives a restart of the service."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    # A second application instance - a restart of the service. It opens the
    # checkpointer again and finds the run in the very same file.
    with TestClient(create_app()) as restarted:
        detail = restarted.get(f"/api/v1/workflows/{started['id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == WorkflowStatus.WAITING_APPROVAL.value
        assert detail.json()["iteration"] == 1

        response = _resume(
            restarted,
            started["id"],
            started["thread_id"],
            decision="approved",
            approver=APPROVER,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == WorkflowStatus.COMPLETED.value


async def test_a_crashed_instance_is_recovered_after_a_restart(
    client,
    db_session,
    project_payload,
):
    """Scenario 4b: an instance that was running when the process died."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    # Simulate a crash in the middle of the run: the instance claims to be
    # running and carries no approval summary.
    await db_session.rollback()
    instance = await db_session.get(WorkflowInstance, UUID(started["id"]))
    instance.status = WorkflowStatus.RUNNING.value
    instance.pending_payload = None
    await db_session.commit()

    # The restarted service reconciles the instances that were left behind.
    with TestClient(create_app()) as restarted:
        detail = restarted.get(f"/api/v1/workflows/{started['id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == WorkflowStatus.PAUSED.value

        # A paused instance is continued without a decision.
        resumed = restarted.post(
            f"/api/v1/workflows/{started['id']}/resume",
            json={"thread_id": started["thread_id"]},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == WorkflowStatus.WAITING_APPROVAL.value


async def test_a_repeated_approval_is_rejected(client, db_session, project_payload):
    """Scenario 5: the same decision is never applied twice."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    first = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
        idempotency_key="idem-0001",
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == WorkflowStatus.COMPLETED.value

    # The same idempotency key: the answer is the current state, no second
    # approval record and no second artifact are written.
    second = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
        idempotency_key="idem-0001",
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == WorkflowStatus.COMPLETED.value
    assert len(second.json()["approvals"]) == 1

    records = await _approvals(db_session, project["id"], started["id"])
    assert len(records) == 1
    assert await _artifact_count(db_session, started["id"]) == 1

    # Without an idempotency key the second submission is a conflict: the
    # workflow has already ended.
    third = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
    )
    assert third.status_code == 409, third.text
    assert third.json()["code"] == "CONFLICT"

    assert len(await _approvals(db_session, project["id"], started["id"])) == 1


async def test_a_second_submission_of_the_same_round_is_rejected(
    client,
    db_session,
    project_payload,
):
    """Scenario 5b: a decision of a round that is already closed."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    # A decision that was taken but never reached the graph - the process
    # died in between. The submission applies it instead of writing a
    # second record.
    await db_session.rollback()
    instance = await db_session.get(WorkflowInstance, UUID(started["id"]))

    await append_approval(
        db_session,
        ApprovalAppend(
            project_id=UUID(project["id"]),
            target_type=ApprovalTargetType.WORKFLOW_INSTANCE,
            target_id=instance.id,
            decision=ApprovalDecision.APPROVED,
            approver=APPROVER,
            idempotency_key=approval_request_key(f"{instance.id}:1"),
        ),
    )

    response = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == WorkflowStatus.COMPLETED.value

    # Only the record that was written before is there.
    records = await _approvals(db_session, project["id"], started["id"])
    assert len(records) == 1
    assert await _artifact_count(db_session, started["id"]) == 1


async def test_two_workflows_of_one_project_stay_isolated(
    client,
    db_session,
    project_payload,
):
    """Scenario 6: two tasks run next to each other without interfering."""

    project = _create_project(client, project_payload)
    first_task = _create_task(client, project["id"], "并行任务 A")
    second_task = _create_task(client, project["id"], "并行任务 B")

    first = _start(client, first_task["id"])
    second = _start(client, second_task["id"])

    assert first["id"] != second["id"]
    assert first["thread_id"] != second["thread_id"]
    assert first["current_artifact"]["id"] != second["current_artifact"]["id"]

    approved = _resume(
        client,
        first["id"],
        first["thread_id"],
        decision="approved",
        approver=APPROVER,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == WorkflowStatus.COMPLETED.value

    # The second workflow did not move.
    detail = client.get(f"/api/v1/workflows/{second['id']}").json()
    assert detail["status"] == WorkflowStatus.WAITING_APPROVAL.value
    assert detail["iteration"] == 1
    assert detail["approvals"] == []

    # The approval trail of the second workflow starts at 1 as well.
    approved = _resume(
        client,
        second["id"],
        second["thread_id"],
        decision="approved",
        approver="bob",
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == WorkflowStatus.COMPLETED.value
    assert [record["sequence"] for record in body["approvals"]] == [1]

    assert await _artifact_count(db_session, first["id"]) == 1
    assert await _artifact_count(db_session, second["id"]) == 1


async def test_invalid_requests_are_rejected(client, db_session, project_payload):
    """Scenario 7: the service validates the state and the parameters."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])

    # An unknown task cannot start a workflow.
    unknown = client.post(
        "/api/v1/tasks/00000000-0000-0000-0000-000000000000/workflow/start",
        json={},
    )
    assert unknown.status_code == 404, unknown.text

    # An unknown workflow key is not registered.
    unknown_key = client.post(
        f"/api/v1/tasks/{task['id']}/workflow/start",
        json={"workflow_key": "does_not_exist"},
    )
    assert unknown_key.status_code == 404, unknown_key.text

    started = _start(client, task["id"])

    # A second workflow for the same task is a conflict.
    duplicate = client.post(f"/api/v1/tasks/{task['id']}/workflow/start", json={})
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["existing_workflow_id"] == started["id"]

    # An unknown workflow cannot be read.
    assert client.get("/api/v1/workflows/00000000-0000-0000-0000-000000000000").status_code == 404

    # A thread id that does not belong to the instance is a conflict.
    mismatch = _resume(
        client,
        started["id"],
        "wf-00000000-0000-0000-0000-000000000000",
        decision="approved",
        approver=APPROVER,
    )
    assert mismatch.status_code == 409, mismatch.text

    # An unknown decision is rejected by the schema.
    invalid = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="maybe",
        approver=APPROVER,
    )
    assert invalid.status_code == 422, invalid.text

    # A decision without an approver is rejected as well.
    without_approver = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
    )
    assert without_approver.status_code == 422, without_approver.text

    # A workflow that waits for an approval needs a decision.
    without_decision = _resume(
        client,
        started["id"],
        started["thread_id"],
    )
    assert without_decision.status_code == 409, without_decision.text

    # A workflow that has ended cannot be continued.
    _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
    )
    ended = _resume(
        client,
        started["id"],
        started["thread_id"],
        decision="approved",
        approver=APPROVER,
    )
    assert ended.status_code == 409, ended.text


async def test_the_generation_node_is_idempotent(client, db_session, project_payload):
    """Scenario 8: a replayed node does not write a second artifact."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    await db_session.rollback()
    instance = await db_session.get(WorkflowInstance, UUID(started["id"]))
    artifact = started["current_artifact"]
    # The values are read right away: a rollback expires the instance and an
    # expired attribute cannot be loaded lazily in an async session.
    workflow_uuid = instance.id
    task_uuid = instance.task_id
    thread_id = instance.thread_id

    # The node is executed a second time - this is what LangGraph does when
    # the process died between the node and the checkpoint.
    state = {
        "workflow_id": str(workflow_uuid),
        "project_id": str(instance.project_id),
        "task_id": str(task_uuid),
        "thread_id": thread_id,
        "iteration": 1,
        "task_title": "工作流测试任务",
    }
    result = await generate_demo_artifact(state)
    assert result["artifact_id"] == artifact["id"]

    # No second row, no second file and no second event.
    assert await _artifact_count(db_session, started["id"]) == 1
    assert await _event_count(db_session, started["id"], "artifact_generated:1") == 1

    # The file of this workflow is written exactly once.
    await db_session.rollback()
    storage_path = await db_session.scalar(
        select(Artifact.storage_path).where(Artifact.id == UUID(artifact["id"])),
    )
    files = list(resolve_within_root(storage_path).parent.parent.rglob("demo-artifact.md"))
    assert len(files) == 1

    # The same holds for the storage helper itself.
    await db_session.rollback()
    reused = await store_workflow_artifact(
        db_session,
        workflow_instance_id=workflow_uuid,
        task_id=task_uuid,
        relative_path=artifact["relative_path"],
        content="完全不同的内容",
    )
    assert str(reused.id) == artifact["id"]
    assert reused.sha256 == artifact["sha256"]
    assert await _artifact_count(db_session, started["id"]) == 1


async def test_the_runtime_exposes_the_compiled_graph(client, app):
    """The runtime compiles the registered workflows with the checkpointer."""

    runtime = app.state.workflow_runtime
    assert runtime is not None
    assert runtime.ready
    graph = runtime.graph("dev_workflow")
    assert graph is not None
    assert runtime.graph("dev_workflow") is graph
