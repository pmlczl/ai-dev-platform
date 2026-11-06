"""Domain enumerations shared by the ORM models and the API schemas.

The values are persisted as plain strings guarded by ``CHECK`` constraints
instead of native PostgreSQL enum types. Adding a value then only requires a
constraint change - no ``ALTER TYPE`` - and the schema stays portable for the
SQLite based test runs. The enumerations live outside ``app.core`` because the
core layer must stay free of domain concepts.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle of a project."""

    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    """Lifecycle of a development task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    """Relative priority of a development task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class WorkflowStatus(StrEnum):
    """Lifecycle of a workflow instance."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactReviewStatus(StrEnum):
    """Review state of an artifact tracked by the platform."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ArtifactStage(StrEnum):
    """Development stage an artifact belongs to."""

    DESIGN = "design"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DELIVERY = "delivery"
    OTHER = "other"


class ApprovalDecision(StrEnum):
    """Outcome of a single approval record."""

    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ApprovalTargetType(StrEnum):
    """Kind of object an approval record refers to."""

    TASK = "task"
    ARTIFACT = "artifact"
    WORKFLOW_INSTANCE = "workflow_instance"


def sql_values(enum_class: type[StrEnum]) -> str:
    """Render the members of an enumeration as a SQL literal list.

    The result is meant to be embedded in a ``CHECK`` constraint, for example
    ``f"status IN ({sql_values(ProjectStatus)})"``.
    """

    return ", ".join(f"'{member.value}'" for member in enum_class)
