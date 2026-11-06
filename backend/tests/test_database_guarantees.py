"""Tests for the database guarantees that the service layer must not rely on.

The application enforces most relations in Python (a task is rejected when its
project does not exist, deleting a project soft-deletes its tasks). These tests
cover the guarantees that live in the schema itself, so a regression in the
schema or in the test harness cannot pass unnoticed:

* foreign keys are actually enforced by the database engine,
* an orphan row cannot be written,
* ``ON DELETE CASCADE`` removes the dependent rows.

The SQLite test database only enforces foreign keys when
``PRAGMA foreign_keys`` is switched on, which the shared fixture in
``conftest.py`` does for every connection.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import engine


async def _foreign_keys_enabled() -> bool:
    async with engine.connect() as connection:
        return bool((await connection.execute(text("PRAGMA foreign_keys"))).scalar())


async def test_sqlite_enforces_foreign_keys(db_session):
    assert await _foreign_keys_enabled() is True


async def test_orphan_task_row_is_rejected(db_session):
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO development_tasks "
                "(id, project_id, seq, title, status, priority, created_at, updated_at) "
                "VALUES (:id, :project_id, 1, '孤儿任务', 'pending', 'low', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid.uuid4()), "project_id": str(uuid.uuid4())},
        )
        await db_session.commit()


async def test_deleting_a_project_row_cascades_to_its_tasks(db_session, project_payload):
    project_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            "INSERT INTO projects (id, code, name, status, task_sequence, created_at, updated_at) "
            "VALUES (:id, :code, '级联测试', 'planning', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": project_id, "code": project_payload["code"]},
    )
    await db_session.execute(
        text(
            "INSERT INTO development_tasks "
            "(id, project_id, seq, title, status, priority, created_at, updated_at) "
            "VALUES (:id, :project_id, 1, '将被级联删除', 'pending', 'low', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": task_id, "project_id": project_id},
    )
    await db_session.commit()

    await db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    await db_session.commit()

    remaining = await db_session.execute(
        text("SELECT COUNT(*) FROM development_tasks WHERE id = :id"),
        {"id": task_id},
    )
    assert remaining.scalar() == 0
