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

# ---- variant（cn 国内版 / ai 国际版）----
# ai 端点取自 workbuddy-switch variant.rs；chat 网关为同构推测，待 P0' 实测
_VARIANT_BASES: dict[str, dict[str, str]] = {
    "cn": {
        "chat": CHAT_URL,
        "plugin": PLUGIN_BASE,
        "meter": METER_BASE,
        "platform": "workbuddy",
        "label": "OAuth 扫码登录",
    },
    "ai": {
        "chat": os.environ.get("WB_UPSTREAM_CHAT_AI", "https://www.codebuddy.ai/v2/chat/completions"),
        "plugin": os.environ.get("WB_PLUGIN_BASE_AI", "https://www.codebuddy.ai/v2/plugin"),
        "meter": os.environ.get("WB_METER_BASE_AI", "https://www.codebuddy.ai/v2/billing/meter"),
        "platform": "workbuddy-ai",
        "label": "OAuth Web 登录",
    },
}
_LOGIN_STATES: dict[str, str] = {}  # state -> variant


def normalize_variant(v: Any) -> str:
    s = str(v or "cn").strip().lower()
    return "ai" if s in ("ai", "intl", "global") else "cn"


def _bases(acct: dict[str, Any] | None = None, variant: str = "cn") -> dict[str, str]:
    if acct is not None:
        return _VARIANT_BASES[normalize_variant(acct.get("variant"))]
    return _VARIANT_BASES[normalize_variant(variant)]
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
        resp = await client.post(f"{_bases(acct)['plugin']}/auth/token/refresh", headers=headers, json={})
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
            async with client.stream("POST", _bases(acct)["chat"], headers=headers, json=body) as resp:
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


_WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")


def _resource_base(acct: dict[str, Any]) -> tuple[str, str]:
    """余额端点基址与 X-Domain：须与 token 签发域一致（wb-switch api_base_for 同款规则）。"""
    domain = str(acct.get("domain") or "").strip().lower()
    if domain.endswith("workbuddy.ai"):
        return "https://www.workbuddy.ai", "www.workbuddy.ai"
    return "https://www.codebuddy.cn", "www.codebuddy.cn"


def _xuid(acct: dict[str, Any]) -> str:
    uid = str(acct.get("uid") or "").strip()
    if uid:
        return uid
    claims = _jwt_claims(str(acct.get("access_token") or ""))
    return str(claims.get("uid") or claims.get("sub") or "")


async def fetch_credits(acct: dict[str, Any]) -> dict[str, Any]:
    """拉取积分余额（get-user-resource，2026-10-20 实测 200）+ 签到状态。

    关键配方（缺一即 403/10085）：Chrome UA + X-Client-Platform: web +
    X-User-Id + X-Domain（与 token 签发域一致）+ Origin/Referer。
    返回 quota_cache 形态；余额解析失败时 remaining=None（轮询退化为轮转）。
    """
    headers = build_headers(acct)
    headers["X-Client-Platform"] = "web"
    headers["User-Agent"] = _WEB_UA
    base, xdom = _resource_base(acct)
    headers["X-Domain"] = xdom
    headers["X-User-Id"] = _xuid(acct)
    headers["Origin"] = base
    headers["Referer"] = base + "/profile/plans-usage"

    remaining: Any = None
    total: Any = None
    packages: list[dict[str, Any]] = []
    earliest: Any = None
    ck_body: dict[str, Any] = {}
    dead = False
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.post(base + "/v2/billing/meter/get-user-resource",
                                     headers=headers, json={})
            if resp.status_code == 401:
                dead = True
            elif resp.status_code == 200:
                body = resp.json()
                d0 = (((body.get("data") or {}).get("Response") or {}).get("Data") or {})
                accts = d0.get("Accounts") or []
                total = int(d0.get("TotalDosage") or 0)
                remain_sum = 0
                for a in accts:
                    if not isinstance(a, dict):
                        continue
                    try:
                        remain_sum += int(a.get("CapacityRemain") or 0)
                    except (TypeError, ValueError):
                        pass
                    packages.append({
                        "name": str(a.get("PackageName") or "未命名资源包"),
                        "remain": a.get("CapacityRemain"),
                        "size": a.get("CapacitySize"),
                        "used": a.get("CapacityUsed"),
                        "unit": str(a.get("CapacityUnit") or "credits"),
                        "expire": str(a.get("CycleEndTime") or ""),
                        "status": a.get("Status"),
                    })
                    end = str(a.get("CycleEndTime") or "")
                    if end and (earliest is None or end < earliest):
                        earliest = end
                remaining = remain_sum
            else:
                logger.warning("wb-client: resource http=%s uid=%s",
                               resp.status_code, acct.get("uid"))
        except Exception as exc:
            logger.warning("wb-client: resource error uid=%s (%s)", acct.get("uid"), exc)
        try:
            resp2 = await client.post(_bases(acct)["meter"] + "/checkin-activity-status",
                                      headers=headers, json={})
            if resp2.status_code == 401:
                dead = True
            elif resp2.status_code == 200:
                ck_body = resp2.json()
        except Exception as exc:
            logger.warning("wb-client: checkin-status error uid=%s (%s)", acct.get("uid"), exc)
    if dead:
        raise WbAccountDead("credits 401")
    ck_data = ck_body.get("data") or {}
    return {
        "remaining": remaining,
        "total": total,
        "packages": packages[:12],
        "expire_at": earliest,
        "checked_at": int(time.time() * 1000),
        "checkin": {"active": ck_data.get("active"),
                    "today_checked_in": ck_data.get("today_checked_in"),
                    "streak_days": ck_data.get("streak_days"),
                    "daily_credit": ck_data.get("daily_credit")},
    }


