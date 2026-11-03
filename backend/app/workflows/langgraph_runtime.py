"""Thin wrapper around the optional LangGraph dependency.

LangGraph is imported lazily so that the API can start even when the workflow
extra is not installed yet.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class LangGraphUnavailableError(RuntimeError):
    """Raised when LangGraph is required but not installed."""


def load_langgraph() -> Any:
    """Import and return the ``langgraph`` module.

    Raises:
        LangGraphUnavailableError: when LangGraph is not installed.
    """

    try:
        import langgraph  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise LangGraphUnavailableError(
            "LangGraph is not installed. Install the backend dependencies first."
        ) from exc
    return langgraph
