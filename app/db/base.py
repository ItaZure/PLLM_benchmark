"""SQLAlchemy declarative base and shared metadata.

All model modules must be imported somewhere that reaches this Base so that
Alembic autogenerate sees the full metadata. See app/models/__init__.py.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass
