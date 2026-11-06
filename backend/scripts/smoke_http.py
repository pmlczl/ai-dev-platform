"""Live HTTP smoke test against a running uvicorn instance.

Run with the server started on the target port:

    DATABASE_URL=sqlite+aiosqlite:///... python scripts/smoke_http.py http://127.0.0.1:8123/api/v1
"""

from __future__ import annotations

import hashlib
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123/api/v1"

#: Unique per run so the script can be executed repeatedly against the same database.
PROJECT_CODE = f"SMOKE-{uuid.uuid4().hex[:8]}"

failures: list[str] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "OK  " if condition else "FAIL"
    suffix = f" :: {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    if not condition:
        failures.append(label)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=10.0) as client:
        health = client.get("/health")
        check("GET /health -> 200", health.status_code == 200, str(health.status_code))
        check(
            "health carries X-Request-ID",
            "x-request-id" in {k.lower() for k in health.headers},
        )

        created = client.post(
            "/projects",
            json={
                "code": PROJECT_CODE,
                "name": "smoke project",
                "description": "live smoke",
                "owner": "qoder",
            },
        )
        check("POST /projects -> 201", created.status_code == 201, created.text[:200])
        project = created.json()
        project_id = project["id"]
        check("project id is a uuid", len(project_id) == 36, project_id)
        check("project status defaults to planning", project["status"] == "planning")

        duplicate = client.post("/projects", json={"code": PROJECT_CODE, "name": "dup"})
        check(
            "POST /projects duplicate code -> 409",
            duplicate.status_code == 409,
            duplicate.text[:200],
        )
        check(
            "duplicate error envelope",
            duplicate.json().get("code") == "CONFLICT",
            duplicate.text[:200],
        )

        invalid = client.post("/projects", json={"code": "", "name": "x"})
        check(
            "POST /projects invalid payload -> 422",
            invalid.status_code == 422,
            invalid.text[:200],
        )

        listing = client.get("/projects", params={"page": 1, "page_size": 5})
        body = listing.json()
        check("GET /projects -> 200", listing.status_code == 200)
        check(
            "page envelope shape",
            set(body) == {"items", "total", "page", "page_size", "pages"},
            str(sorted(body)),
        )
        check("list contains the project", any(i["id"] == project_id for i in body["items"]))
        check(
            "list items expose task_count",
            all("task_count" in i for i in body["items"]),
            body["items"][0].keys() if body["items"] else "no items",
        )

        detail = client.get(f"/projects/{project_id}")
        check("GET /projects/{id} -> 200", detail.status_code == 200, detail.text[:200])
        check(
            "detail returns the project fields",
            {"id", "code", "name", "status", "created_at", "updated_at"} <= set(detail.json()),
            str(sorted(detail.json())),
        )

        missing = client.get("/projects/00000000-0000-4000-8000-000000000000")
        check("GET unknown project -> 404", missing.status_code == 404, missing.text[:200])
        check("404 envelope has request_id", "request_id" in missing.json(), missing.text[:200])

        updated = client.put(
            f"/projects/{project_id}",
            json={"status": "active", "name": "renamed"},
        )
        check("PUT /projects/{id} -> 200", updated.status_code == 200, updated.text[:200])
        check("update applied", updated.json()["status"] == "active")
        check(
            "partial update keeps untouched fields",
            updated.json()["owner"] == "qoder",
            updated.text[:200],
        )

        task = client.post(
            "/tasks",
            json={
                "project_id": project_id,
                "title": "first task",
                "priority": "high",
            },
        )
        check("POST /tasks -> 201", task.status_code == 201, task.text[:200])
        task_id = task.json()["id"]
        check(
            "task carries project info",
            task.json()["project_code"] == PROJECT_CODE,
            task.text[:200],
        )

        orphan = client.post(
            "/tasks",
            json={
                "project_id": "00000000-0000-4000-8000-000000000000",
                "title": "orphan",
            },
        )
        check("POST /tasks unknown project -> 404", orphan.status_code == 404, orphan.text[:200])

        bad_status = client.put(f"/tasks/{task_id}", json={"status": "not-a-status"})
        check(
            "PUT /tasks invalid status -> 422",
            bad_status.status_code == 422,
            bad_status.text[:200],
        )

        tasks = client.get("/tasks", params={"project_id": project_id})
        check("GET /tasks?project_id -> 200", tasks.status_code == 200)
        check(
            "task list filtered by project",
            all(i["project_id"] == project_id for i in tasks.json()["items"]),
        )

        scoped = client.get(f"/projects/{project_id}/tasks")
        check("GET /projects/{id}/tasks -> 200", scoped.status_code == 200, scoped.text[:200])
        check("scoped task list not empty", len(scoped.json()["items"]) >= 1)

        # --- artifacts -----------------------------------------------------
        document = "# smoke\n\nfile management smoke test\n"
        uploaded = client.post(
            f"/tasks/{task_id}/artifacts",
            files={"file": ("prd.md", document.encode(), "application/octet-stream")},
            data={"stage": "design", "relative_path": "docs/prd.md"},
        )
        check("POST /tasks/{id}/artifacts -> 201", uploaded.status_code == 201, uploaded.text[:200])
        artifact = uploaded.json()
        artifact_id = artifact["id"]
        check(
            "upload returns the sha256 of the file",
            artifact["sha256"] == hashlib.sha256(document.encode()).hexdigest(),
            artifact["sha256"],
        )
        check("upload starts at version 1", artifact["version"] == 1)
        check("upload starts as pending", artifact["review_status"] == "pending")
        check("upload records the stage", artifact["stage"] == "design")
        check(
            "the storage path stays relative",
            not artifact["storage_path"].startswith("/"),
            artifact["storage_path"],
        )

        metadata = client.get(f"/artifacts/{artifact_id}")
        check("GET /artifacts/{id} -> 200", metadata.status_code == 200, metadata.text[:200])
        check(
            "metadata carries hash, version and stage",
            {"sha256", "version", "stage", "review_status", "created_at"} <= set(metadata.json()),
            str(sorted(metadata.json())),
        )

        download = client.get(f"/artifacts/{artifact_id}/download")
        check(
            "GET /artifacts/{id}/download -> 200",
            download.status_code == 200,
            download.text[:200],
        )
        check("download returns the original bytes", download.content == document.encode())
        check(
            "download sets a content disposition",
            "content-disposition" in {k.lower() for k in download.headers},
        )

        second = client.post(
            f"/tasks/{task_id}/artifacts",
            files={"file": ("prd.md", b"# v2\n", "application/octet-stream")},
            data={"relative_path": "docs/prd.md"},
        )
        check("second upload -> 201", second.status_code == 201, second.text[:200])
        check("second upload is version 2", second.json()["version"] == 2)

        superseded = client.get(f"/artifacts/{artifact_id}")
        check(
            "the previous revision is superseded",
            superseded.json()["review_status"] == "superseded",
            superseded.text[:200],
        )

        revision = client.post(
            f"/artifacts/{second.json()['id']}/revisions",
            files={"file": ("prd.md", b"# v3\n", "application/octet-stream")},
        )
        check(
            "POST /artifacts/{id}/revisions -> 201",
            revision.status_code == 201,
            revision.text[:200],
        )
        check("the revision is version 3", revision.json()["version"] == 3)

        listing = client.get(f"/tasks/{task_id}/artifacts")
        check("GET /tasks/{id}/artifacts -> 200", listing.status_code == 200, listing.text[:200])
        check(
            "the artifact list is paginated",
            set(listing.json()) == {"items", "total", "page", "page_size", "pages"},
            str(sorted(listing.json())),
        )
        check("the list contains the uploaded files", listing.json()["total"] >= 2)

        reviewed = client.post(
            f"/artifacts/{revision.json()['id']}/review",
            json={"decision": "approved", "reviewed_by": "smoke"},
        )
        check(
            "POST /artifacts/{id}/review -> 200",
            reviewed.status_code == 200,
            reviewed.text[:200],
        )
        check("the file is approved", reviewed.json()["review_status"] == "approved")
        check("the reviewer is recorded", reviewed.json()["reviewed_by"] == "smoke")

        forbidden = client.post(
            f"/tasks/{task_id}/artifacts",
            files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        check(
            "POST an unknown file type -> 422",
            forbidden.status_code == 422,
            forbidden.text[:200],
        )

        missing_artifact = client.get(
            "/artifacts/00000000-0000-4000-8000-000000000000/download",
        )
        check(
            "GET an unknown artifact -> 404",
            missing_artifact.status_code == 404,
            missing_artifact.text[:200],
        )

        deleted = client.delete(f"/projects/{project_id}")
        check("DELETE /projects/{id} -> 204", deleted.status_code == 204, deleted.text[:200])

        after = client.get(f"/projects/{project_id}")
        check("deleted project -> 404", after.status_code == 404, after.text[:200])

        after_tasks = client.get("/tasks", params={"project_id": project_id})
        check(
            "tasks of deleted project are hidden",
            after_tasks.json()["total"] == 0,
            after_tasks.text[:200],
        )

    print()
    if failures:
        print(f"SMOKE FAILED: {len(failures)} check(s) failed: {failures}")
        return 1
    print("SMOKE PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
