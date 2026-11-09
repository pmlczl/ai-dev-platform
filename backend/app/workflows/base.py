"""Workflow foundation.

The workflow layer hosts LangGraph based orchestration. This module only
provides the abstractions and the registry; no concrete agent workflow is
implemented yet (that work is intentionally out of scope of the base
scaffold).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, TypedDict


class WorkflowState(TypedDict, total=False):
    """Minimal state shape shared by workflow graphs.

    Concrete workflows are expected to declare their own specialised state.
    """

    input: str
    output: str
    error: str


class BaseWorkflow(ABC):
    """Contract every workflow implementation has to fulfil."""

    name: ClassVar[str] = "base"
    description: ClassVar[str] = ""

    @abstractmethod
    def build_graph(self, checkpointer: Any | None = None) -> Any:
        """Build and compile the LangGraph graph of this workflow.

        Args:
            checkpointer: Optional checkpointer the graph is compiled with.
                It is the object that persists the state of a run; the
                runtime owns it, the workflow only receives it.

        Returns:
            The compiled LangGraph application.
        """

    async def run(self, state: WorkflowState) -> WorkflowState:
        """Execute the workflow. Overridden once concrete graphs exist."""

        graph = self.build_graph()
        return await graph.ainvoke(state)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{type(self).__name__} name={self.name!r}>"


class WorkflowExecutionError(RuntimeError):
    """Raised when a node cannot continue the workflow.

    The error carries a message that is safe to show to the operator: the
    workflow service turns it into a failed workflow instance.
    """
