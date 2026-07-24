"""Evaluation orchestration: async run loop + in-memory run registry.

Single-worker assumption (design 5.6): the registry lives in process memory.
Phase 4b adds cancellation via RunContext.cancel_event; the plumbing is here
already so 4b only needs to wire the endpoint.
"""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.dimension import Dimension
from app.models.evaluation import (
    Evaluation,
    EvaluationModel,
    EvaluationTask,
    OpenScoringSession,
    Result,
)
from app.models.model import ChatModel, ImageModel
from app.models.task import Task
from app.services.llm_runner import (
    auto_score,
    run_chat_single,
    run_image_aicodewith_async,
    run_image_poe_chat,
)

# Limit concurrent outbound requests within one evaluation (design 5.3).
_CONCURRENCY = 5


@dataclass
class RunContext:
    task: asyncio.Task | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


# eval_id -> RunContext
running_tasks: dict[uuid.UUID, RunContext] = {}


async def _load_plan(db, eval_id: uuid.UUID):
    """Load the (task, weight) and (model) lists plus dimension prompts."""
    et_rows = (
        await db.execute(
            select(EvaluationTask).where(EvaluationTask.evaluation_id == eval_id)
        )
    ).scalars().all()
    em_rows = (
        await db.execute(
            select(EvaluationModel).where(EvaluationModel.evaluation_id == eval_id)
        )
    ).scalars().all()

    tasks: dict[uuid.UUID, Task] = {}
    dim_prompts: dict[uuid.UUID, str | None] = {}
    for et in et_rows:
        t = await db.get(Task, et.task_id)
        if t is not None:
            tasks[et.task_id] = t
            if t.dimension_id not in dim_prompts:
                dim = await db.get(Dimension, t.dimension_id)
                dim_prompts[t.dimension_id] = dim.system_prompt if dim else None
    return et_rows, em_rows, tasks, dim_prompts


async def _persist(result: Result) -> None:
    """Write one Result in its own session so status polling sees progress.

    Each combo commits independently — required because concurrent coroutines
    cannot share a single AsyncSession, and incremental commits make the
    /status endpoint reflect live progress.
    """
    async with AsyncSessionLocal() as db:
        db.add(result)
        await db.commit()


async def _run_one(eval_id, et, em, task, system_prompt, sem, cancel_event):
    """Run a single task x model combo and persist a Result row."""
    def _mk(**kw) -> Result:
        return Result(
            evaluation_id=eval_id, task_id=et.task_id,
            model_id=em.model_id, model_type=em.model_type, **kw,
        )

    # Load the model in a short-lived session (chat or image).
    async with AsyncSessionLocal() as db:
        if em.model_type == "chat":
            model = await db.get(ChatModel, em.model_id)
        else:
            model = await db.get(ImageModel, em.model_id)
    if model is None:
        await _persist(_mk(status="failed", error="模型不存在", auto_scored=False))
        return

    async with sem:
        if cancel_event.is_set():
            await _persist(_mk(status="cancelled", error="已取消", auto_scored=False))
            return
        if em.model_type == "chat":
            rr = await run_chat_single(
                api_base_url=model.api_base_url,
                api_key=model.api_key,
                model_name=model.model_name,
                default_params=model.default_params,
                system_prompt=system_prompt,
                prompt=task.prompt,
                cancel_event=cancel_event,
            )
        elif model.provider_mode == "aicodewith_async":
            rr = await run_image_aicodewith_async(
                api_base_url=model.api_base_url,
                api_key=model.api_key,
                model_name=model.model_name,
                default_params=model.default_params,
                prompt=task.prompt,
                cancel_event=cancel_event,
            )
        else:  # poe_chat (default)
            rr = await run_image_poe_chat(
                api_base_url=model.api_base_url,
                api_key=model.api_key,
                model_name=model.model_name,
                default_params=model.default_params,
                prompt=task.prompt,
                cancel_event=cancel_event,
            )

    # Image tasks are open by nature -> no auto scoring; await blind scoring.
    score = None
    auto_scored = False
    if em.model_type == "chat" and rr.status == "success" \
            and task.task_type == "closed":
        score = auto_score(
            rr.output_text, task.scoring_regex or "",
            task.expected_answer or "", et.score_weight,
        )
        auto_scored = True

    await _persist(Result(
        evaluation_id=eval_id, task_id=et.task_id,
        model_id=em.model_id, model_type=em.model_type,
        output_text=rr.output_text,
        ttft_ms=rr.ttft_ms, total_duration_ms=rr.total_duration_ms,
        output_char_count=rr.output_char_count, char_per_sec=rr.char_per_sec,
        score=score, auto_scored=auto_scored,
        status=rr.status, error=rr.error,
    ))


