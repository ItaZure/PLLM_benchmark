"""Global application settings, stored as a simple key-value table.

Single-user tool: a handful of global switches (e.g. which chat model is
used for AI-assisted task generation) live here instead of a config file so
they can be edited from the web UI.
"""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AppSetting(TimestampMixin, Base):
    """One row per setting key. `key` is the primary key."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)


# Well-known setting keys.
KEY_GENERATION_CHAT_MODEL_ID = "generation_chat_model_id"
