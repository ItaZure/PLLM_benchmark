"""Evaluation dimensions and their model whitelist."""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Dimension(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A benchmark dimension, e.g. writing, math, image generation."""

    __tablename__ = "dimensions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fixed system prompt for this dimension; passed as system role at eval time.
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Manual display order (ascending). Lower = shown first. Used by all dropdowns.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Per-dimension AI task-generation model (chat only). Nullable = not configured.
    generation_model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, default=None
    )

    whitelist: Mapped[list["DimensionModelWhitelist"]] = relationship(
        back_populates="dimension",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="dimension")  # noqa: F821


class DimensionModelWhitelist(UUIDPrimaryKeyMixin, Base):
    """Which models are allowed to participate in a given dimension."""

    __tablename__ = "dimension_model_whitelist"

    dimension_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dimensions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Points at chat_models.id or image_models.id depending on model_type.
    model_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)

    dimension: Mapped["Dimension"] = relationship(back_populates="whitelist")
