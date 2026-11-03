"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    """Application instance shared by the test session."""

    return create_app()


@pytest.fixture(scope="session")
def client(app):
    """HTTP client with the application lifespan running."""

    with TestClient(app) as test_client:
        yield test_client
