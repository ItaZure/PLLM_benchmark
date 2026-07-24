"""Pydantic schemas for task management."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskBase(BaseModel):
    dimension_id: uuid.UUID
    name: str = Field(..., max_length=200)
    task_type: str = Field(..., pattern="^(open|closed)$")
    prompt: str
    scoring_regex: str | None = Field(None, max_length=500)
    expected_answer: str | None = Field(None, max_length=500)
    scoring_rubric: str | None = None

    @model_validator(mode="after")
    def _check_type_fields(self):
        """Closed tasks need regex + expected answer; open-task rubric is optional."""
        if self.task_type == "closed":
            if not (self.scoring_regex and self.scoring_regex.strip()):
                raise ValueError("封闭型任务必须填写 scoring_regex（答案提取正则）")
            if not (self.expected_answer and self.expected_answer.strip()):
                raise ValueError("封闭型任务必须填写 expected_answer（标准答案）")
        # 开放型任务的 scoring_rubric 为选填
        return self


class TaskCreate(TaskBase):
    pass


class TaskUpdate(TaskBase):
    """Full replacement on update; same validation as create."""

    pass


class TaskGenerateRequest(BaseModel):
    dimension_id: uuid.UUID
    task_type: str = Field(..., pattern="^(open|closed)$")
    # 可选：已填的任务名称。若提供，AI 需围绕该名称出题。
    name_hint: str | None = Field(None, max_length=200)


class TaskGenerateResponse(BaseModel):
    """Generated task fields to prefill the form (not persisted)."""

    name: str
    task_type: str
    prompt: str
    scoring_regex: str | None = None
    expected_answer: str | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dimension_id: uuid.UUID
    dimension_name: str | None = None
    name: str
    task_type: str
    prompt: str
    scoring_regex: str | None = None
    expected_answer: str | None = None
    scoring_rubric: str | None = None
    created_at: datetime
    updated_at: datetime
