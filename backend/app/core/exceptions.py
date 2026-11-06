"""Unified exception types and handlers.

Every error leaving the API is rendered with the same envelope::

    {
        "code": "NOT_FOUND",
        "message": "human readable message",
        "detail": null,
        "request_id": "0f0c...",
        "timestamp": "2026-11-03T10:00:00+00:00"
    }
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import REQUEST_ID_HEADER, resolve_request_id
from app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorCode(StrEnum):
    """Stable, machine readable error identifiers."""

    APP_ERROR = "APP_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


_STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    # 422 is written as a literal: the starlette constant is deprecated and the
    # numeric value is stable across framework versions.
    422: ErrorCode.VALIDATION_ERROR,
    status.HTTP_501_NOT_IMPLEMENTED: ErrorCode.NOT_IMPLEMENTED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


class AppException(Exception):
    """Base class for expected, business level errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: ErrorCode = ErrorCode.APP_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundException(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND


class ConflictException(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CONFLICT


class ValidationException(AppException):
    """Raised when the request is syntactically valid but semantically wrong."""

    status_code = 422
    code = ErrorCode.VALIDATION_ERROR


class ServiceUnavailableException(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.SERVICE_UNAVAILABLE


def build_error_payload(
    request: Request,
    code: ErrorCode,
    message: str,
    detail: Any = None,
) -> dict[str, Any]:
    """Build the unified error envelope.

    ``request`` is required so that the correlation id can be read from
    ``request.state``, which is still populated when the error handler runs
    outside of the middleware that owns the context variable.
    """

    return {
        "code": code.value,
        "message": message,
        "detail": jsonable_encoder(detail) if detail is not None else None,
        "request_id": resolve_request_id(request),
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _response_headers(
    request: Request,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the response headers, always including the correlation id."""

    headers = {REQUEST_ID_HEADER: resolve_request_id(request)}
    if extra:
        headers.update(extra)
    return headers


def register_exception_handlers(app: FastAPI) -> None:
    """Register the unified exception handlers on the application."""

    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Handled application exception: code=%s message=%s",
            exc.code.value,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(request, exc.code, exc.message, exc.detail),
            headers=_response_headers(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.APP_ERROR)
        detail = exc.detail if isinstance(exc.detail, (dict, list)) else None
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(request, code, message, detail),
            headers=_response_headers(request, getattr(exc, "headers", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=build_error_payload(
                request,
                ErrorCode.VALIDATION_ERROR,
                "Request validation failed",
                exc.errors(),
            ),
            headers=_response_headers(request),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error_payload(
                request,
                ErrorCode.INTERNAL_SERVER_ERROR,
                "Internal server error",
            ),
            headers=_response_headers(request),
        )
