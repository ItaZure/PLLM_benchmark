"""LLM invocation + metric collection + closed-task auto scoring.

Chat models are called with SSE streaming to measure TTFT accurately
(design 5.1 / 5.2). Image models are handled in phase 4b.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass

import httpx

# Chat streaming timeout. Generous read timeout for slow first token.
_CHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
# Image generation is slow (~30-40s) and may be cut off by intermediaries;
# use a large read timeout (design: >=180s).
_IMAGE_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)
# Regex to pull the image URL out of a POE markdown image link.
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
# Poll interval for the aicodewith async task API.
_POLL_INTERVAL_S = 3.0
# Safety cap on total async polling time.
_POLL_MAX_S = 300.0


@dataclass
class RunResult:
    status: str  # 'success' / 'failed' / 'cancelled'
    output_text: str = ""
    ttft_ms: float | None = None
    total_duration_ms: float | None = None
    output_char_count: int | None = None
    char_per_sec: float | None = None
    error: str | None = None


def _build_messages(system_prompt: str | None, prompt: str) -> list[dict]:
    messages: list[dict] = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return messages


async def run_chat_single(
    *,
    api_base_url: str,
    api_key: str,
    model_name: str,
    default_params: dict,
    system_prompt: str | None,
    prompt: str,
    cancel_event: asyncio.Event | None = None,
) -> RunResult:
    """Stream a chat completion and collect TTFT / duration / char metrics."""
    base = api_base_url.rstrip("/")
    payload = {
        "model": model_name,
        "messages": _build_messages(system_prompt, prompt),
        "stream": True,
        **(default_params or {}),
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    t_start = time.monotonic()
    ttft_ms: float | None = None
    chunks: list[str] = []

    def _finish(status: str, error: str | None = None) -> RunResult:
        duration_s = time.monotonic() - t_start
        text = "".join(chunks)
        if status == "success":
            char_count = len(text)
            cps = char_count / duration_s if duration_s > 0 else 0.0
            return RunResult(
                status="success",
                output_text=text,
                ttft_ms=ttft_ms,
                total_duration_ms=duration_s * 1000,
                output_char_count=char_count,
                char_per_sec=cps,
            )
        # failed / cancelled: keep partial text, leave metrics empty.
        return RunResult(status=status, output_text=text, error=error)

    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{base}/v1/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:500]
                    return _finish("failed", f"HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    if cancel_event is not None and cancel_event.is_set():
                        return _finish("cancelled", "已取消")
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content", "")
                    if delta:
                        if ttft_ms is None:
                            ttft_ms = (time.monotonic() - t_start) * 1000
                        chunks.append(delta)
    except httpx.HTTPError as exc:
        return _finish("failed", f"{type(exc).__name__}: {exc}")

    return _finish("success")


def auto_score(output_text: str, scoring_regex: str, expected_answer: str,
               score_weight: int) -> float:
    """Closed-task scoring: extract answer via regex, compare to expected.

    First match; group(1) if capture groups exist else group(0);
    strip-equality against expected_answer. Full weight or 0.
    """
    if not scoring_regex:
        return 0.0
    match = re.search(scoring_regex, output_text or "", re.DOTALL)
    if not match:
        return 0.0
    extracted = (match.group(1) if match.groups() else match.group(0)).strip()
    if extracted == (expected_answer or "").strip():
        return float(score_weight)
    return 0.0


def _image_result(status, t_start, output_text="", error=None) -> RunResult:
    """Image metrics: ttft == total duration; char metrics stay empty."""
    duration_ms = (time.monotonic() - t_start) * 1000
    if status == "success":
        return RunResult(
            status="success", output_text=output_text,
            ttft_ms=duration_ms, total_duration_ms=duration_ms,
        )
    return RunResult(status=status, output_text=output_text, error=error)


async def run_image_poe_chat(
    *, api_base_url, api_key, model_name, default_params, prompt,
    cancel_event: asyncio.Event | None = None,
) -> RunResult:
    """POE synchronous image mode: chat/completions, stream=False, parse markdown."""
    base = api_base_url.rstrip("/")
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        **(default_params or {}),
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    t_start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_IMAGE_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/v1/chat/completions", json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        return _image_result("failed", t_start, error=f"{type(exc).__name__}: {exc}")
    if resp.status_code >= 400:
        return _image_result("failed", t_start,
                             error=f"HTTP {resp.status_code}: {resp.text[:400]}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError, ValueError):
        return _image_result("failed", t_start,
                             error=f"响应结构异常：{resp.text[:400]}")
    match = _MD_IMAGE_RE.search(content or "")
    if not match:
        return _image_result("failed", t_start,
                             error=f"未提取到图片 URL：{content[:400]}")
    return _image_result("success", t_start, output_text=match.group(1))


async def run_image_aicodewith_async(
    *, api_base_url, api_key, model_name, default_params, prompt,
    cancel_event: asyncio.Event | None = None,
) -> RunResult:
    """aicodewith async mode: submit task, poll /v1/tasks/{id} until done."""
    base = api_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    submit_body = {"model": model_name, "prompt": prompt, "n": 1,
                   **(default_params or {})}
    t_start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_IMAGE_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/v1/images/generations", json=submit_body, headers=headers
            )
            if resp.status_code >= 400:
                return _image_result("failed", t_start,
                                     error=f"提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
            task_id = resp.json().get("id")
            if not task_id:
                return _image_result("failed", t_start,
                                     error=f"未拿到 task id：{resp.text[:300]}")
            # Poll until completed / failed / timeout / cancelled.
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    return _image_result("cancelled", t_start, error="已取消")
                if (time.monotonic() - t_start) > _POLL_MAX_S:
                    return _image_result("failed", t_start, error="轮询超时")
                await asyncio.sleep(_POLL_INTERVAL_S)
                pr = await client.get(f"{base}/v1/tasks/{task_id}", headers=headers)
                if pr.status_code >= 400:
                    return _image_result("failed", t_start,
                                         error=f"轮询失败 HTTP {pr.status_code}: {pr.text[:300]}")
                data = pr.json()
                status = data.get("status")
                if status in ("completed", "succeeded", "success"):
                    url = _extract_async_url(data)
                    if not url:
                        return _image_result("failed", t_start,
                                             error=f"完成但无 URL：{pr.text[:300]}")
                    return _image_result("success", t_start, output_text=url)
                if status in ("failed", "error", "cancelled"):
                    return _image_result("failed", t_start,
                                         error=f"任务 {status}：{pr.text[:300]}")
    except httpx.HTTPError as exc:
        return _image_result("failed", t_start, error=f"{type(exc).__name__}: {exc}")


def _extract_async_url(data: dict) -> str | None:
    rd = data.get("result_data")
    if isinstance(rd, list) and rd:
        first = rd[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]
        if isinstance(first, str):
            return first
    results = data.get("results")
    if isinstance(results, list) and results:
        if isinstance(results[0], str):
            return results[0]
        if isinstance(results[0], dict) and results[0].get("url"):
            return results[0]["url"]
    return None
