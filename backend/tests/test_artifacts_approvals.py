"""Tests for the artifact metadata and the append only approval trail.

Both features are service level only in this iteration - they have no HTTP
endpoints yet - so the tests drive the services directly against the migrated
database.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.core.exceptions import NotFoundException, ValidationException
from app.models.approval import ApprovalRecord
from app.models.enums import ApprovalDecision, ApprovalTargetType, ArtifactReviewStatus
from app.schemas.approval import ApprovalAppend
from app.schemas.artifact import ArtifactRegister
from app.services.approvals import append_approval, list_approvals
from app.services.artifacts import list_artifacts, register_artifact

SHA256_A = "a" * 64
SHA256_B = "b" * 64


def _create_project(client, payload) -> dict:
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    return response.json()


async def test_register_artifact_appends_a_new_version(db_session, client, project_payload):
    project = _create_project(client, project_payload)

    first = await register_artifact(
        db_session,
        ArtifactRegister(
            project_id=UUID(project["id"]),
            relative_path="docs/prd.md",
            sha256=SHA256_A,
            file_type="text/markdown",
            size_bytes=2048,
        ),
    )
    second = await register_artifact(
        db_session,
        ArtifactRegister(
            project_id=UUID(project["id"]),
            relative_path="docs/prd.md",
            sha256=SHA256_B,
            file_type="text/markdown",
            size_bytes=4096,
        ),
    )

    assert first.version == 1
    assert second.version == 2
    assert second.sha256 == SHA256_B
    assert second.review_status == ArtifactReviewStatus.PENDING.value
    assert second.relative_path == "docs/prd.md"

    artifacts = await list_artifacts(db_session, UUID(project["id"]))
    assert len(artifacts) == 2
    # The previous revision is superseded instead of being overwritten.
    superseded = [a for a in artifacts if a.version == 1][0]
    assert superseded.review_status == ArtifactReviewStatus.SUPERSEDED.value


async def test_register_artifact_rejects_a_task_of_another_project(
    db_session,
    client,
    project_payload,
):
    first_project = _create_project(client, project_payload)
    second_payload = {**project_payload, "code": f"{project_payload['code']}-B"}
    second_project = _create_project(client, second_payload)
    task = client.post(
        "/api/v1/tasks",
        json={"project_id": first_project["id"], "title": "属于另一个项目的任务"},
    ).json()

    with pytest.raises(ValidationException):
        await register_artifact(
            db_session,
            ArtifactRegister(
                project_id=UUID(second_project["id"]),
                task_id=UUID(task["id"]),
                relative_path="docs/sdd.md",
                sha256=SHA256_A,
                file_type="text/markdown",
            ),
        )


async def test_append_approval_increases_the_sequence(db_session, client, project_payload):
    project = _create_project(client, project_payload)
    task = client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "待审批的任务"},
    ).json()

    first = await append_approval(
        db_session,
        ApprovalAppend(
            project_id=UUID(project["id"]),
            target_type=ApprovalTargetType.TASK,
            target_id=UUID(task["id"]),
            decision=ApprovalDecision.CHANGES_REQUESTED,
            approver="reviewer-a",
            comment="补充异常处理",
        ),
    )
    second = await append_approval(
        db_session,
        ApprovalAppend(
            project_id=UUID(project["id"]),
            target_type=ApprovalTargetType.TASK,
            target_id=UUID(task["id"]),
            decision=ApprovalDecision.APPROVED,
            approver="reviewer-b",
        ),
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.decision == ApprovalDecision.CHANGES_REQUESTED.value
    assert second.decision == ApprovalDecision.APPROVED.value
    assert first.approver == "reviewer-a"

    trail = await list_approvals(
        db_session,
        UUID(project["id"]),
        target_type=ApprovalTargetType.TASK,
        target_id=UUID(task["id"]),
    )
    assert [record.sequence for record in trail] == [1, 2]
    assert [record.decision for record in trail] == ["changes_requested", "approved"]


async def test_append_approval_for_an_unknown_target_raises_not_found(
    db_session,
    client,
    project_payload,
):
    project = _create_project(client, project_payload)

    with pytest.raises(NotFoundException):
        await append_approval(
            db_session,
            ApprovalAppend(
                project_id=UUID(project["id"]),
                target_type=ApprovalTargetType.TASK,
                target_id=UUID("00000000-0000-0000-0000-000000000000"),
                decision=ApprovalDecision.APPROVED,
                approver="reviewer",
            ),
        )


async def test_append_approval_rejects_a_target_of_another_project(
    db_session,
    client,
    project_payload,
):
    first_project = _create_project(client, project_payload)
    second_payload = {**project_payload, "code": f"{project_payload['code']}-B"}
    second_project = _create_project(client, second_payload)
    task = client.post(
        "/api/v1/tasks",
        json={"project_id": first_project["id"], "title": "另一个项目的任务"},
    ).json()

    with pytest.raises(ValidationException):
        await append_approval(
            db_session,
            ApprovalAppend(
                project_id=UUID(second_project["id"]),
                target_type=ApprovalTargetType.TASK,
                target_id=UUID(task["id"]),
                decision=ApprovalDecision.APPROVED,
                approver="reviewer",
            ),
        )


def test_approval_records_have_no_update_timestamp():
    """The table is append only: there is no column that could be rewritten."""

    assert "updated_at" not in ApprovalRecord.__table__.columns
    assert "created_at" in ApprovalRecord.__table__.columns
