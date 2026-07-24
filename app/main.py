"""FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import logging

from app.api.routers import dimensions, evaluations, health, models, tasks
from app.api.routers import settings as settings_router
from app.core.config import settings
from app.services import eval_runner

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title=settings.APP_NAME)


@app.on_event("startup")
async def _heal_orphaned_evaluations() -> None:
    """Recover evaluations stuck at 'running' after a restart (single-worker)."""
    try:
        healed = await eval_runner.heal_orphaned_runs()
        if healed:
            logger.warning("自愈了 %d 个中断的评测: %s", len(healed), ", ".join(healed))
    except Exception as exc:  # never block app startup on self-heal
        logger.error("评测自愈失败: %s", exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers are mounted under the /api prefix.
app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(models.chat_router, prefix=settings.API_PREFIX)
app.include_router(models.image_router, prefix=settings.API_PREFIX)
app.include_router(dimensions.router, prefix=settings.API_PREFIX)
app.include_router(tasks.router, prefix=settings.API_PREFIX)
app.include_router(evaluations.router, prefix=settings.API_PREFIX)
app.include_router(settings_router.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict:
    return {"data": {"app": settings.APP_NAME}, "message": "ok"}
