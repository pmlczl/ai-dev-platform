"""Manual smoke test of the workflow endpoints.

Run with::

    python -m scripts.smoke_workflow

The script creates a project and a task, starts a workflow, rejects the
artifact, approves the rework and prints the event log. It is meant to be
run against a local database, not as part of the test suite.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def show(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    app = create_app()
    with TestClient(app) as client:
        code = uuid.uuid4().hex[:12]
        project = client.post(
            "/api/v1/projects",
            json={"code": f"PRJ-{code}", "name": "冒烟项目", "owner": "smoke"},
        )
        print("project:", project.status_code)
        project_id = project.json()["id"]

        task = client.post(
            "/api/v1/tasks",
            json={"project_id": project_id, "title": "冒烟任务"},
        )
        print("task:", task.status_code)
        task_id = task.json()["id"]

        started = client.post(f"/api/v1/tasks/{task_id}/workflow/start", json={})
        show("start", started.json())
        if started.status_code != 201:
            return 1
        workflow = started.json()
        workflow_id = workflow["id"]
        thread_id = workflow["thread_id"]

        logs = client.get(f"/api/v1/workflows/{workflow_id}/logs")
        show("logs after start", logs.json())

        rejected = client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json={
                "thread_id": thread_id,
                "decision": "rejected",
                "approver": "alice",
                "comment": "请补充异常处理",
            },
        )
        show("resume rejected", rejected.json())

        approved = client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json={
                "thread_id": thread_id,
                "decision": "approved",
                "approver": "alice",
            },
        )
        show("resume approved", approved.json())

        logs = client.get(f"/api/v1/workflows/{workflow_id}/logs")
        show("logs at the end", logs.json())

        task_view = client.get(f"/api/v1/tasks/{task_id}")
        show("task", task_view.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
