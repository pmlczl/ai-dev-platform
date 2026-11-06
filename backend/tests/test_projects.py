"""Tests for the project management endpoints."""

from __future__ import annotations

import uuid


def test_create_project_returns_201_with_the_persisted_fields(client, project_payload):
    response = client.post("/api/v1/projects", json=project_payload)

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"]
    assert payload["code"] == project_payload["code"]
    assert payload["name"] == project_payload["name"]
    assert payload["description"] == project_payload["description"]
    assert payload["owner"] == project_payload["owner"]
    assert payload["status"] == "planning"
    assert payload["created_at"]
    assert payload["updated_at"]


def test_create_project_with_a_duplicated_code_returns_409(client, project_payload):
    first = client.post("/api/v1/projects", json=project_payload)
    assert first.status_code == 201

    second = client.post("/api/v1/projects", json=project_payload)

    assert second.status_code == 409
    assert second.json()["code"] == "CONFLICT"


def test_get_project_by_id_returns_the_project(client, project_payload):
    created = client.post("/api/v1/projects", json=project_payload).json()

    response = client.get(f"/api/v1/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["code"] == project_payload["code"]


def test_get_unknown_project_returns_404_with_the_error_envelope(client):
    response = client.get(f"/api/v1/projects/{uuid.uuid4()}")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "NOT_FOUND"
    assert payload["request_id"]


def test_list_projects_is_paginated(client, project_payload):
    client.post("/api/v1/projects", json=project_payload)

    response = client.get("/api/v1/projects", params={"page": 1, "page_size": 5})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"items", "total", "page", "page_size", "pages"}
    assert payload["page"] == 1
    assert payload["page_size"] == 5
    assert payload["total"] >= 1
    assert payload["pages"] >= 1
    assert len(payload["items"]) <= 5


def test_list_projects_filters_by_keyword(client, project_payload):
    client.post("/api/v1/projects", json=project_payload)

    response = client.get("/api/v1/projects", params={"keyword": project_payload["code"]})

    assert response.status_code == 200
    codes = [item["code"] for item in response.json()["items"]]
    assert project_payload["code"] in codes

    empty = client.get("/api/v1/projects", params={"keyword": "no-such-project-code"})
    assert empty.json()["total"] == 0


def test_list_projects_filters_by_status(client, project_payload):
    client.post("/api/v1/projects", json=project_payload)

    response = client.get("/api/v1/projects", params={"status": "active"})

    assert response.status_code == 200
    assert all(item["status"] == "active" for item in response.json()["items"])


def test_list_projects_rejects_an_out_of_range_page_size(client):
    response = client.get("/api/v1/projects", params={"page_size": 5000})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_update_project_changes_only_the_given_fields(client, project_payload):
    created = client.post("/api/v1/projects", json=project_payload).json()

    response = client.put(
        f"/api/v1/projects/{created['id']}",
        json={"name": "改名后的项目", "status": "active"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "改名后的项目"
    assert payload["status"] == "active"
    # Untouched fields keep their value.
    assert payload["code"] == project_payload["code"]
    assert payload["description"] == project_payload["description"]


def test_update_unknown_project_returns_404(client):
    response = client.put(f"/api/v1/projects/{uuid.uuid4()}", json={"name": "不存在"})

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_delete_project_hides_it_and_its_tasks(client, project_payload):
    created = client.post("/api/v1/projects", json=project_payload).json()
    task = client.post(
        "/api/v1/tasks",
        json={"project_id": created["id"], "title": "待删除项目下的任务"},
    )
    assert task.status_code == 201

    response = client.delete(f"/api/v1/projects/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""

    assert client.get(f"/api/v1/projects/{created['id']}").status_code == 404
    assert client.get(f"/api/v1/tasks/{task.json()['id']}").status_code == 404
    listed = client.get("/api/v1/tasks", params={"project_id": created["id"]})
    assert listed.json()["total"] == 0


def test_create_project_with_an_invalid_payload_returns_422(client, unique_code):
    empty_code = client.post("/api/v1/projects", json={"code": "", "name": "缺少编号"})
    assert empty_code.status_code == 422
    assert empty_code.json()["code"] == "VALIDATION_ERROR"

    long_name = client.post(
        "/api/v1/projects",
        json={"code": unique_code, "name": "x" * 201},
    )
    assert long_name.status_code == 422

    bad_status = client.post(
        "/api/v1/projects",
        json={"code": unique_code, "name": "非法状态", "status": "not-a-status"},
    )
    assert bad_status.status_code == 422

    bad_pattern = client.post(
        "/api/v1/projects",
        json={"code": "非法 编号", "name": "非法编号"},
    )
    assert bad_pattern.status_code == 422


def test_project_list_item_reports_the_task_count(client, project_payload):
    created = client.post("/api/v1/projects", json=project_payload).json()
    client.post("/api/v1/tasks", json={"project_id": created["id"], "title": "任务一"})
    client.post("/api/v1/tasks", json={"project_id": created["id"], "title": "任务二"})

    response = client.get("/api/v1/projects", params={"keyword": project_payload["code"]})

    assert response.status_code == 200
    item = next(i for i in response.json()["items"] if i["id"] == created["id"])
    assert item["task_count"] == 2
