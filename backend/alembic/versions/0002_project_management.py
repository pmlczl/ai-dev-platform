"""Add the project management tables.

Revision ID: 0002_project_management
Revises: 0001_baseline
Create Date: 2026-11-06

The script was generated with ``alembic revision --autogenerate`` and reviewed
by hand afterwards. Two things were adjusted compared to the raw output:

* the ``Text()`` reference inside the JSONB variant was qualified with
  ``sa.`` - the generated code would have raised a ``NameError`` at runtime;
* the statements were reformatted to the repository style (double quotes,
  100 column limit).

The table order respects the foreign keys: ``projects`` first, then the tables
that reference it, and ``artifacts`` last because it references both
``development_tasks`` and ``workflow_instances``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_project_management"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the project management tables."""

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("task_sequence", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('planning', 'active', 'paused', 'completed', 'archived', 'cancelled')",
            name=op.f("ck_projects_status_valid"),
        ),
        sa.CheckConstraint(
            "task_sequence >= 0",
            name=op.f("ck_projects_task_sequence_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("code", name=op.f("uq_projects_code")),
    )
    op.create_index("ix_projects_created_at", "projects", ["created_at"], unique=False)
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"], unique=False)
    op.create_index("ix_projects_status", "projects", ["status"], unique=False)

    op.create_table(
        "development_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("assignee", sa.String(length=120), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'blocked', 'in_review', "
            "'completed', 'cancelled')",
            name=op.f("ck_development_tasks_status_valid"),
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name=op.f("ck_development_tasks_priority_valid"),
        ),
        sa.CheckConstraint("seq >= 1", name=op.f("ck_development_tasks_seq_valid")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_development_tasks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_development_tasks")),
        sa.UniqueConstraint(
            "project_id",
            "seq",
            name="uq_development_tasks_project_seq",
        ),
    )
    op.create_index(
        "ix_development_tasks_project_id",
        "development_tasks",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_development_tasks_project_id_status",
        "development_tasks",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_development_tasks_status",
        "development_tasks",
        ["status"],
        unique=False,
    )

    op.create_table(
        "workflow_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column(
            "state",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()),
                "postgresql",
            ),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'waiting_approval', "
            "'completed', 'failed', 'cancelled')",
            name=op.f("ck_workflow_instances_status_valid"),
        ),        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_workflow_instances_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["development_tasks.id"],
            name=op.f("fk_workflow_instances_task_id_development_tasks"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_instances")),
    )
    op.create_index(
        "ix_workflow_instances_project_id",
        "workflow_instances",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_instances_project_id_status",
        "workflow_instances",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_instances_status",
        "workflow_instances",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_instances_task_id",
        "workflow_instances",
        ["task_id"],
        unique=False,
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_instance_id", sa.Uuid(), nullable=True),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected', 'superseded')",
            name=op.f("ck_artifacts_review_status_valid"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_artifacts_version_valid")),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name=op.f("ck_artifacts_size_bytes_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_artifacts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["development_tasks.id"],
            name=op.f("fk_artifacts_task_id_development_tasks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_instance_id"],
            ["workflow_instances.id"],
            name=op.f("fk_artifacts_workflow_instance_id_workflow_instances"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
        sa.UniqueConstraint(
            "project_id",
            "relative_path",
            "version",
            name="uq_artifacts_project_path_version",
        ),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"], unique=False)
    op.create_index(
        "ix_artifacts_review_status",
        "artifacts",
        ["review_status"],
        unique=False,
    )
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"], unique=False)
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"], unique=False)
    op.create_index(
        "ix_artifacts_workflow_instance_id",
        "artifacts",
        ["workflow_instance_id"],
        unique=False,
    )

    # The approval trail is append only: no "updated_at" column, and the
    # reference to the approved object is polymorphic (target_type/target_id).
    op.create_table(
        "approval_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("approver", sa.String(length=120), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_type IN ('task', 'artifact', 'workflow_instance')",
            name=op.f("ck_approval_records_target_type_valid"),
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'changes_requested')",
            name=op.f("ck_approval_records_decision_valid"),
        ),
        sa.CheckConstraint(
            "sequence >= 1",
            name=op.f("ck_approval_records_sequence_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_approval_records_project_id_projects"),
            # RESTRICT: an audit trail must not vanish with the project.
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_records")),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            "sequence",
            name="uq_approval_records_target_sequence",
        ),
    )
    op.create_index(
        "ix_approval_records_created_at",
        "approval_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_approval_records_project_id",
        "approval_records",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_approval_records_target_type_target_id",
        "approval_records",
        ["target_type", "target_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the project management tables in reverse dependency order."""

    op.drop_index(
        "ix_approval_records_target_type_target_id",
        table_name="approval_records",
    )
    op.drop_index("ix_approval_records_project_id", table_name="approval_records")
    op.drop_index("ix_approval_records_created_at", table_name="approval_records")
    op.drop_table("approval_records")

    op.drop_index(
        "ix_artifacts_workflow_instance_id",
        table_name="artifacts",
    )
    op.drop_index("ix_artifacts_task_id", table_name="artifacts")
    op.drop_index("ix_artifacts_sha256", table_name="artifacts")
    op.drop_index("ix_artifacts_review_status", table_name="artifacts")
    op.drop_index("ix_artifacts_project_id", table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index("ix_workflow_instances_task_id", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_status", table_name="workflow_instances")
    op.drop_index(
        "ix_workflow_instances_project_id_status",
        table_name="workflow_instances",
    )
    op.drop_index("ix_workflow_instances_project_id", table_name="workflow_instances")
    op.drop_table("workflow_instances")

    op.drop_index("ix_development_tasks_status", table_name="development_tasks")
    op.drop_index(
        "ix_development_tasks_project_id_status",
        table_name="development_tasks",
    )
    op.drop_index("ix_development_tasks_project_id", table_name="development_tasks")
    op.drop_table("development_tasks")

    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_index("ix_projects_created_at", table_name="projects")
    op.drop_table("projects")
