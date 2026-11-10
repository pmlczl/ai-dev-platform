"""Tests for the workflow listing endpoints.

The suite covers the two queries the browser needs to build its pages:

1. ``GET /api/v1/workflows`` - the list of the runs, with the filters the
   approval page applies,
2. ``GET /api/v1/tasks/{task_id}/workflows`` - the runs of one task, including
   the ones that already ended.

The endpoints are pure additions: the existing workflow endpoints keep their
contract, which the workflow suite of ``test_workflow_approval.py`` guards.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.models.enums import WorkflowStatus
from app.models.workflow import WorkflowInstance

APPROVER = "alice"


def _create_project(client, payload) -> dict:
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_task(client, project_id: str, title: str = "列表测试任务") -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start(client, task_id: str) -> dict:
    response = client.post(f"/api/v1/tasks/{task_id}/workflow/start", json={})
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, workflow: dict) -> dict:
    response = client.post(
        f"/api/v1/workflows/{workflow['id']}/resume",
        json={
            "thread_id": workflow["thread_id"],
            "decision": "approved",
            "approver": APPROVER,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _list(client, **params) -> dict:
    response = client.get("/api/v1/workflows", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _insert_history(
    db_session,
    project_id: str,
    task_id: str,
    status: str = WorkflowStatus.COMPLETED.value,
) -> str:
    """Write an instance directly into the database.

    A task can only run one workflow at a time through the API, so a second
    run of the same task is written into the database - it is the history a
    real system produces over time.
    """

    instance_id = uuid4()
    instance = WorkflowInstance(
        id=instance_id,
        thread_id=f"wf-{instance_id}",
        project_id=UUID(project_id),
        task_id=UUID(task_id),
        workflow_key="dev_workflow",
        status=status,
        iteration=1,
    )
    db_session.add(instance)
    await db_session.commit()
    return str(instance_id)


def test_the_workflow_list_returns_the_runs(client, project_payload):
    """The list contains the run and never the internals of the graph."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    body = _list(client, project_id=project["id"])

    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]

    assert item["id"] == started["id"]
    assert item["project_id"] == project["id"]
    assert item["task_id"] == task["id"]
    assert item["status"] == WorkflowStatus.WAITING_APPROVAL.value
    assert item["thread_id"] == started["thread_id"]
    assert item["current_artifact"]["id"] == started["current_artifact"]["id"]
    assert item["pending_approval"]["iteration"] == 1

    # The state of the graph is not part of the view.
    assert "state" not in item
    assert "checkpoint_id" not in item


def test_the_workflow_list_is_ordered_newest_first(client, project_payload):
    """The rows are ordered by their creation time, newest first."""

    project = _create_project(client, project_payload)
    first_task = _create_task(client, project["id"], "排序任务 A")
    second_task = _create_task(client, project["id"], "排序任务 B")

    _start(client, first_task["id"])
    second = _start(client, second_task["id"])

    body = _list(client, project_id=project["id"])

    timestamps = [item["created_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)
    # The run that was started last is the first one - as long as the two
    # runs were not written in the very same second.
    if timestamps[0] != timestamps[-1]:
        assert body["items"][0]["id"] == second["id"]


def test_the_workflow_list_is_paginated(client, project_payload):
    """The list is cut into pages and the pages do not overlap."""

    project = _create_project(client, project_payload)
    started: list[str] = []
    for index in range(3):
        task = _create_task(client, project["id"], f"分页任务 {index}")
        started.append(_start(client, task["id"])["id"])

    first = _list(client, project_id=project["id"], page=1, page_size=2)
    second = _list(client, project_id=project["id"], page=2, page_size=2)

    assert first["total"] == 3
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert first["pages"] == 2
    assert len(first["items"]) == 2

    assert second["total"] == 3
    assert second["page"] == 2
    assert len(second["items"]) == 1

    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert set(first_ids).isdisjoint(second_ids)
    assert set(first_ids) | set(second_ids) == set(started)


def test_the_workflow_list_can_be_filtered_by_status(client, project_payload):
    """Only the runs in the requested state are returned."""

    project = _create_project(client, project_payload)
    waiting_task = _create_task(client, project["id"], "等待审批任务")
    done_task = _create_task(client, project["id"], "已完成任务")

    waiting = _start(client, waiting_task["id"])
    done = _start(client, done_task["id"])
    _approve(client, done)

    waiting_body = _list(
        client,
        project_id=project["id"],
        status=WorkflowStatus.WAITING_APPROVAL.value,
    )
    assert [item["id"] for item in waiting_body["items"]] == [waiting["id"]]

    done_body = _list(
        client,
        project_id=project["id"],
        status=WorkflowStatus.COMPLETED.value,
    )
    assert [item["id"] for item in done_body["items"]] == [done["id"]]


def test_the_workflow_list_can_be_filtered_by_project(client, project_payload):
    """A project filter only returns the runs of that project."""

    first = _create_project(client, project_payload)
    second_payload = dict(project_payload)
    second_payload["code"] = f"{project_payload['code']}-B"
    second = _create_project(client, second_payload)

    first_task = _create_task(client, first["id"], "项目 A 任务")
    second_task = _create_task(client, second["id"], "项目 B 任务")
    first_run = _start(client, first_task["id"])
    _start(client, second_task["id"])

    body = _list(client, project_id=first["id"])

    assert body["total"] == 1
    assert body["items"][0]["id"] == first_run["id"]
    assert body["items"][0]["project_id"] == first["id"]


def test_the_workflow_list_can_be_filtered_by_task(client, project_payload):
    """A task filter only returns the runs of that task."""

    project = _create_project(client, project_payload)
    first_task = _create_task(client, project["id"], "任务过滤 A")
    second_task = _create_task(client, project["id"], "任务过滤 B")
    first_run = _start(client, first_task["id"])
    _start(client, second_task["id"])

    body = _list(client, task_id=first_task["id"])

    assert body["total"] == 1
    assert body["items"][0]["id"] == first_run["id"]
    assert body["items"][0]["task_id"] == first_task["id"]


def test_the_workflow_list_combines_the_filters(client, project_payload):
    """The filters can be combined - every one of them narrows the result."""

    project = _create_project(client, project_payload)
    other_payload = dict(project_payload)
    other_payload["code"] = f"{project_payload['code']}-C"
    other = _create_project(client, other_payload)

    task = _create_task(client, project["id"], "组合过滤任务")
    other_task = _create_task(client, other["id"], "组合过滤任务 B")
    run = _start(client, task["id"])
    _start(client, other_task["id"])

    body = _list(
        client,
        status=WorkflowStatus.WAITING_APPROVAL.value,
        project_id=project["id"],
        task_id=task["id"],
    )

    assert body["total"] == 1
    assert body["items"][0]["id"] == run["id"]

    # A filter that does not match the row empties the result.
    empty = _list(
        client,
        status=WorkflowStatus.COMPLETED.value,
        project_id=project["id"],
        task_id=task["id"],
    )
    assert empty["total"] == 0
    assert empty["items"] == []


def test_the_workflow_list_rejects_an_unknown_status(client):
    """An unknown state is rejected by the schema."""

    response = client.get("/api/v1/workflows", params={"status": "does_not_exist"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_the_runs_of_a_task_are_listed(client, db_session, project_payload):
    """The runs of a task are found again, including the old ones."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    started = _start(client, task["id"])

    history_id = await _insert_history(
        db_session,
        project_id=project["id"],
        task_id=task["id"],
    )

    response = client.get(f"/api/v1/tasks/{task['id']}/workflows")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] == 2
    ids = [item["id"] for item in body["items"]]
    assert started["id"] in ids
    assert history_id in ids


def test_the_runs_of_a_task_are_paginated(client, project_payload):
    """The reverse lookup is paginated as well."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    _start(client, task["id"])

    response = client.get(
        f"/api/v1/tasks/{task['id']}/workflows",
        params={"page": 1, "page_size": 1},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] == 1
    assert body["pages"] == 1
    assert len(body["items"]) == 1


def test_an_unknown_task_has_no_runs(client):
    """A task that does not exist is reported as not found."""

    response = client.get(
        "/api/v1/tasks/00000000-0000-0000-0000-000000000000/workflows",
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_deleted_task_has_no_runs(client, project_payload):
    """A task that was deleted follows the existing convention: 404."""

    project = _create_project(client, project_payload)
    task = _create_task(client, project["id"])
    _start(client, task["id"])

    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204, deleted.text

    # The task is gone ...
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404

    # ... and its runs cannot be looked up any more either.
    response = client.get(f"/api/v1/tasks/{task['id']}/workflows")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"

    # The run itself is still there - the history survives the soft delete.
    runs = _list(client, project_id=project["id"])
    assert runs["total"] == 1
