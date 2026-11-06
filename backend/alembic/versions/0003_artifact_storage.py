"""add the storage fields to the artifact table

Revision ID: 0003_artifact_storage
Revises: 0002_project_management
Create Date: 2026-11-06

The script was generated with ``python -m alembic revision --autogenerate``
and then adjusted by hand:

* ``stage`` is added with a server default, because a column cannot become
  ``NOT NULL`` on a table that already holds rows without one,
* the check constraint on ``stage`` and the unique constraint on
  ``storage_path`` cannot be added with a plain ``ALTER TABLE`` on SQLite, so
  the whole change runs inside a batch block. The batch mode recreates the
  table on SQLite and keeps its check constraints and foreign keys, while
  PostgreSQL receives ordinary ``ALTER TABLE`` statements.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_artifact_storage"
down_revision: str | None = "0002_project_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Legal values of the ``stage`` column, kept as literals so that the
#: migration stays a self contained snapshot of the schema.
STAGE_VALUES = "'design', 'development', 'testing', 'delivery', 'other'"


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("artifacts", naming_convention=None) as batch:
        batch.add_column(
            sa.Column(
                "stage",
                sa.String(length=32),
                nullable=False,
                server_default="development",
            )
        )
        batch.add_column(
            sa.Column("original_filename", sa.String(length=255), nullable=True),
        )
        batch.add_column(
            sa.Column("storage_path", sa.String(length=500), nullable=True),
        )
        batch.create_check_constraint(
            # ``op.f`` marks the name as final. Without it Alembic would hand
            # the name to the project wide naming convention
            # (``ck_%(table_name)s_%(constraint_name)s``), which prefixes the
            # already prefixed name a second time.
            op.f("ck_artifacts_stage_valid"),
            f"stage IN ({STAGE_VALUES})",
        )
        batch.create_unique_constraint(op.f("uq_artifacts_storage_path"), ["storage_path"])
        batch.create_index("ix_artifacts_project_id_task_id", ["project_id", "task_id"])
        batch.create_index("ix_artifacts_stage", ["stage"])


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("artifacts", naming_convention=None) as batch:
        batch.drop_index("ix_artifacts_stage")
        batch.drop_index("ix_artifacts_project_id_task_id")
        batch.drop_constraint(op.f("uq_artifacts_storage_path"), type_="unique")
        batch.drop_constraint(op.f("ck_artifacts_stage_valid"), type_="check")
        batch.drop_column("storage_path")
        batch.drop_column("original_filename")
        batch.drop_column("stage")
