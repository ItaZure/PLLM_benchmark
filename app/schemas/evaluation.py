"""Pydantic schemas for evaluation runs."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvalTaskItem(BaseModel):
    task_id: uuid.UUID
    score_weight: int = Field(1, ge=1, le=20)


class EvalModelItem(BaseModel):
    model_id: uuid.UUID
    model_type: str = Field(..., pattern="^(chat|image)$")


class EvaluationCreate(BaseModel):
    name: str = Field(..., max_length=200)
    tasks: list[EvalTaskItem] = Field(..., min_length=1)
    models: list[EvalModelItem] = Field(..., min_length=1)


class EvaluationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    task_count: int = 0
    model_count: int = 0
    created_at: datetime
    finished_at: datetime | None = None
    # Frontend routing helpers:
    #   has_open_tasks — evaluation contains open-type tasks (needs blind scoring)
    #   awaiting_scoring — status == 'scoring' (blind scoring not finished)
    # "评测中" (user-visible) = status in {running, scoring}; only 'done' -> 查看.
    has_open_tasks: bool = False
    awaiting_scoring: bool = False


class ResultItem(BaseModel):
    result_id: uuid.UUID
    task_id: uuid.UUID
    task_name: str | None = None
    # model_id / model_name are hidden (None) for open-type results until the
    # evaluation is 'done' (blind-scoring reveal gate).
    model_id: uuid.UUID | None = None
    model_type: str
    model_name: str | None = None
    output_text: str | None = None
    ttft_ms: float | None = None
    total_duration_ms: float | None = None
    output_char_count: int | None = None
    char_per_sec: float | None = None
    score: float | None = None
    auto_scored: bool = False
    status: str
    error: str | None = None


class EvalTaskDetail(BaseModel):
    task_id: uuid.UUID
    name: str | None = None
    task_type: str | None = None
    score_weight: int


class EvalModelDetail(BaseModel):
    model_id: uuid.UUID
    model_type: str
    name: str | None = None


class EvaluationDetail(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    tasks: list[EvalTaskDetail] = Field(default_factory=list)
    models: list[EvalModelDetail] = Field(default_factory=list)
    results: list[ResultItem] = Field(default_factory=list)


class EvaluationStatus(BaseModel):
    status: str
    total: int
    completed: int
    success: int = 0
    failed: int = 0
    cancelled: int = 0
    skipped: int = 0


# ---- Blind scoring (open-type) ----

class ScoringSessionItem(BaseModel):
    """One open task's blind-scoring session progress in the list view.

    ready — every participating model has produced a result for this task, so
    the blind set is final and scoring can begin. Not-ready tasks are still
    generating and must be disabled in the UI.
    """
    task_id: uuid.UUID
    task_name: str | None = None
    ready: bool = False
    total: int = 0
    scored: int = 0
    completed: bool = False


class BlindItem(BaseModel):
    """A single blind entry shown to the user (no model attribution)."""
    blind_id: uuid.UUID          # == result_id, but labeled generically
    model_type: str              # chat / image -> lets frontend pick renderer
    output_text: str | None = None
    current_score: float | None = None  # already-scored value if revisited


class ScoringTaskDetail(BaseModel):
    """Full blind-scoring view for one open task."""
    task_id: uuid.UUID
    task_name: str | None = None
    prompt: str | None = None
    rubric: str | None = None
    score_weight: int
    current_index: int
    total: int
    completed: bool
    items: list[BlindItem] = Field(default_factory=list)


class ScoreSubmit(BaseModel):
    """Submit a 1-5 tier score for one blind entry."""
    blind_id: uuid.UUID
    tier: int = Field(..., ge=1, le=5)
