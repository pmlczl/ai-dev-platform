"""ORM models.

Domain models are added here as the platform grows. The declarative base is
exported so that Alembic can autogenerate migrations against a single
metadata object.
"""

from app.models.base import Base, TimestampMixin

__all__ = ["Base", "TimestampMixin"]
