"""Evaluation management: create, list, detail, run, status."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.evaluation import (
    Evaluation,
    EvaluationModel,
    EvaluationTask,
    Result,
)
from app.models.model import ChatModel, ImageModel
from app.models.task import Task
from app.schemas.evaluation import (
    BlindItem,
    EvaluationCreate,
    EvaluationDetail,
    EvaluationListItem,
    EvaluationStatus,
    EvalModelDetail,
    EvalTaskDetail,
    ResultItem,
    ScoreSubmit,
    ScoringSessionItem,
    ScoringTaskDetail,
)
from app.models.evaluation import OpenScoringSession
from app.services import eval_runner
import random

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


async def _get_or_404(db: AsyncSession, eval_id: uuid.UUID) -> Evaluation:
    obj = await db.get(Evaluation, eval_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="评测不存在")
    return obj


async def _model_name(db: AsyncSession, model_id, model_type) -> str | None:
    cls = ChatModel if model_type == "chat" else ImageModel
    obj = await db.get(cls, model_id)
    return obj.name if obj else None


@router.get("")
async def list_evaluations(db: AsyncSession = Depends(get_db)) -> dict:
    evals = (
        await db.execute(select(Evaluation).order_by(Evaluation.created_at.desc()))
    ).scalars().all()
    items = []
    for e in evals:
        tc = await db.scalar(
            select(func.count()).select_from(EvaluationTask).where(
                EvaluationTask.evaluation_id == e.id
            )
        )
        mc = await db.scalar(
            select(func.count()).select_from(EvaluationModel).where(
                EvaluationModel.evaluation_id == e.id
            )
        )
        # Does this evaluation contain any open-type task? (needs blind scoring)
        open_ids = await _open_task_ids(db, e.id)
        items.append(
            EvaluationListItem(
                id=e.id, name=e.name, status=e.status,
                task_count=tc or 0, model_count=mc or 0,
                created_at=e.created_at, finished_at=e.finished_at,
                has_open_tasks=len(open_ids) > 0,
                awaiting_scoring=(e.status == "scoring"),
            ).model_dump()
        )
    return {"data": items, "message": "ok"}


@router.post("")
async def create_evaluation(
    payload: EvaluationCreate, db: AsyncSession = Depends(get_db)
) -> dict:
    # Validate referenced tasks + models exist.
    for t in payload.tasks:
        if await db.get(Task, t.task_id) is None:
            raise HTTPException(status_code=400, detail=f"任务不存在：{t.task_id}")
    for m in payload.models:
        cls = ChatModel if m.model_type == "chat" else ImageModel
        if await db.get(cls, m.model_id) is None:
            raise HTTPException(status_code=400, detail=f"模型不存在：{m.model_id}")

    evaluation = Evaluation(name=payload.name, status="pending")
    db.add(evaluation)
    await db.flush()
    for t in payload.tasks:
        db.add(EvaluationTask(
            evaluation_id=evaluation.id, task_id=t.task_id,
            score_weight=t.score_weight,
        ))
    for m in payload.models:
        db.add(EvaluationModel(
            evaluation_id=evaluation.id, model_id=m.model_id,
            model_type=m.model_type,
        ))
    await db.commit()
    await db.refresh(evaluation)
    return {"data": {"id": str(evaluation.id), "status": evaluation.status},
            "message": "ok"}


@router.get("/{eval_id}")
async def get_evaluation(
    eval_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    e = await _get_or_404(db, eval_id)
    et_rows = (await db.execute(
        select(EvaluationTask).where(EvaluationTask.evaluation_id == eval_id)
    )).scalars().all()
    em_rows = (await db.execute(
        select(EvaluationModel).where(EvaluationModel.evaluation_id == eval_id)
    )).scalars().all()
    res_rows = (await db.execute(
        select(Result).where(Result.evaluation_id == eval_id)
    )).scalars().all()

    # Unblinding gate: before the evaluation is 'done', open-type results must
    # NOT expose model_id / model_name (prevents pre-scoring reveal even via
    # direct API access). Closed-type results are unaffected.
    unblinded = e.status == "done"
    task_types: dict[uuid.UUID, str | None] = {}

    tasks = []
    for et in et_rows:
        t = await db.get(Task, et.task_id)
        task_types[et.task_id] = t.task_type if t else None
        tasks.append(EvalTaskDetail(
            task_id=et.task_id, name=t.name if t else None,
            task_type=t.task_type if t else None, score_weight=et.score_weight,
        ))
    models = []
    for em in em_rows:
        models.append(EvalModelDetail(
            model_id=em.model_id, model_type=em.model_type,
            name=await _model_name(db, em.model_id, em.model_type),
        ))
    results = []
    for r in res_rows:
        t = await db.get(Task, r.task_id)
        hide = (not unblinded) and (task_types.get(r.task_id) == "open")
        results.append(ResultItem(
            result_id=r.id, task_id=r.task_id,
            task_name=t.name if t else None,
            model_id=(None if hide else r.model_id), model_type=r.model_type,
            model_name=(None if hide else await _model_name(
                db, r.model_id, r.model_type)),
            output_text=r.output_text, ttft_ms=r.ttft_ms,
            total_duration_ms=r.total_duration_ms,
            output_char_count=r.output_char_count, char_per_sec=r.char_per_sec,
            score=r.score, auto_scored=r.auto_scored,
            status=r.status, error=r.error,
        ))
    detail = EvaluationDetail(
        id=e.id, name=e.name, status=e.status,
        created_at=e.created_at, finished_at=e.finished_at,
        tasks=tasks, models=models, results=results,
    )
    return {"data": detail.model_dump(), "message": "ok"}


@router.post("/{eval_id}/run")
async def run_evaluation(
    eval_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    e = await _get_or_404(db, eval_id)
    # Method A: one evaluation = one run. Only a pending, never-run evaluation
    # may start; already-run evaluations are immutable historical reports.
    if eval_id in eval_runner.running_tasks or e.status == "running":
        raise HTTPException(status_code=409, detail="评测已在运行中")
    if e.status != "pending":
        raise HTTPException(status_code=409, detail="该评测已运行过，请新建评测重新组卷")
    has_result = await db.scalar(
        select(func.count()).select_from(Result).where(
            Result.evaluation_id == eval_id)
    )
    if has_result:
        raise HTTPException(status_code=409, detail="该评测已有结果，请新建评测")
    e.status = "running"
    e.finished_at = None
    await db.commit()
    eval_runner.start_run(eval_id)
    return {"data": {"status": "running"}, "message": "ok"}


@router.post("/{eval_id}/cancel")
async def cancel_evaluation(
    eval_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    e = await _get_or_404(db, eval_id)
    ctx = eval_runner.running_tasks.get(eval_id)
    if e.status != "running" or ctx is None:
        raise HTTPException(status_code=409, detail="评测不在运行中，无法取消")
    ctx.cancel_event.set()
    return {"data": {"status": "cancelling"}, "message": "ok"}


@router.delete("/{eval_id}")
async def delete_evaluation(
    eval_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    e = await _get_or_404(db, eval_id)
    if eval_id in eval_runner.running_tasks or e.status == "running":
        raise HTTPException(status_code=409, detail="评测运行中，请先取消再删除")
    # Cascade delete: relationships are configured all/delete-orphan.
    await db.delete(e)
    await db.commit()
    return {"data": {"deleted": True}, "message": "ok"}


@router.get("/{eval_id}/status")
async def evaluation_status(
    eval_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    e = await _get_or_404(db, eval_id)
    total = (await db.scalar(
        select(func.count()).select_from(EvaluationTask).where(
            EvaluationTask.evaluation_id == eval_id)
    ) or 0) * (await db.scalar(
        select(func.count()).select_from(EvaluationModel).where(
            EvaluationModel.evaluation_id == eval_id)
    ) or 0)
    res_rows = (await db.execute(
        select(Result.status).where(Result.evaluation_id == eval_id)
    )).all()
    counts = {"success": 0, "failed": 0, "cancelled": 0, "skipped": 0}
    for (st,) in res_rows:
        counts[st] = counts.get(st, 0) + 1
    completed = len(res_rows)
    status = EvaluationStatus(
        status=e.status, total=total, completed=completed,
        success=counts["success"], failed=counts["failed"],
        cancelled=counts["cancelled"], skipped=counts["skipped"],
    )
    return {"data": status.model_dump(), "message": "ok"}


# ---- Blind scoring (open-type tasks) ----

async def _open_task_ids(db: AsyncSession, eval_id: uuid.UUID) -> list[uuid.UUID]:
    """Task ids in this evaluation whose task_type == 'open'."""
    et_rows = (await db.execute(
        select(EvaluationTask.task_id).where(
            EvaluationTask.evaluation_id == eval_id)
    )).scalars().all()
    open_ids = []
    for tid in et_rows:
        t = await db.get(Task, tid)
        if t is not None and t.task_type == "open":
            open_ids.append(tid)
    return open_ids


async def _task_ready(db: AsyncSession, eval_id, task_id) -> bool:
    """True when every participating model has produced a result for the task.

    Readiness means the task's outputs are all in (regardless of success/failed/
    cancelled), so the blind set is final and won't grow. Only success results
    become blind entries; a task with 0 success but all models done is still
    'ready' (nothing to score -> session completes immediately).
    """
    model_count = await db.scalar(
        select(func.count()).select_from(EvaluationModel).where(
            EvaluationModel.evaluation_id == eval_id)
    ) or 0
    result_count = await db.scalar(
        select(func.count()).select_from(Result).where(
            Result.evaluation_id == eval_id, Result.task_id == task_id)
    ) or 0
    return model_count > 0 and result_count >= model_count


async def _ensure_session(db: AsyncSession, eval_id, task_id):
    """Get the blind-scoring session for one open task, creating it only when
    the task is ready (all participating models have produced results).

    Returns None if the task is not yet ready and no session exists yet — the
    session snapshot (shuffled_order) must only be frozen once the full blind
    set is known, otherwise late-arriving outputs would be missed.
    """
    sess = (await db.execute(
        select(OpenScoringSession).where(
            OpenScoringSession.evaluation_id == eval_id,
            OpenScoringSession.task_id == task_id,
        )
    )).scalar_one_or_none()
    if sess is not None:
        return sess
    if not await _task_ready(db, eval_id, task_id):
        return None
    success_ids = (await db.execute(
        select(Result.id).where(
            Result.evaluation_id == eval_id,
            Result.task_id == task_id,
            Result.status == "success",
        )
    )).scalars().all()
    order = [str(rid) for rid in success_ids]
    random.shuffle(order)
    sess = OpenScoringSession(
        evaluation_id=eval_id, task_id=task_id,
        shuffled_order=order, current_index=0,
        completed=(len(order) == 0),
    )
    db.add(sess)
    await db.flush()
    return sess


@router.get("/{eval_id}/scoring-sessions")
async def list_scoring_sessions(
    eval_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    """List blind-scoring sessions for all open tasks.

    Sessions are created lazily only once a task is ready (all models done).
    Not-ready tasks are returned with ready=false so the UI can disable them.
    """
    await _get_or_404(db, eval_id)
    items = []
    for tid in await _open_task_ids(db, eval_id):
        t = await db.get(Task, tid)
        sess = await _ensure_session(db, eval_id, tid)
        if sess is None:
            items.append(ScoringSessionItem(
                task_id=tid, task_name=t.name if t else None,
                ready=False, total=0, scored=0, completed=False,
            ).model_dump())
        else:
            items.append(ScoringSessionItem(
                task_id=tid, task_name=t.name if t else None,
                ready=True, total=len(sess.shuffled_order),
                scored=sess.current_index, completed=sess.completed,
            ).model_dump())
    await db.commit()
    return {"data": items, "message": "ok"}


@router.get("/{eval_id}/scoring-sessions/{task_id}")
async def get_scoring_task(
    eval_id: uuid.UUID, task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Full blind view for one open task: prompt + rubric + blind entries.

    Model attribution is intentionally omitted (only blind_id + output).
    """
    await _get_or_404(db, eval_id)
    t = await db.get(Task, task_id)
    if t is None or t.task_type != "open":
        raise HTTPException(status_code=404, detail="开放型任务不存在")
    sess = await _ensure_session(db, eval_id, task_id)
    if sess is None:
        # Task not ready: outputs still generating, blind set not final yet.
        raise HTTPException(status_code=409, detail="该任务输出尚未全部生成，暂不可盲评")
    await db.commit()

    items = []
    for rid in sess.shuffled_order:
        r = await db.get(Result, uuid.UUID(rid))
        if r is None:
            continue
        items.append(BlindItem(
            blind_id=r.id, model_type=r.model_type,
            output_text=r.output_text, current_score=r.score,
        ))
    # score_weight (task full mark) comes from EvaluationTask.
    et = (await db.execute(
        select(EvaluationTask).where(
            EvaluationTask.evaluation_id == eval_id,
            EvaluationTask.task_id == task_id,
        )
    )).scalar_one_or_none()
    detail = ScoringTaskDetail(
        task_id=task_id, task_name=t.name, prompt=t.prompt,
        rubric=t.scoring_rubric, score_weight=et.score_weight if et else 1,
        current_index=sess.current_index, total=len(sess.shuffled_order),
        completed=sess.completed, items=items,
    )
    return {"data": detail.model_dump(), "message": "ok"}


