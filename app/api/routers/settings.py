"""Global app settings: currently the AI task-generation model selection."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.model import ChatModel
from app.models.setting import KEY_GENERATION_CHAT_MODEL_ID, AppSetting
from app.schemas.setting import GenerationModelResponse, GenerationModelUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


async def _get_setting(db: AsyncSession, key: str) -> AppSetting | None:
    return await db.get(AppSetting, key)


async def get_generation_model(db: AsyncSession) -> ChatModel | None:
    """Resolve the configured generation chat model, or None if unset/stale."""
    row = await _get_setting(db, KEY_GENERATION_CHAT_MODEL_ID)
    if not row or not row.value:
        return None
    try:
        model_id = uuid.UUID(row.value)
    except ValueError:
        return None
    return await db.get(ChatModel, model_id)


@router.get("/generation-model")
async def get_generation_model_setting(
    db: AsyncSession = Depends(get_db),
) -> dict:
    model = await get_generation_model(db)
    if model is None:
        resp = GenerationModelResponse()
    else:
        resp = GenerationModelResponse(
            generation_chat_model_id=model.id,
            model_name=model.model_name,
            display_name=model.name,
        )
    return {"data": resp.model_dump(mode="json"), "message": "ok"}


@router.put("/generation-model")
async def set_generation_model_setting(
    payload: GenerationModelUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    new_id = payload.generation_chat_model_id
    # Validate the target chat model exists before persisting.
    if new_id is not None:
        model = await db.get(ChatModel, new_id)
        if model is None:
            raise HTTPException(status_code=400, detail="所选 Chat 模型不存在")
    row = await _get_setting(db, KEY_GENERATION_CHAT_MODEL_ID)
    value = str(new_id) if new_id is not None else None
    if row is None:
        row = AppSetting(key=KEY_GENERATION_CHAT_MODEL_ID, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()
    # Re-read for the response.
    model = await get_generation_model(db)
    if model is None:
        resp = GenerationModelResponse()
    else:
        resp = GenerationModelResponse(
            generation_chat_model_id=model.id,
            model_name=model.model_name,
            display_name=model.name,
        )
    return {"data": resp.model_dump(mode="json"), "message": "ok"}
