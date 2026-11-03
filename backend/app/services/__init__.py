"""Service layer.

Services hold the business logic that the API layer calls. They must not
depend on FastAPI request objects so that they stay reusable from workflows
and background jobs.
"""

__all__: list[str] = []
