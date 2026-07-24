"""Pydantic schemas for global app settings."""
import uuid

from pydantic import BaseModel


class GenerationModelResponse(BaseModel):
    """Current AI task-generation model selection.

    generation_chat_model_id is None when unset. The extra fields are
    convenience so the frontend can render the current name without a
    second lookup.
    """

    generation_chat_model_id: uuid.UUID | None = None
    model_name: str | None = None
    display_name: str | None = None


class GenerationModelUpdate(BaseModel):
    # None clears the selection.
    generation_chat_model_id: uuid.UUID | None = None
