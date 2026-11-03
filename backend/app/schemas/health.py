"""Schemas describing the health endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: str = Field(default="ok", examples=["ok"])
    app: str = Field(examples=["AI Dev Platform"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])
    timestamp: datetime


class DatabaseHealth(BaseModel):
    """Database connectivity probe result."""

    status: str = Field(default="ok", examples=["ok", "unavailable"])
    latency_ms: float | None = Field(default=None, examples=[1.42])


class ReadinessResponse(BaseModel):
    """Readiness payload, including the database probe."""

    status: str = Field(default="ok", examples=["ok", "not_ready"])
    database: DatabaseHealth
    timestamp: datetime
