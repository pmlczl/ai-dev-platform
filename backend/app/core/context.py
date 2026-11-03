"""Context variables shared across request handling layers."""

from __future__ import annotations

from contextvars import ContextVar

from starlette.requests import Request

#: Identifier of the request currently being processed. Used by the logging
#: formatter and by the unified error payload.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

#: Name of the header that carries the correlation id into and out of the API.
REQUEST_ID_HEADER = "X-Request-ID"


def resolve_request_id(request: Request | None = None) -> str:
    """Return the correlation id of the request that is being handled.

    The context variable is the primary source, but it is reset as soon as an
    exception leaves the middleware stack, while the outermost error handler
    still needs the id. ``request.state`` is backed by ``scope["state"]`` and
    therefore survives that reset, which keeps the error envelope in sync with
    the access log.
    """

    state_request_id = getattr(getattr(request, "state", None), "request_id", None)
    if state_request_id:
        return str(state_request_id)
    return request_id_var.get()
