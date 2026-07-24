"""Evaluation runs, their task/model associations, results and scoring sessions."""
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Evaluation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single evaluation session (a batch run over tasks x models)."""

    __tablename__ = "evaluations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 'pending' / 'running' / 'scoring' / 'done' / 'cancelled'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    finished_at: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    eval_tasks: Mapped[list["EvaluationTask"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    eval_models: Mapped[list["EvaluationModel"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    results: Mapped[list["Result"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    scoring_sessions: Mapped[list["OpenScoringSession"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationTask(UUIDPrimaryKeyMixin, Base):
    """A task included in an evaluation, with its score weight."""

    __tablename__ = "evaluation_tasks"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Weight 1-20, default 1
    score_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="eval_tasks")


class EvaluationModel(UUIDPrimaryKeyMixin, Base):
    """A model included in an evaluation."""

    __tablename__ = "evaluation_models"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="eval_models")


class Result(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One task x model output with performance metrics and score."""

    __tablename__ = "results"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)

    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Time to first token (ms)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Total generation time (ms)
    total_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Output character count, len(output_text)
    output_char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Generation speed, chars/sec
    char_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_scored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 'success' / 'failed' / 'cancelled'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="results")


class OpenScoringSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Blind scoring session for one open-type task within an evaluation."""

    __tablename__ = "open_scoring_sessions"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Shuffled list of result_id (as strings) for blind display order.
    shuffled_order: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    current_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="scoring_sessions")
