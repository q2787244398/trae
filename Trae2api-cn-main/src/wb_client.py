"""WorkBuddy 上游客户端：网关头构造 / token 刷新 / chat 流式直透 / 401 重放。

上游（P0 实测 + WorkBuddy 5.8.3 app.asar 取证）:
  推理  POST https://copilot.tencent.com/v2/chat/completions   (OpenAI 格式)
  刷新  POST https://www.codebuddy.cn/v2/plugin/auth/token/refresh  (X-Refresh-Token 头)
  积分  GET  https://www.codebuddy.cn/v2/billing/meter/checkin-activity-status 等
  登录  POST https://www.codebuddy.cn/v2/plugin/auth/state?platform=workbuddy
        GET  https://www.codebuddy.cn/v2/plugin/auth/token?state=...
        GET  https://www.codebuddy.cn/v2/plugin/login/account?state=...
错误码: 12153 = refresh token 失效（invalid_grant）→ needs_relogin
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
import uuid
from typing import Any, AsyncIterator, Optional

import httpx

from . import wb_store

logger = logging.getLogger("wb-client")

CHAT_URL = os.environ.get("WB_UPSTREAM_CHAT", "https://copilot.tencent.com/v2/chat/completions")
PLUGIN_BASE = os.environ.get("WB_PLUGIN_BASE", "https://www.codebuddy.cn/v2/plugin")
METER_BASE = os.environ.get("WB_METER_BASE", "https://www.codebuddy.cn/v2/billing/meter")
IDE_VERSION = os.environ.get("WB_IDE_VERSION", "5.8.3")
MODEL_PREFIX = os.environ.get("WB_MODEL_PREFIX", "wb-")
CONNECT_TIMEOUT = float(os.environ.get("WB_CONNECT_TIMEOUT", "10"))
READ_TIMEOUT = float(os.environ.get("WB_READ_TIMEOUT", "300"))

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"

FIXED_HEADERS = {
    "X-Agent-Intent": "craft",
    "X-Agent-Purpose": "conversation",
    "x-codebuddy-request": "1",
    "X-IDE-Type": "WorkBuddy",
    "X-IDE-Name": "WorkBuddy",
    "X-IDE-Version": IDE_VERSION,
    "X-Private-Data": "true",
    "X-Product": "SaaS",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Accept-Encoding": "identity",
    "User-Agent": UA,
}


class WbError(Exception):
    """对外 OpenAI 错误直映射。code: upstream_error/token_refresh_failed/pool_unavailable"""

    def __init__(self, message: str, status: int = 502, err_type: str = "api_error", code: str = ""):
        super().__init__(message)
        self.status = int(status)
        self.err_type = err_type
        self.code = code or err_type


class WbAccountDead(Exception):
    """账号级失败（401 刷新失败 / 12153 / 403 风控），上层应换号重试。"""


def _uuid() -> str:
    return str(uuid.uuid4())


def _trace_headers() -> dict[str, str]:
    tp = secrets.token_hex(16)
    span = secrets.token_hex(8)
    return {"traceparent": f"00-{tp}-{span}-01", "b3": f"{tp}-{span}-1"}


def build_headers(acct: dict[str, Any], *, with_auth: bool = True) -> dict[str, str]:
    h = dict(FIXED_HEADERS)
    h.update({
        "X-Conversation-ID": _uuid(),
        "X-Conversation-Request-ID": _uuid(),
        "X-Conversation-Message-ID": _uuid(),
        "X-Request-ID": _uuid(),
        "acp-connection-id": _uuid(),
    })
    h.update(_trace_headers())
    if with_auth:
        h["Authorization"] = f"Bearer {acct.get('access_token', '')}"
    return h


def _expired(acct: dict[str, Any], margin_ms: int) -> bool:
    return int(acct.get("expires_at") or 0) - margin_ms <= int(time.time() * 1000)


async def refresh_token(acct: dict[str, Any]) -> bool:
    """刷新单个账号 token；成功回写存储并返回 True。

    失败语义：12153 / 400（refresh 失效）→ needs_relogin=True；网络错误原样抛出由调用方计数。
    """
    rt = str(acct.get("refresh_token") or "")
    if not rt or acct.get("needs_relogin"):
        raise WbAccountDead("missing refresh token or needs_relogin")
    headers = build_headers(acct, with_auth=False)
    headers["Authorization"] = f"Bearer {acct.get('access_token', '')}"
    headers["X-Refresh-Token"] = rt
    headers["X-Auth-Refresh-Source"] = "plugin"
    async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT + 20) as client:
        resp = await client.post(f"{PLUGIN_BASE}/auth/token/refresh", headers=headers, json={})
    try:
        body = resp.json()
    except Exception:
        body = {}
    code = body.get("code")
    data = body.get("data") or {}
    new_at = str(data.get("accessToken") or data.get("access_token") or "")
    new_rt = str(data.get("refreshToken") or data.get("refresh_token") or "")
    if resp.status_code == 200 and code == 0 and new_at:
        acct["access_token"] = new_at
        if new_rt:
            acct["refresh_token"] = new_rt
        exp = data.get("expiresAt") or data.get("expires_at")
        acct["expires_at"] = int(exp) if exp else int(time.time() * 1000) + 2419200 * 1000
        acct["last_refresh_at"] = int(time.time() * 1000)
        acct["consecutive_failures"] = 0
        acct["disabled_until"] = 0
        acct["last_error"] = None
        wb_store.save()
        logger.info("wb-client: refreshed token uid=%s", acct.get("uid"))
        return True
    if code == 12153 or resp.status_code in (400, 401):
        acct["needs_relogin"] = True
        acct["last_error"] = f"refresh_failed code={code} http={resp.status_code}"
        wb_store.save()
        logger.warning("wb-client: refresh failed uid=%s code=%s -> needs_relogin", acct.get("uid"), code)
        raise WbAccountDead(f"refresh failed code={code}")
    acct["last_error"] = f"refresh_http_{resp.status_code}"
    wb_store.save()
    raise WbAccountDead(f"refresh http {resp.status_code}")


async def ensure_fresh(acct: dict[str, Any], margin_min: float = 30) -> None:
    margin_ms = int(margin_min * 60 * 1000)
    if not _expired(acct, margin_ms):
        return
    await refresh_token(acct)


async def chat_stream(acct: dict[str, Any], payload: dict[str, Any]) -> AsyncIterator[bytes]:
    """直透 /v2/chat/completions（SSE 逐块转发）。401 自动刷新并重放一次。"""
    body = dict(payload)
    model = str(body.get("model") or "")
    if model.startswith(MODEL_PREFIX):
        body["model"] = model[len(MODEL_PREFIX):]
    replayed = False
    for attempt in (0, 1):
        headers = build_headers(acct)
        timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
        client = httpx.AsyncClient(timeout=timeout)
        try:
            async with client.stream("POST", CHAT_URL, headers=headers, json=body) as resp:
                if resp.status_code == 401 and attempt == 0 and not replayed:
                    replayed = True
                    await resp.aread()
                    await client.aclose()
                    await refresh_token(acct)
                    continue
                if resp.status_code == 401:
                    raise WbAccountDead("upstream 401 after replay")
                if resp.status_code == 403:
                    raise WbAccountDead("upstream 403 (possible risk control)")
                if resp.status_code == 429:
                    # 读一次 body 供上层退避
                    raw = await resp.aread()
                    raise WbRateLimited(raw.decode("utf-8", "replace")[:200])
                if resp.status_code != 200:
                    raw = (await resp.aread()).decode("utf-8", "replace")
                    raise WbError(f"wb upstream {resp.status_code}: {raw[:300]}",
                                  status=502, err_type="api_error", code="wb_upstream_error")
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
                return
        finally:
            try:
                await client.aclose()
            except Exception:
                pass


class WbRateLimited(Exception):
    def __init__(self, snippet: str = ""):
        super().__init__("wb upstream 429")
        self.snippet = snippet


def _mark_failure(uid: str, reason: str) -> None:
    rec = wb_store.get(uid)
    if not rec:
        return
    rec["consecutive_failures"] = int(rec.get("consecutive_failures") or 0) + 1
    rec["last_error"] = reason
    if rec["consecutive_failures"] >= 5:
        rec["disabled_until"] = int(time.time() * 1000) + 30 * 60 * 1000
        rec["consecutive_failures"] = 0
        logger.warning("wb-client: account %s circuit-broken for 30min (%s)", uid, reason)
    wb_store.save()


def mark_success(uid: str) -> None:
    rec = wb_store.get(uid)
    if rec and (rec.get("consecutive_failures") or rec.get("disabled_until") or rec.get("last_error")):
        rec["consecutive_failures"] = 0
        rec["disabled_until"] = 0
        rec["last_error"] = None
        wb_store.save()


async def fetch_credits(acct: dict[str, Any]) -> dict[str, Any]:
    """拉取账号状态/积分信号（P0 实测：
    - POST /v2/billing/meter/checkin-activity-status → 200（签到状态，含 daily_credit）
    - POST /billing/meter/get-user-resource-summary → 403/10085（web 令牌域受限，暂不用）
    返回 quota_cache 形态；余额未知时 remaining=None，轮询器自动退化为轮转。"""
    headers = build_headers(acct)
    headers["X-Client-Platform"] = "web"
    origin = PLUGIN_BASE.rsplit("/v2", 1)[0]
    headers["Origin"] = origin
    headers["Referer"] = f"{origin}/profile/plans-usage"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{METER_BASE}/checkin-activity-status", headers=headers, json={})
    if resp.status_code == 401:
        raise WbAccountDead("credits 401")
    try:
        body = resp.json()
    except Exception:
        raise WbError(f"credits bad json http={resp.status_code}", status=502)
    if body.get("code") not in (0, None):
        raise WbError(f"credits code={body.get('code')}", status=502)
    data = body.get("data") or {}
    return {
        "remaining": None,           # 余额端点待官方域开放；保持 None → 轮转模式
        "total": None,
        "expire_at": data.get("expireAt"),
        "checked_at": int(time.time() * 1000),
        "checkin": {"active": data.get("active"),
                    "today_checked_in": data.get("today_checked_in"),
                    "streak_days": data.get("streak_days"),
                    "daily_credit": data.get("daily_credit")},
    }


def login_start() -> dict[str, Any]:
    """发起 OAuth 登录：返回 {state, auth_url}。"""
    import httpx as _hx
    r = _hx.post(f"{PLUGIN_BASE}/auth/state?platform=workbuddy",
                 headers={"User-Agent": UA}, json={}, timeout=15)
    body = r.json()
    data = body.get("data") or {}
    state = str(data.get("state") or "")
    if not state:
        raise WbError(f"auth/state no state: {str(body)[:200]}", status=502)
    return {"state": state, "auth_url": str(data.get("authUrl") or "")}


def login_poll(state: str) -> dict[str, Any]:
    """轮询一次 auth/token。返回 {status: pending|ok|error, ...}。"""
    import httpx as _hx
    r = _hx.get(f"{PLUGIN_BASE}/auth/token?state={state}",
                headers={"User-Agent": UA}, timeout=15)
    body = r.json()
    code = body.get("code")
    data = body.get("data") or {}
    if code == 0 and isinstance(data.get("accessToken"), str):
        acct = {}
        try:
            ra = _hx.get(f"{PLUGIN_BASE}/login/account?state={state}",
                         headers={"User-Agent": UA}, timeout=15)
            acct = (ra.json().get("data") or {})
        except Exception:
            pass
        return {"status": "ok", "token": data, "account": acct}
    if code == 11217:
        return {"status": "pending"}
    return {"status": "error", "code": code, "msg": str(body.get("msg"))[:160]}
