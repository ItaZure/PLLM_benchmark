"""AI-assisted benchmark task generation.

Given a dimension (name + description) and a target task type, ask the
configured generation chat model to invent one task and return it as
structured JSON, which we parse into the task-form fields.

Closed tasks are forced into a strict four-option single-choice format so
the answer-extraction regex `[A-D]` and a single-letter expected answer are
always valid.
"""
import asyncio
import json
import re

from app.services.llm_runner import run_chat_single


class GenerationError(Exception):
    """Raised when generation or parsing fails; message is user-facing."""


class _AuthError(GenerationError):
    """Non-retryable: auth/permission failure (401/403). Fail fast."""


# Retry policy for transient failures (network blips, 5xx, bad JSON).
_MAX_ATTEMPTS = 3
_RETRY_DELAY_S = 1.5


def _is_auth_error(error: str) -> bool:
    """True if the runner error string signals a non-retryable auth failure."""
    return "HTTP 401" in error or "HTTP 403" in error


_CLOSED_INSTRUCTION = """\
你是一个基准测试出题助手。请为下面这个评测维度出一道【四选一单项选择题】。

维度名称：{dim_name}
维度描述：{dim_desc}
{name_hint_block}
要求：
1. 题目必须是四选一单项选择题，选项用 A、B、C、D 标注，有且只有一个正确答案。
2. 题干要清晰、答案唯一、无歧义。
3. 在题目提示词的最后，明确要求被测模型「只回答选项字母（A/B/C/D），不要解释」。
4. 严格只输出一个 JSON 对象，不要包含任何额外文字、不要用 markdown 代码块包裹。

JSON 格式：
{{
  "name": "简短的任务名称（10 字以内）",
  "prompt": "完整的题目提示词，包含题干、四个选项、以及只回答字母的要求",
  "expected_answer": "正确选项的单个字母，只能是 A/B/C/D 之一"
}}"""

_OPEN_INSTRUCTION = """\
你是一个基准测试出题助手。请为下面这个评测维度出一道【开放型主观题】。

维度名称：{dim_name}
维度描述：{dim_desc}
{name_hint_block}
要求：
1. 题目是开放型主观题，用于考察模型的生成能力，没有唯一标准答案。
2. 题干要具体、有挑战性，符合该维度的考察目标。
3. 严格只输出一个 JSON 对象，不要包含任何额外文字、不要用 markdown 代码块包裹。

JSON 格式：
{{
  "name": "简短的任务名称（10 字以内）",
  "prompt": "完整的题目提示词"
}}"""

# Inserted when the user has already typed a task name; the model must出题
# 紧扣该名称，并沿用它作为 name 字段。
_NAME_HINT_TMPL = """\
【重要】用户已指定任务名称：{name_hint}
请严格围绕这个名称的主题出题，题目内容必须紧扣该名称所描述的方向。
输出 JSON 的 name 字段请直接沿用「{name_hint}」，不要另起名称。
"""


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model output, tolerating fences."""
    s = text.strip()
    # Strip a ```json ... ``` or ``` ... ``` fence if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    # Fall back to the first {...} block.
    if not s.startswith("{"):
        brace = re.search(r"\{.*\}", s, re.DOTALL)
        if brace:
            s = brace.group(0)
    try:
        return json.loads(s)
    except json.JSONDecodeError as exc:
        raise GenerationError(f"模型输出不是合法 JSON：{text[:200]}") from exc


async def generate_task(
    *,
    model,  # ChatModel ORM instance
    task_type: str,
    dim_name: str,
    dim_desc: str | None,
    name_hint: str | None = None,
) -> dict:
    """Return {name, prompt, [scoring_regex, expected_answer]} for the form.

    If name_hint is given, the model must出题围绕该名称，并沿用它作为 name。
    Raises GenerationError on any failure (call, parse, validation).
    """
    tmpl = _CLOSED_INSTRUCTION if task_type == "closed" else _OPEN_INSTRUCTION
    hint = (name_hint or "").strip()
    name_hint_block = _NAME_HINT_TMPL.format(name_hint=hint) if hint else ""
    prompt = tmpl.format(
        dim_name=dim_name,
        dim_desc=(dim_desc or "（无描述）").strip() or "（无描述）",
        name_hint_block=name_hint_block,
    )

    # Retry transient failures (network blips, 5xx, malformed JSON). Auth
    # errors (401/403) fail fast — retrying wastes time and tokens.
    last_err: GenerationError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return await _attempt_once(
                model=model, prompt=prompt, hint=hint, task_type=task_type
            )
        except _AuthError:
            raise  # non-retryable
        except GenerationError as exc:
            last_err = exc
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY_S)

    raise GenerationError(f"已重试 {_MAX_ATTEMPTS} 次仍失败：{last_err}")


async def _attempt_once(*, model, prompt: str, hint: str, task_type: str) -> dict:
    """One generation attempt: call model, parse, validate. Raises on failure."""
    result = await run_chat_single(
        api_base_url=model.api_base_url,
        api_key=model.api_key,
        model_name=model.model_name,
        default_params=model.default_params or {},
        system_prompt=None,
        prompt=prompt,
    )
    if result.status != "success":
        err = result.error or "未知错误"
        if _is_auth_error(err):
            raise _AuthError(f"鉴权失败，请检查生成模型的 API Key：{err}")
        raise GenerationError(f"生成模型调用失败：{err}")

    data = _extract_json(result.output_text)
    # 用户已指定名称时以其为准，忽略模型可能改写的 name。
    name = hint or (data.get("name") or "").strip()
    task_prompt = (data.get("prompt") or "").strip()
    if not name or not task_prompt:
        raise GenerationError("生成结果缺少 name 或 prompt 字段")

    out = {"name": name[:200], "prompt": task_prompt, "task_type": task_type}

    if task_type == "closed":
        answer = (data.get("expected_answer") or "").strip().upper()
        # Guard the forced four-option contract.
        if answer not in ("A", "B", "C", "D"):
            raise GenerationError(f"生成的标准答案非法（应为 A/B/C/D）：{answer!r}")
        out["scoring_regex"] = "[A-D]"
        out["expected_answer"] = answer
    return out