@router.post("/{eval_id}/scoring-sessions/{task_id}/score")
async def submit_score(
    eval_id: uuid.UUID, task_id: uuid.UUID, payload: ScoreSubmit,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record a 1-5 tier score for one blind entry.

    Final score = tier * (score_weight / 5), rounded to int. Human-scored
    results keep auto_scored=False. When every entry of every open task is
    scored, the evaluation transitions scoring -> done.
    """
    await _get_or_404(db, eval_id)
    sess = (await db.execute(
        select(OpenScoringSession).where(
            OpenScoringSession.evaluation_id == eval_id,
            OpenScoringSession.task_id == task_id,
        )
    )).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=404, detail="盲评会话不存在")
    if str(payload.blind_id) not in sess.shuffled_order:
        raise HTTPException(status_code=400, detail="blind_id 不属于该任务盲评")

    result = await db.get(Result, payload.blind_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在")
    et = (await db.execute(
        select(EvaluationTask).where(
            EvaluationTask.evaluation_id == eval_id,
            EvaluationTask.task_id == task_id,
        )
    )).scalar_one_or_none()
    weight = et.score_weight if et else 5
    result.score = round(payload.tier * (weight / 5))
    result.auto_scored = False

    # Advance progress: count how many entries now carry a score.
    scored = 0
    for rid in sess.shuffled_order:
        r = await db.get(Result, uuid.UUID(rid))
        if r is not None and r.score is not None:
            scored += 1
    sess.current_index = scored
    sess.completed = scored >= len(sess.shuffled_order)
    await db.flush()

    # Recompute evaluation status from DB (single source of truth): flips to
    # 'done' only when generation is finished AND every open task is scored.
    evaluation = await db.get(Evaluation, eval_id)
    if evaluation.status != "cancelled":
        evaluation.status = await eval_runner.recompute_status(db, eval_id)
    await db.commit()

    return {"data": {"scored": sess.current_index,
                     "total": len(sess.shuffled_order),
                     "completed": sess.completed,
                     "eval_status": evaluation.status,
                     "score": result.score}, "message": "ok"}
