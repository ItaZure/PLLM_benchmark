"""Pydantic schemas for chat/image model management."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderMode(str, Enum):
    """Image model platform call modes. Only these two are supported."""

    POE_CHAT = "poe_chat"
    AICODEWITH_ASYNC = "aicodewith_async"


class ModelBase(BaseModel):
    name: str = Field(..., max_length=100)
    api_base_url: str = Field(..., max_length=500)
    model_name: str = Field(..., max_length=200)
    default_params: dict[str, Any] = Field(default_factory=dict)


class ModelCreate(ModelBase):
    api_key: str = Field(..., max_length=500)


class ModelUpdate(BaseModel):
    """All fields optional; only provided fields are updated.

    api_key: omit or send null to keep the existing key; send a new string
    to replace it.
    """

    name: str | None = Field(None, max_length=100)
    api_base_url: str | None = Field(None, max_length=500)
    model_name: str | None = Field(None, max_length=200)
    default_params: dict[str, Any] | None = None
    api_key: str | None = Field(None, max_length=500)


class ModelResponse(ModelBase):
    """List/detail response. api_key is masked; api_key_set flags presence."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    api_key_masked: str
    api_key_set: bool
    test_status: str | None = None
    test_error: str | None = None
    last_tested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TestResult(BaseModel):
    available: bool
    error: str | None = None
    tested_at: datetime


# --- Image model variants (add required provider_mode) ---


class ImageModelCreate(ModelCreate):
    provider_mode: ProviderMode


class ImageModelUpdate(ModelUpdate):
    provider_mode: ProviderMode | None = None


class ImageModelResponse(ModelResponse):
    provider_mode: ProviderMode
