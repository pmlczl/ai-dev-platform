"""Tests for the artifact file storage: upload, download and versioning.

The tests drive the HTTP API, because the module is about the interaction of
three layers: the endpoint, the service and the file system. Every upload
lands in a throw away storage directory that is removed after the test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import get_settings

#: A minimal valid markdown document.
MARKDOWN = "# 需求文档\n\n这是自动化测试写入的内容。\n"


@pytest.fixture()
def small_upload_limit(monkeypatch) -> None:
    """Lower the size limit so that the limit can be tested with a small file."""

    monkeypatch.setenv("STORAGE_MAX_UPLOAD_SIZE", "512")
    get_settings.cache_clear()


def _upload(client, task_id: str, *, name: str = "prd.md", content: bytes = None, **data):
    """Upload a file and return the response."""

    payload = content if content is not None else MARKDOWN.encode()
    return client.post(
        f"/api/v1/tasks/{task_id}/artifacts",
        files={"file": (name, payload, "application/octet-stream")},
        data=data,
    )


def _stored_files(root: Path) -> list[Path]:
    """Return every file below the storage root."""

    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def test_upload_returns_the_metadata_of_the_file(client, task_id, storage_root):
    response = _upload(client, task_id, stage="design")

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["review_status"] == "pending"
    assert body["stage"] == "design"
    assert body["relative_path"] == "prd.md"
    assert body["size_bytes"] == len(MARKDOWN.encode())
    assert body["sha256"] == hashlib.sha256(MARKDOWN.encode()).hexdigest()
    assert body["original_filename"] == "prd.md"


def test_upload_writes_the_file_to_the_storage_root(client, task_id, storage_root):
    body = _upload(client, task_id).json()

    stored = storage_root / body["storage_path"]
    assert stored.is_file()
    assert stored.read_bytes() == MARKDOWN.encode()

    # The database only knows the path relative to the storage root.
    assert not body["storage_path"].startswith("/")
    assert str(storage_root) not in body["storage_path"]


def test_upload_rejects_a_file_type_outside_the_whitelist(client, task_id, storage_root):
    response = _upload(client, task_id, name="payload.exe", content=b"MZ\x90\x00")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert _stored_files(storage_root) == []


def test_upload_rejects_content_that_does_not_match_the_extension(client, task_id):
    response = _upload(client, task_id, name="spec.pdf", content=b"MZ\x90\x00 not a pdf")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_upload_rejects_a_file_that_is_too_large(client, task_id, storage_root, small_upload_limit):
    response = _upload(client, task_id, content=b"a" * 2048)

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
    # Nothing is left behind, neither in the storage tree nor in the temp area.
    assert _stored_files(storage_root) == []


def test_upload_rejects_a_file_name_with_a_path(client, task_id, storage_root):
    response = _upload(client, task_id, name="../../etc/passwd.md")

    assert response.status_code == 422
    assert _stored_files(storage_root) == []
    assert not (storage_root.parent / "etc").exists()


def test_upload_rejects_a_relative_path_with_a_traversal(client, task_id, storage_root):
    response = _upload(client, task_id, relative_path="../../secret/prd.md")

    assert response.status_code == 422
    assert _stored_files(storage_root) == []


def test_upload_to_an_unknown_task_returns_not_found(client, storage_root):
    response = _upload(client, "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_download_returns_the_stored_bytes(client, task_id, storage_root):
    body = _upload(client, task_id, name="设计说明.md").json()

    response = client.get(f"/api/v1/artifacts/{body['id']}/download")

    assert response.status_code == 200
    assert response.content == MARKDOWN.encode()
    assert "filename*=utf-8''" in response.headers["content-disposition"].lower()
    assert response.headers["x-content-sha256"] == body["sha256"]


def test_download_of_an_unknown_artifact_returns_not_found(client):
    response = client.get(
        "/api/v1/artifacts/00000000-0000-0000-0000-000000000000/download",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_download_returns_not_found_when_the_file_vanished(client, task_id, storage_root):
    body = _upload(client, task_id).json()
    stored = storage_root / body["storage_path"]
    stored.unlink()

    response = client.get(f"/api/v1/artifacts/{body['id']}/download")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_second_upload_of_the_same_path_creates_a_new_version(client, task_id, storage_root):
    first = _upload(client, task_id, content=b"# first\n").json()
    second = _upload(client, task_id, content=b"# second\n").json()

    assert first["version"] == 1
    assert second["version"] == 2
    assert first["id"] != second["id"]

    # The old revision is superseded, but its content is still on disk.
    old = client.get(f"/api/v1/artifacts/{first['id']}").json()
    assert old["review_status"] == "superseded"

    files = _stored_files(storage_root)
    assert len(files) == 2
    contents = {path.read_bytes() for path in files}
    assert contents == {b"# first\n", b"# second\n"}


def test_creating_a_revision_appends_a_new_version(client, task_id, storage_root):
    first = _upload(client, task_id, content=b"# v1\n").json()

    response = client.post(
        f"/api/v1/artifacts/{first['id']}/revisions",
        files={"file": ("prd.md", b"# v2\n", "application/octet-stream")},
        data={"stage": "testing"},
    )

    assert response.status_code == 201
    second = response.json()
    assert second["version"] == 2
    assert second["stage"] == "testing"
    assert second["relative_path"] == first["relative_path"]

    old = client.get(f"/api/v1/artifacts/{first['id']}").json()
    assert old["review_status"] == "superseded"

    files = _stored_files(storage_root)
    assert len(files) == 2
    assert {path.read_bytes() for path in files} == {b"# v1\n", b"# v2\n"}


def test_the_task_file_list_is_paginated_and_filterable(client, task_id):
    _upload(client, task_id, name="prd.md", stage="design")
    _upload(client, task_id, name="sdd.md", stage="development")

    response = client.get(f"/api/v1/tasks/{task_id}/artifacts")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["pages"] == 1
    assert len(body["items"]) == 2

    filtered = client.get(f"/api/v1/tasks/{task_id}/artifacts", params={"stage": "design"})
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["relative_path"] == "prd.md"

    by_status = client.get(
        f"/api/v1/tasks/{task_id}/artifacts",
        params={"review_status": "superseded"},
    )
    assert by_status.json()["total"] == 0

    by_keyword = client.get(f"/api/v1/tasks/{task_id}/artifacts", params={"keyword": "sdd"})
    assert by_keyword.json()["total"] == 1
    assert by_keyword.json()["items"][0]["relative_path"] == "sdd.md"


def test_review_moves_the_file_into_a_reviewed_state(client, task_id):
    body = _upload(client, task_id).json()

    response = client.post(
        f"/api/v1/artifacts/{body['id']}/review",
        json={"decision": "approved", "reviewed_by": "reviewer", "comment": "内容完整"},
    )

    assert response.status_code == 200
    reviewed = response.json()
    assert reviewed["review_status"] == "approved"
    assert reviewed["reviewed_by"] == "reviewer"
    assert reviewed["reviewed_at"] is not None


def test_review_rejects_a_file_that_was_superseded(client, task_id):
    first = _upload(client, task_id, content=b"# v1\n").json()
    _upload(client, task_id, content=b"# v2\n")

    response = client.post(
        f"/api/v1/artifacts/{first['id']}/review",
        json={"decision": "approved", "reviewed_by": "reviewer"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_a_json_file_is_accepted_and_stored_unchanged(client, task_id, storage_root):
    document = json.dumps({"title": "接口约定"}, ensure_ascii=False).encode()

    response = _upload(client, task_id, name="api.json", content=document)

    assert response.status_code == 201
    stored = storage_root / response.json()["storage_path"]
    assert stored.read_bytes() == document


def test_the_artifact_metadata_endpoint_returns_the_stored_hash(client, task_id):
    body = _upload(client, task_id).json()

    response = client.get(f"/api/v1/artifacts/{body['id']}")

    assert response.status_code == 200
    assert response.json()["sha256"] == hashlib.sha256(MARKDOWN.encode()).hexdigest()
    assert response.json()["created_at"] is not None
