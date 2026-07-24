"""CRUD for dimensions + model whitelist management."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.dimension import Dimension, DimensionModelWhitelist
from app.models.model import ChatModel, ImageModel
from app.models.task import Task
from app.schemas.dimension import (
    DimensionCreate,
    DimensionReorder,
    DimensionResponse,
    DimensionUpdate,
    WhitelistModelInfo,
    WhitelistUpdate,
)

router = APIRouter(prefix="/dimensions", tags=["dimensions"])


async def _get_or_404(db: AsyncSession, dim_id: uuid.UUID) -> Dimension:
    obj = await db.get(Dimension, dim_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="维度不存在")
    return obj


async def _model_name_lookup(db: AsyncSession) -> dict[tuple[uuid.UUID, str], str]:
    """Map (model_id, model_type) -> display name for both model tables."""
    lookup: dict[tuple[uuid.UUID, str], str] = {}
    for row in (await db.execute(select(ChatModel.id, ChatModel.name))).all():
        lookup[(row[0], "chat")] = row[1]
    for row in (await db.execute(select(ImageModel.id, ImageModel.name))).all():
        lookup[(row[0], "image")] = row[1]
    return lookup


async def _serialize(db: AsyncSession, dim: Dimension, name_lookup=None) -> dict:
    if name_lookup is None:
        name_lookup = await _model_name_lookup(db)
    # Task count
    task_count = await db.scalar(
        select(func.count()).select_from(Task).where(Task.dimension_id == dim.id)
    )
    # Whitelist entries
    wl_rows = (
        await db.execute(
            select(DimensionModelWhitelist).where(
                DimensionModelWhitelist.dimension_id == dim.id
            )
        )
    ).scalars().all()
    whitelist = [
        WhitelistModelInfo(
            model_id=w.model_id,
            model_type=w.model_type,
            name=name_lookup.get((w.model_id, w.model_type)),
        )
        for w in wl_rows
    ]
    return DimensionResponse(
        id=dim.id,
        name=dim.name,
        description=dim.description,
        system_prompt=dim.system_prompt,
        task_count=task_count or 0,
        sort_order=dim.sort_order,
        whitelist=whitelist,
        created_at=dim.created_at,
    ).model_dump()


@router.get("")
async def list_dimensions(db: AsyncSession = Depends(get_db)) -> dict:
    dims = (
        await db.execute(
            select(Dimension).order_by(
                Dimension.sort_order.asc(), Dimension.created_at.desc()
            )
        )
    ).scalars().all()
    name_lookup = await _model_name_lookup(db)
    items = [await _serialize(db, d, name_lookup) for d in dims]
    return {"data": items, "message": "ok"}


@router.put("/reorder")
async def reorder_dimensions(
    payload: DimensionReorder, db: AsyncSession = Depends(get_db)
) -> dict:
    """Assign sort_order by the position of each id in the given list."""
    dims = (await db.execute(select(Dimension))).scalars().all()
    by_id = {d.id: d for d in dims}
    order = {dim_id: idx for idx, dim_id in enumerate(payload.ids)}
    # Ids not included keep going after the ordered ones, preserving relative order.
    tail = len(order)
    for d in dims:
        if d.id in order:
            d.sort_order = order[d.id]
        else:
            d.sort_order = tail
            tail += 1
    await db.commit()
    name_lookup = await _model_name_lookup(db)
    ordered = sorted(by_id.values(), key=lambda x: x.sort_order)
    items = [await _serialize(db, d, name_lookup) for d in ordered]
    return {"data": items, "message": "ok"}


@router.post("")
async def create_dimension(
    payload: DimensionCreate, db: AsyncSession = Depends(get_db)
) -> dict:
    max_order = await db.scalar(select(func.max(Dimension.sort_order)))
    dim = Dimension(
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        sort_order=(max_order + 1) if max_order is not None else 0,
    )
    db.add(dim)
    await db.commit()
    await db.refresh(dim)
    return {"data": await _serialize(db, dim), "message": "ok"}


@router.put("/{dim_id}")
async def update_dimension(
    dim_id: uuid.UUID, payload: DimensionUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    dim = await _get_or_404(db, dim_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dim, field, value)
    await db.commit()
    await db.refresh(dim)
    return {"data": await _serialize(db, dim), "message": "ok"}


@router.delete("/{dim_id}")
async def delete_dimension(
    dim_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    dim = await _get_or_404(db, dim_id)
    # Cascade guard: refuse deletion when tasks are attached.
    task_count = await db.scalar(
        select(func.count()).select_from(Task).where(Task.dimension_id == dim_id)
    )
    if task_count:
        raise HTTPException(
            status_code=409,
            detail=f"该维度下有 {task_count} 个任务，请先删除这些任务再删除维度",
        )
    await db.delete(dim)
    await db.commit()
    return {"data": {"id": str(dim_id)}, "message": "ok"}


@router.put("/{dim_id}/whitelist")
async def update_whitelist(
    dim_id: uuid.UUID, payload: WhitelistUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    await _get_or_404(db, dim_id)
    # Validate every referenced model exists in its table.
    for item in payload.models:
        model_cls = ChatModel if item.model_type == "chat" else ImageModel
        if await db.get(model_cls, item.model_id) is None:
            raise HTTPException(
                status_code=400,
                detail=f"模型不存在：{item.model_type} {item.model_id}",
            )
    # Full replacement: drop existing rows, insert new set.
    existing = (
        await db.execute(
            select(DimensionModelWhitelist).where(
                DimensionModelWhitelist.dimension_id == dim_id
            )
        )
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    for item in payload.models:
        db.add(
            DimensionModelWhitelist(
                dimension_id=dim_id,
                model_id=item.model_id,
                model_type=item.model_type,
            )
        )
    await db.commit()
    dim = await _get_or_404(db, dim_id)
    return {"data": await _serialize(db, dim), "message": "ok"}
