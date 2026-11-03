"""Request scoped middleware: correlation id propagation and access logging."""

from __future__ import annotations

import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import REQUEST_ID_HEADER, request_id_var
from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = ["AccessLogMiddleware", "REQUEST_ID_HEADER", "RequestContextMiddleware"]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id to every request and echo it in the response.

    The id is stored twice on purpose: in the context variable, which the
    logging formatter reads, and in ``request.state``, which survives the
    context variable reset and is therefore still available to the outermost
    error handler when an exception leaves the middleware stack.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Write one structured access log line per request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "%.3fms %s %s -> error",
                duration_ms,
                request.method,
                request.url.path,
            )
            raise
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "%s %s -> %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
