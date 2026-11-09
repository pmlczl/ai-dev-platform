"""Workflow layer (LangGraph orchestration).

The layer hosts the workflow graphs and the registry they are published
through. The graphs are built by the runtime, which owns the checkpointer -
a workflow never sees a checkpoint itself.
"""

from app.workflows.base import BaseWorkflow, WorkflowExecutionError, WorkflowState
from app.workflows.dev_workflow import DevWorkflow
from app.workflows.registry import (
    clear_workflows,
    get_workflow,
    list_workflows,
    register_workflow,
)

__all__ = [
    "BaseWorkflow",
    "DevWorkflow",
    "WorkflowExecutionError",
    "WorkflowState",
    "clear_workflows",
    "get_workflow",
    "list_workflows",
    "register_workflow",
]

# The workflows of the platform are published through the registry, so that
# the runtime can compile them without knowing their concrete classes.
register_workflow(DevWorkflow(), override=True)
