"""CRUD + availability test for chat and image models.

Chat and image models share identical management logic, so a single router
factory serves both under /api/models/chat and /api/models/image.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.model import ChatModel, ImageModel
from app.schemas.model import (
    ImageModelCreate,
    ImageModelResponse,
    ImageModelUpdate,
    ModelCreate,
    ModelResponse,
    ModelUpdate,
    TestResult,
)
from app.services.model_test import test_chat_model, test_image_model


def _mask_key(api_key: str) -> str:
    """Mask an API key, revealing only a short prefix/suffix."""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "••••"
    return f"{api_key[:4]}••••{api_key[-4:]}"


def _to_response(obj, response_cls):
    data = dict(
        id=obj.id,
        name=obj.name,
        api_base_url=obj.api_base_url,
        model_name=obj.model_name,
        default_params=obj.default_params or {},
        api_key_masked=_mask_key(obj.api_key or ""),
        api_key_set=bool(obj.api_key),
        test_status=obj.test_status,
        test_error=obj.test_error,
        last_tested_at=obj.last_tested_at,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )
    # Image models carry provider_mode; chat models do not.
    if hasattr(obj, "provider_mode"):
        data["provider_mode"] = obj.provider_mode
    return response_cls(**data)


def build_model_router(
    model_cls, prefix: str, tag: str, test_fn, create_cls, update_cls, response_cls
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    async def _get_or_404(db: AsyncSession, model_id: uuid.UUID):
        obj = await db.get(model_cls, model_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="模型不存在")
        return obj

    @router.get("")
    async def list_models(db: AsyncSession = Depends(get_db)) -> dict:
        result = await db.execute(
            select(model_cls).order_by(model_cls.created_at.desc())
        )
        items = [
            _to_response(o, response_cls).model_dump()
            for o in result.scalars().all()
        ]
        return {"data": items, "message": "ok"}

    @router.post("")
    async def create_model(
        payload: create_cls, db: AsyncSession = Depends(get_db)
    ) -> dict:
        # model_dump gives all model fields incl. provider_mode for image;
        # enum values serialize to their string value.
        fields = payload.model_dump(mode="json")
        obj = model_cls(**fields)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return {"data": _to_response(obj, response_cls).model_dump(), "message": "ok"}

    @router.put("/{model_id}")
    async def update_model(
        model_id: uuid.UUID,
        payload: update_cls,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        obj = await _get_or_404(db, model_id)
        data = payload.model_dump(exclude_unset=True, mode="json")
        # Empty/None api_key means "keep existing"; don't overwrite.
        if not data.get("api_key"):
            data.pop("api_key", None)
        for field, value in data.items():
            setattr(obj, field, value)
        await db.commit()
        await db.refresh(obj)
        return {"data": _to_response(obj, response_cls).model_dump(), "message": "ok"}

    @router.delete("/{model_id}")
    async def delete_model(
        model_id: uuid.UUID, db: AsyncSession = Depends(get_db)
    ) -> dict:
        obj = await _get_or_404(db, model_id)
        await db.delete(obj)
        await db.commit()
        return {"data": {"id": str(model_id)}, "message": "ok"}

    @router.post("/{model_id}/test")
    async def test_model(
        model_id: uuid.UUID, db: AsyncSession = Depends(get_db)
    ) -> dict:
        obj = await _get_or_404(db, model_id)
        available, error = await test_fn(
            obj.api_base_url, obj.api_key, obj.model_name
        )
        now = datetime.now(timezone.utc)
        obj.test_status = "ok" if available else "error"
        obj.test_error = None if available else error
        obj.last_tested_at = now
        await db.commit()
        result = TestResult(available=available, error=error, tested_at=now)
        return {"data": result.model_dump(), "message": "ok"}

    return router


chat_router = build_model_router(
    ChatModel, "/models/chat", "models-chat", test_chat_model,
    ModelCreate, ModelUpdate, ModelResponse,
)
image_router = build_model_router(
    ImageModel, "/models/image", "models-image", test_image_model,
    ImageModelCreate, ImageModelUpdate, ImageModelResponse,
)