async def recompute_status(db, eval_id: uuid.UUID) -> str:
    """Derive an evaluation's status from DB state (single source of truth).

    Rules:
      - cancelled stays cancelled (terminal, set only by the run loop).
      - generation not finished (results < task×model combos) -> 'running'.
      - has open tasks with unfinished blind scoring -> 'scoring'.
      - otherwise -> 'done'.

    Used by both the run loop (after generation) and score submission (after a
    blind score), so the two paths can never disagree on the final state.
    """
    evaluation = await db.get(Evaluation, eval_id)
    if evaluation is None or evaluation.status == "cancelled":
        return evaluation.status if evaluation else "cancelled"

    task_ids = (await db.execute(
        select(EvaluationTask.task_id).where(
            EvaluationTask.evaluation_id == eval_id)
    )).scalars().all()
    model_count = await db.scalar(
        select(func.count()).select_from(EvaluationModel).where(
            EvaluationModel.evaluation_id == eval_id)
    ) or 0
    result_count = await db.scalar(
        select(func.count()).select_from(Result).where(
            Result.evaluation_id == eval_id)
    ) or 0
    generation_done = result_count >= len(task_ids) * model_count

    open_ids = []
    for tid in task_ids:
        t = await db.get(Task, tid)
        if t is not None and t.task_type == "open":
            open_ids.append(tid)

    if not generation_done:
        return "running"

    if open_ids:
        scoring_done = True
        for tid in open_ids:
            sess = (await db.execute(
                select(OpenScoringSession).where(
                    OpenScoringSession.evaluation_id == eval_id,
                    OpenScoringSession.task_id == tid,
                )
            )).scalar_one_or_none()
            if sess is None or not sess.completed:
                scoring_done = False
                break
        if not scoring_done:
            return "scoring"
    return "done"


async def _run_evaluation(eval_id: uuid.UUID, cancel_event: asyncio.Event):
    """Top-level coroutine: execute all combos, then finalize status."""
    try:
        # Load the plan up front in a short-lived session.
        async with AsyncSessionLocal() as db:
            et_rows, em_rows, tasks, dim_prompts = await _load_plan(db, eval_id)

        sem = asyncio.Semaphore(_CONCURRENCY)
        coros = []
        for et in et_rows:
            task = tasks.get(et.task_id)
            if task is None:
                continue
            system_prompt = dim_prompts.get(task.dimension_id)
            for em in em_rows:
                coros.append(
                    _run_one(eval_id, et, em, task, system_prompt, sem, cancel_event)
                )
        await asyncio.gather(*coros)

        # Finalize evaluation status in a fresh session. Cancellation wins;
        # otherwise derive from DB state (may already be 'done' if there were
        # no open tasks, or 'scoring' if open tasks await blind scoring).
        async with AsyncSessionLocal() as db:
            evaluation = await db.get(Evaluation, eval_id)
            if cancel_event.is_set():
                evaluation.status = "cancelled"
            else:
                evaluation.status = await recompute_status(db, eval_id)
            evaluation.finished_at = datetime.now(timezone.utc)
            await db.commit()
    finally:
        running_tasks.pop(eval_id, None)


def start_run(eval_id: uuid.UUID) -> RunContext:
    """Register and launch the background run task."""
    ctx = RunContext()
    ctx.task = asyncio.create_task(_run_evaluation(eval_id, ctx.cancel_event))
    running_tasks[eval_id] = ctx
    return ctx
