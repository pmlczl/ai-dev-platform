"""Aggregated router for API version 1."""

from fastapi import APIRouter

from app.api.v1.endpoints import artifacts, health, projects, tasks, workflows

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(artifacts.router, tags=["artifacts"])
api_router.include_router(workflows.router, tags=["workflows"])
