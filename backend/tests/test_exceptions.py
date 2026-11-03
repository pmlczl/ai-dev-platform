"""Tests for the unified exception handling."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app

app = create_app()


class EchoPayload(BaseModel):
    name: str


@app.get("/_test/boom")
async def _boom() -> None:
    raise RuntimeError("boom")


@app.post("/_test/echo")
async def _echo(payload: EchoPayload) -> dict[str, str]:
    return {"name": payload.name}


client = TestClient(app, raise_server_exceptions=False)


def test_not_found_uses_the_unified_envelope():
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "NOT_FOUND"
    assert payload["message"]
    assert payload["request_id"]
    assert payload["timestamp"]


def test_validation_error_uses_the_unified_envelope():
    response = client.post("/_test/echo", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["detail"]


def test_unhandled_exception_returns_500_envelope():
    response = client.get("/_test/boom")

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INTERNAL_SERVER_ERROR"
    assert payload["request_id"] != "-"


def test_unhandled_exception_keeps_the_request_id():
    """The 500 envelope and its headers must carry the correlation id.

    The error handler runs outside of the middleware that owns the context
    variable, so the id is taken from ``request.state`` instead.
    """

    response = client.get("/_test/boom", headers={"X-Request-ID": "boom-request-id"})

    assert response.status_code == 500
    payload = response.json()
    assert payload["request_id"] == "boom-request-id"
    assert response.headers["X-Request-ID"] == "boom-request-id"


def test_not_found_response_carries_the_request_id_header():
    response = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "missing-request-id"})

    assert response.status_code == 404
    assert response.json()["request_id"] == "missing-request-id"
    assert response.headers["X-Request-ID"] == "missing-request-id"
