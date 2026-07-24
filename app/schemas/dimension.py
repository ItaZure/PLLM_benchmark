"""Pydantic schemas for dimension management + model whitelist."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WhitelistItem(BaseModel):
    model_id: uuid.UUID
    model_type: str = Field(..., pattern="^(chat|image)$")


class DimensionCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = None
    system_prompt: str | None = None


class DimensionUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = None
    system_prompt: str | None = None


class WhitelistModelInfo(BaseModel):
    """A whitelisted model, enriched with its display name for the frontend."""

    model_id: uuid.UUID
    model_type: str
    name: str | None = None


class DimensionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    system_prompt: str | None = None
    task_count: int = 0
    sort_order: int = 0
    whitelist: list[WhitelistModelInfo] = Field(default_factory=list)
    created_at: datetime


class WhitelistUpdate(BaseModel):
    models: list[WhitelistItem] = Field(default_factory=list)


class DimensionReorder(BaseModel):
    """Full ordered list of dimension ids; index becomes the new sort_order."""

    ids: list[uuid.UUID] = Field(default_factory=list)
