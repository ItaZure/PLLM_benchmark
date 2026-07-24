"""Availability testing for OpenAI-compatible model endpoints.

Two distinct strategies (kept separate to avoid semantic confusion):

- Chat models (`test_chat_model`): GET /v1/models; on 404 fall back to a
  minimal chat completion request.
- Image models (`test_image_model`): GET /v1/models only. Image generation on
  POE-style aggregators goes through /v1/chat/completions and is slow + costly,
  so we never probe generation for a connectivity check.

Failures are classified into distinct, human-readable reasons.
"""
import httpx

# Keep tests snappy: don't let a dead endpoint hang the UI.
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _normalize_base(api_base_url: str) -> str:
    """Strip trailing slash so we can join /v1/... cleanly."""
    return api_base_url.rstrip("/")


def _classify_status(status_code: int) -> str | None:
    """Map an HTTP status to a failure reason, or None if it's acceptable."""
    if status_code < 400:
        return None
    if status_code in (401, 403):
        return f"{status_code} 鉴权失败：API key 无效或无权限"
    if status_code == 429:
        return "429 触发限流（rate limit）"
    if 500 <= status_code < 600:
        return f"{status_code} 服务端错误"
    return f"HTTP {status_code}"


async def _try_chat_fallback(
    client: httpx.AsyncClient, base: str, api_key: str, model_name: str
) -> tuple[bool, str | None]:
    """Minimal chat completion when /v1/models is unavailable (404)."""
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    try:
        resp = await client.post(url, json=payload, headers=_auth_headers(api_key))
    except httpx.HTTPError as exc:  # noqa: BLE001
        return False, _classify_transport_error(exc)
    reason = _classify_status(resp.status_code)
    if reason is None:
        return True, None
    return False, reason


def _classify_transport_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return "连接超时：无法在限定时间内建立连接"
    if isinstance(exc, httpx.ReadTimeout):
        return "读取超时：服务端响应过慢"
    if isinstance(exc, httpx.ConnectError):
        return "连接失败：地址不可达或端口未开放"
    if isinstance(exc, httpx.TimeoutException):
        return "请求超时"
    return f"网络错误：{type(exc).__name__}"


async def _get_models(
    client: httpx.AsyncClient, base: str, api_key: str
) -> tuple[bool, str | None, int | None]:
    """GET /v1/models. Return (ok, error, status_code).

    ok is True when status < 400. status_code is None on transport error.
    """
    try:
        resp = await client.get(f"{base}/v1/models", headers=_auth_headers(api_key))
    except httpx.HTTPError as exc:  # noqa: BLE001
        return False, _classify_transport_error(exc), None
    reason = _classify_status(resp.status_code)
    return (reason is None), reason, resp.status_code


async def test_chat_model(
    api_base_url: str, api_key: str, model_name: str
) -> tuple[bool, str | None]:
    """Chat model availability.

    GET /v1/models; if 404, fall back to a minimal chat completion request.
    Returns (available, error_reason).
    """
    base = _normalize_base(api_base_url)
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        ok, error, status = await _get_models(client, base, api_key)
        if status == 404:
            # Endpoint doesn't expose /v1/models; probe with a tiny chat request.
            return await _try_chat_fallback(client, base, api_key, model_name)
        return ok, error


async def test_image_model(
    api_base_url: str, api_key: str, model_name: str
) -> tuple[bool, str | None]:
    """Image model availability.

    Image generation on POE-style aggregators runs through
    /v1/chat/completions (slow, costs money), so we do NOT probe generation.
    Connectivity/auth is verified with GET /v1/models only: <400 => available.
    Returns (available, error_reason).
    """
    base = _normalize_base(api_base_url)
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        ok, error, _status = await _get_models(client, base, api_key)
        return ok, error
