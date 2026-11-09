"""ORM models.

Every table of the platform lives here and is registered on ``Base.metadata``
so that Alembic can autogenerate migrations against a single metadata object.
"""

from app.models.approval import ApprovalRecord
from app.models.artifact import Artifact
from app.models.base import Base, TimestampMixin
from app.models.enums import (
    ApprovalDecision,
    ApprovalTargetType,
    ArtifactReviewStatus,
    ProjectStatus,
    TaskPriority,
    TaskStatus,
    WorkflowStatus,
)
from app.models.project import Project
from app.models.task import DevelopmentTask
from app.models.workflow import WorkflowInstance
from app.models.workflow_event import WorkflowEvent

__all__ = [
    "ApprovalDecision",
    "ApprovalRecord",
    "ApprovalTargetType",
    "Artifact",
    "ArtifactReviewStatus",
    "Base",
    "DevelopmentTask",
    "Project",
    "ProjectStatus",
    "TaskPriority",
    "TaskStatus",
    "TimestampMixin",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowStatus",
]
