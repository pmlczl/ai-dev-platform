"""Lifecycle of the LangGraph checkpointer and of the compiled graphs.

The runtime is the only component that knows how the state of a run is
persisted. It owns the checkpointer, compiles the graph of every registered
workflow with it and hands the compiled graph to the workflow service.

Three backends are supported:

* ``postgres`` - the production backend; the checkpoints live in their own
  database so that they never mix with the business schema,
* ``sqlite`` - a single file; used for local development and the test suite,
* ``memory`` - no persistence at all; useful for quick experiments.

The backend is selected with ``WORKFLOW_CHECKPOINT_BACKEND``. Whichever
backend is used, the semantics of a run are the same: one ``thread_id`` per
workflow instance, the state of a thread survives a restart of the service.

The runtime belongs to exactly one application instance and not to the
process: the checkpointer holds a connection (and, with SQLite, a lock) that
is bound to the event loop it was opened in. A second application - a restart
of the service - therefore opens its own runtime and reads the very same
checkpoints from the very same file or database.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationException
from app.core.logging import get_logger
from app.workflows.registry import get_workflow, list_workflows

logger = get_logger(__name__)

#: Backends the runtime knows.
SUPPORTED_BACKENDS = ("postgres", "sqlite", "memory")


class WorkflowRuntime:
    """Owns the checkpointer and the compiled workflow graphs."""

    def __init__(self, backend: str | None = None) -> None:
        self._backend = (backend or get_settings().checkpoint_backend).strip().lower()
        self._checkpointer: Any | None = None
        self._graphs: dict[str, Any] = {}
        self._stack: AsyncExitStack | None = None

    @property
    def backend(self) -> str:
        """Name of the configured checkpointer backend."""

        return self._backend

    @property
    def checkpointer(self) -> Any:
        """The checkpointer the graphs are compiled with."""

        return self._checkpointer

    @property
    def ready(self) -> bool:
        """True when the runtime can serve graphs."""

        return self._checkpointer is not None

    async def startup(self) -> None:
        """Create the checkpointer and compile the graphs of all workflows."""

        if self._checkpointer is not None:
            return

        settings = get_settings()
        stack = AsyncExitStack()
        checkpointer = await _create_checkpointer(stack, self._backend, settings)
        self._stack = stack
        self._checkpointer = checkpointer

        for key in list_workflows():
            self._graphs[key] = get_workflow(key).build_graph(checkpointer)

        logger.info(
            "Workflow runtime started (backend=%s, workflows=%s)",
            self._backend,
            ", ".join(sorted(self._graphs)) or "-",
        )

    async def shutdown(self) -> None:
        """Release the checkpointer and drop the compiled graphs."""

        self._graphs.clear()
        self._checkpointer = None
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.aclose()
        logger.info("Workflow runtime stopped")

    def graph(self, workflow_key: str) -> Any:
        """Return the compiled graph of a workflow.

        A workflow that was registered after the runtime started is compiled
        on demand and cached afterwards.
        """

        graph = self._graphs.get(workflow_key)
        if graph is not None:
            return graph
        workflow = get_workflow(workflow_key)
        graph = workflow.build_graph(self._checkpointer)
        self._graphs[workflow_key] = graph
        return graph


async def _create_checkpointer(
    stack: AsyncExitStack,
    backend: str,
    settings: Settings,
) -> Any:
    """Create the checkpointer of the given backend and prepare its schema."""

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        logger.info("Using the in-memory checkpointer")
        return MemorySaver()

    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = settings.sqlite_checkpoint_path
        path.parent.mkdir(parents=True, exist_ok=True)
        saver = await stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(path)),
        )
        await saver.setup()
        logger.info("Using the SQLite checkpointer at %s", path)
        return saver

    if backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_uri),
        )
        await saver.setup()
        logger.info(
            "Using the PostgreSQL checkpointer at %s",
            settings.masked_checkpoint_database_uri,
        )
        return saver

    raise ValidationException(
        f"未知的检查点后端: {backend}（可用: {', '.join(SUPPORTED_BACKENDS)}）",
    )
