"""Tests for the health endpoints and the cross cutting concerns."""

from __future__ import annotations


def test_health_endpoint_returns_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"]
    assert payload["version"]
    assert payload["environment"]
    assert payload["timestamp"]


def test_health_endpoint_is_documented(client):
    schema = client.get("/openapi.json").json()

    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/health/ready" in schema["paths"]


def test_swagger_ui_is_served(client):
    assert client.get("/docs").status_code == 200


def test_request_id_header_is_echoed(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["X-Request-ID"] == "test-request-id"


def test_cors_preflight_is_allowed(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