def login_start(variant: str = "cn") -> dict[str, Any]:
    """发起 OAuth 登录：返回 {state, auth_url, variant, label}。"""
    import httpx as _hx
    v = normalize_variant(variant)
    base = _VARIANT_BASES[v]
    r = _hx.post(f"{base['plugin']}/auth/state?platform={base['platform']}",
                 headers={"User-Agent": UA}, json={}, timeout=15)
    body = r.json()
    data = body.get("data") or {}
    state = str(data.get("state") or "")
    if not state:
        raise WbError(f"auth/state no state: {str(body)[:200]}", status=502)
    _LOGIN_STATES[state] = v
    return {"state": state, "auth_url": str(data.get("authUrl") or data.get("auth_url") or ""),
            "variant": v, "label": base["label"]}


def _jwt_claims(token_str: str) -> dict[str, Any]:
    """解析 JWT payload（不验签，仅取声明）。"""
    import base64 as _b64
    import json as _json
    try:
        p = token_str.split(".")[1]
        p += "=" * (-len(p) % 4)
        return _json.loads(_b64.urlsafe_b64decode(p))
    except Exception:
        return {}


def login_poll(state: str) -> dict[str, Any]:
    """轮询一次 auth/token。返回 {status: pending|ok|error, ...}。

    uid 优先取 /login/account，缺失时回退到 access token (JWT) 的 uid/sub 声明
    —— 实测 /login/account 可能不返回 uid（2026-10-20 用户扫码导入失败定位）。
    variant 由 login_start 记录（_LOGIN_STATES），导入时随账号写入账号库。
    """
    import httpx as _hx
    variant = _LOGIN_STATES.get(state, "cn")
    base = _VARIANT_BASES[variant]
    r = _hx.get(f"{base['plugin']}/auth/token?state={state}",
                headers={"User-Agent": UA}, timeout=15)
    body = r.json()
    code = body.get("code")
    data = body.get("data") or {}
    if code == 0 and isinstance(data.get("accessToken"), str):
        acct = {}
        try:
            ra = _hx.get(f"{base['plugin']}/login/account?state={state}",
                         headers={"User-Agent": UA}, timeout=15)
            acct = dict(ra.json().get("data") or {})
        except Exception:
            acct = {}
        claims = _jwt_claims(data["accessToken"])
        if not acct.get("uid"):
            uid = claims.get("uid") or claims.get("sub")
            if uid:
                acct["uid"] = str(uid)
        if not acct.get("nickname"):
            nick = claims.get("nickname") or claims.get("preferred_username")
            if nick:
                acct["nickname"] = str(nick)
        acct.setdefault("uin", str(claims.get("preferred_username") or ""))
        if variant == "ai":
            acct.setdefault("domain", "www.workbuddy.ai")
        else:
            acct.setdefault("domain", "www.workbuddy.cn")
        acct["variant"] = variant
        return {"status": "ok", "token": data, "account": acct}
    if code == 11217:
        return {"status": "pending"}
    return {"status": "error", "code": code, "msg": str(body.get("msg"))[:160]}


async def checkin(acct: dict[str, Any]) -> dict[str, Any]:
    """执行每日签到（POST /v2/billing/meter/daily-checkin）。

    参考 workbuddy-switch checkin.rs：服务端返回"已签到"按成功处理。
    返回 {ok, already, code, msg, credit}。
    """
    headers = build_headers(acct)
    headers["X-Client-Platform"] = "web"
    headers["User-Agent"] = _WEB_UA
    headers["X-Domain"] = _resource_base(acct)[1]
    headers["X-User-Id"] = _xuid(acct)
    origin = _bases(acct)["plugin"].rsplit("/v2", 1)[0]
    headers["Origin"] = origin
    headers["Referer"] = f"{origin}/profile/plans-usage"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{_bases(acct)['meter']}/daily-checkin",
                                 headers=headers, json={})
    if resp.status_code == 401:
        raise WbAccountDead("checkin 401")
    try:
        body = resp.json()
    except Exception:
        return {"ok": False, "already": False, "code": resp.status_code,
                "msg": f"bad json http={resp.status_code}", "credit": None}
    code = body.get("code")
    msg = str(body.get("msg") or body.get("message") or "")
    data = body.get("data") or {}
    # 0 = 成功；常见"已签到"提示语也按成功处理
    already = ("已签到" in msg) or ("already" in msg.lower())
    ok = (code in (0, None)) or already
    credit = None
    for key in ("credit", "addCredit", "rewardCredit", "dailyCredit"):
        if isinstance(data, dict) and data.get(key) is not None:
            credit = data.get(key)
            break
    if not ok and msg:
        return {"ok": False, "already": False, "code": code, "msg": msg[:120], "credit": None}
    return {"ok": True, "already": already, "code": code, "msg": msg[:120], "credit": credit}
