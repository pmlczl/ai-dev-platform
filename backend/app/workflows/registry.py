"""Registry keeping track of the available workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import NotFoundException
from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from app.workflows.base import BaseWorkflow

logger = get_logger(__name__)

_WORKFLOWS: dict[str, BaseWorkflow] = {}


def register_workflow(workflow: BaseWorkflow, *, override: bool = False) -> BaseWorkflow:
    """Register a workflow instance under its declared name."""

    name = workflow.name
    if name in _WORKFLOWS and not override:
        raise ValueError(f"Workflow '{name}' is already registered")
    _WORKFLOWS[name] = workflow
    logger.info("Workflow registered: %s", name)
    return workflow


def get_workflow(name: str) -> BaseWorkflow:
    """Return a registered workflow by name."""

    try:
        return _WORKFLOWS[name]
    except KeyError as exc:
        raise NotFoundException(f"Workflow '{name}' is not registered") from exc


def list_workflows() -> list[str]:
    """Return the names of all registered workflows."""

    return sorted(_WORKFLOWS)


def clear_workflows() -> None:
    """Remove every registered workflow (used by tests)."""

    _WORKFLOWS.clear()
