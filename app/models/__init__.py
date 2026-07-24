"""Import all ORM models so that Base.metadata is complete.

Alembic autogenerate and create_all rely on every model being registered
against the shared Base.metadata. Import them all here.
"""
from app.db.base import Base
from app.models.dimension import Dimension, DimensionModelWhitelist
from app.models.evaluation import (
    Evaluation,
    EvaluationModel,
    EvaluationTask,
    OpenScoringSession,
    Result,
)
from app.models.model import ChatModel, ImageModel
from app.models.setting import AppSetting
from app.models.task import Task

__all__ = [
    "Base",
    "ChatModel",
    "ImageModel",
    "Dimension",
    "DimensionModelWhitelist",
    "Task",
    "Evaluation",
    "EvaluationTask",
    "EvaluationModel",
    "Result",
    "OpenScoringSession",
    "AppSetting",
]
