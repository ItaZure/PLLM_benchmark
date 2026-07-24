"""CRUD for benchmark tasks."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.settings import get_generation_model
from app.db.session import get_db
from app.models.dimension import Dimension
from app.models.task import Task
from app.schemas.task import (
    TaskCreate,
    TaskGenerateRequest,
    TaskGenerateResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.task_generator import GenerationError, generate_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _get_or_404(db: AsyncSession, task_id: uuid.UUID) -> Task:
    obj = await db.get(Task, task_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return obj


async def _dim_name_lookup(db: AsyncSession) -> dict[uuid.UUID, str]:
    rows = (await db.execute(select(Dimension.id, Dimension.name))).all()
    return {r[0]: r[1] for r in rows}


def _serialize(task: Task, dim_names: dict[uuid.UUID, str]) -> dict:
    return TaskResponse(
        id=task.id,
        dimension_id=task.dimension_id,
        dimension_name=dim_names.get(task.dimension_id),
        name=task.name,
        task_type=task.task_type,
        prompt=task.prompt,
        scoring_regex=task.scoring_regex,
        expected_answer=task.expected_answer,
        scoring_rubric=task.scoring_rubric,
        created_at=task.created_at,
        updated_at=task.updated_at,
    ).model_dump()


async def _ensure_dimension(db: AsyncSession, dim_id: uuid.UUID) -> None:
    if await db.get(Dimension, dim_id) is None:
        raise HTTPException(status_code=400, detail="所属维度不存在")


@router.get("")
async def list_tasks(
    dimension_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Task).order_by(Task.created_at.desc())
    if dimension_id is not None:
        stmt = stmt.where(Task.dimension_id == dimension_id)
    tasks = (await db.execute(stmt)).scalars().all()
    dim_names = await _dim_name_lookup(db)
    items = [_serialize(t, dim_names) for t in tasks]
    return {"data": items, "message": "ok"}


@router.post("/generate")
async def generate_task_endpoint(
    payload: TaskGenerateRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """AI-generate one task for the given dimension + type (not persisted)."""
    dim = await db.get(Dimension, payload.dimension_id)
    if dim is None:
        raise HTTPException(status_code=400, detail="所属维度不存在")
    model = await get_generation_model(db)
    if model is None:
        raise HTTPException(
            status_code=400,
            detail="尚未配置评测生成模型，请先在【评测生成模型】页面选择",
        )
    try:
        result = await generate_task(
            model=model,
            task_type=payload.task_type,
            dim_name=dim.name,
            dim_desc=dim.description,
            name_hint=payload.name_hint,
        )
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": TaskGenerateResponse(**result).model_dump(), "message": "ok"}


@router.post("")
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure_dimension(db, payload.dimension_id)
    task = Task(**payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    dim_names = await _dim_name_lookup(db)
    return {"data": _serialize(task, dim_names), "message": "ok"}


@router.put("/{task_id}")
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    task = await _get_or_404(db, task_id)
    await _ensure_dimension(db, payload.dimension_id)
    for field, value in payload.model_dump().items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    dim_names = await _dim_name_lookup(db)
    return {"data": _serialize(task, dim_names), "message": "ok"}


@router.delete("/{task_id}")
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    task = await _get_or_404(db, task_id)
    await db.delete(task)
    await db.commit()
    return {"data": {"id": str(task_id)}, "message": "ok"}
