"""Baseline revision of the platform scaffold.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-03

The platform scaffold does not define any domain table yet, so this baseline
only records the migration anchor. Domain models are added in follow-up
revisions.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema object yet - the baseline only anchors the revision chain."""


def downgrade() -> None:
    """Nothing to revert."""
