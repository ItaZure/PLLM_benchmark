"""Chat and image generation model registrations."""
from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TestStatusMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ChatModel(UUIDPrimaryKeyMixin, TimestampMixin, TestStatusMixin, Base):
    """A registered chat (text) LLM endpoint."""

    __tablename__ = "chat_models"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class ImageModel(UUIDPrimaryKeyMixin, TimestampMixin, TestStatusMixin, Base):
    """A registered image generation model endpoint.

    provider_mode is required and only supports two platform modes (no
    generalization by design):
      - 'poe_chat': POE synchronous, image via /v1/chat/completions
      - 'aicodewith_async': aicodewith async task, submit + poll
    """

    __tablename__ = "image_models"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    provider_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="poe_chat"
    )
