"""Logging configuration.

A single ``configure_logging`` entry point is called once during application
start-up. It supports a human readable text format for local development and a
JSON format for container log collectors.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.core.config import Settings
from app.core.context import request_id_var

_CONFIGURED = False

_TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ContextFilter(logging.Filter):
    """Inject the current request id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once, using the application settings."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Keep third-party loggers from polluting the application output.
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module level logger."""

    return logging.getLogger(name)
