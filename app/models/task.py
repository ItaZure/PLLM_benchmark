"""Benchmark tasks belonging to a dimension."""
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single benchmark task (open or closed type)."""

    __tablename__ = "tasks"

    dimension_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dimensions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 'open' (human-scored) or 'closed' (regex auto-scored)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Closed-type scoring
    scoring_regex: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expected_answer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Open-type scoring
    scoring_rubric: Mapped[str | None] = mapped_column(Text, nullable=True)

    dimension: Mapped["Dimension"] = relationship(back_populates="tasks")  # noqa: F821
