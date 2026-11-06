"""Tests for the development task endpoints and the project relation."""

from __future__ import annotations

import uuid


def _create_project(client, project_payload) -> dict:
    response = client.post("/api/v1/projects", json=project_payload)
    assert response.status_code == 201
    return response.json()


def test_create_task_belongs_to_the_given_project(client, project_payload):
    project = _create_project(client, project_payload)

    response = client.post(
        "/api/v1/tasks",
        json={
            "project_id": project["id"],
            "title": "实现项目列表分页接口",
            "description": "补充参数校验",
            "priority": "high",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_id"] == project["id"]
    assert payload["project_code"] == project["code"]
    assert payload["project_name"] == project["name"]
    assert payload["seq"] == 1
    assert payload["status"] == "pending"
    assert payload["priority"] == "high"


def test_create_task_with_an_unknown_project_returns_404(client):
    response = client.post(
        "/api/v1/tasks",
        json={"project_id": str(uuid.uuid4()), "title": "没有归属的任务"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_create_task_without_a_project_returns_422(client):
    response = client.post("/api/v1/tasks", json={"title": "缺少项目"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_task_sequence_increases_inside_a_project(client, project_payload):
    project = _create_project(client, project_payload)

    first = client.post("/api/v1/tasks", json={"project_id": project["id"], "title": "一"})
    second = client.post("/api/v1/tasks", json={"project_id": project["id"], "title": "二"})

    assert first.json()["seq"] == 1
    assert second.json()["seq"] == 2


def test_task_sequence_is_independent_per_project(client, project_payload):
    first_project = _create_project(client, project_payload)
    second_payload = {**project_payload, "code": f"{project_payload['code']}-B"}
    second_project = _create_project(client, second_payload)

    first = client.post("/api/v1/tasks", json={"project_id": first_project["id"], "title": "一"})
    second = client.post(
        "/api/v1/tasks",
        json={"project_id": second_project["id"], "title": "二"},
    )

    assert first.json()["seq"] == 1
    assert second.json()["seq"] == 1


def test_list_tasks_can_be_filtered_by_project(client, project_payload):
    project = _create_project(client, project_payload)
    client.post("/api/v1/tasks", json={"project_id": project["id"], "title": "属于该项目"})

    response = client.get("/api/v1/tasks", params={"project_id": project["id"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert all(item["project_id"] == project["id"] for item in payload["items"])


def test_list_project_tasks_endpoint_returns_the_tasks_of_one_project(client, project_payload):
    project = _create_project(client, project_payload)
    client.post("/api/v1/tasks", json={"project_id": project["id"], "title": "任务一"})

    response = client.get(f"/api/v1/projects/{project['id']}/tasks")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["project_id"] == project["id"]


def test_list_project_tasks_of_an_unknown_project_returns_404(client):
    response = client.get(f"/api/v1/projects/{uuid.uuid4()}/tasks")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_get_task_by_id_returns_the_task(client, project_payload):
    project = _create_project(client, project_payload)
    created = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "可查询的任务"},
    ).json()

    response = client.get(f"/api/v1/tasks/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["title"] == "可查询的任务"


def test_get_unknown_task_returns_404(client):
    response = client.get(f"/api/v1/tasks/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_update_task_changes_only_the_given_fields(client, project_payload):
    project = _create_project(client, project_payload)
    created = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "原始标题"},
    ).json()

    response = client.put(
        f"/api/v1/tasks/{created['id']}",
        json={"status": "in_progress", "assignee": "developer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "in_progress"
    assert payload["assignee"] == "developer"
    assert payload["title"] == "原始标题"
    assert payload["project_id"] == project["id"]


def test_update_unknown_task_returns_404(client):
    response = client.put(f"/api/v1/tasks/{uuid.uuid4()}", json={"title": "不存在"})

    assert response.status_code == 404


def test_create_task_with_an_invalid_payload_returns_422(client, project_payload):
    project = _create_project(client, project_payload)

    empty_title = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": ""},
    )
    assert empty_title.status_code == 422
    assert empty_title.json()["code"] == "VALIDATION_ERROR"

    long_title = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "x" * 301},
    )
    assert long_title.status_code == 422

    bad_status = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "非法状态", "status": "unknown"},
    )
    assert bad_status.status_code == 422

    bad_priority = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "非法优先级", "priority": "highest"},
    )
    assert bad_priority.status_code == 422


def test_tasks_of_a_deleted_project_disappear_from_the_list(client, project_payload):
    project = _create_project(client, project_payload)
    client.post("/api/v1/tasks", json={"project_id": project["id"], "title": "将被级联软删"})

    client.delete(f"/api/v1/projects/{project['id']}")

    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    assert all(item["project_id"] != project["id"] for item in response.json()["items"])
