"""WorkBuddy 池调度：credit-priority 轮询 + 双后台协程（token 刷新 / 积分刷新）+ 熔断。"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

from . import wb_client, wb_store

logger = logging.getLogger("wb-polling")

REFRESH_MARGIN_MIN = float(os.environ.get("WB_REFRESH_MARGIN_MIN", "30"))
CREDITS_INTERVAL_MIN = float(os.environ.get("WB_CREDITS_REFRESH_MIN", "10"))
TOKEN_SCAN_INTERVAL_S = float(os.environ.get("WB_TOKEN_SCAN_INTERVAL_S", "300"))

_ROTATION_CURSOR = 0
_TASKS: list[asyncio.Task] = []


def _eligible(rec: dict[str, Any]) -> bool:
    if not rec.get("model_enabled", True):
        return False
    if rec.get("needs_relogin"):
        return False
    du = int(rec.get("disabled_until") or 0)
    if du and du > time.time() * 1000:
        return False
    rexp = int(rec.get("refresh_expires_at") or 0)
    if rexp and rexp <= time.time() * 1000:
        return False
    at = str(rec.get("access_token") or "")
    if not at or len(at) < 20:
        return False
    return True


def _usable_now(rec: dict[str, Any]) -> bool:
    """eligible 且未被本轮请求内临时失败标记（由 handle 层负责排除）。"""
    return _eligible(rec)


def pick_account(exclude_uids: Optional[set[str]] = None) -> Optional[dict[str, Any]]:
    """credit-priority：剩余积分降序（未知的排最后），同分按轮询游标。"""
    global _ROTATION_CURSOR
    exclude = exclude_uids or set()
    cfg = wb_store.polling_cfg()
    if not cfg.get("enabled", True):
        return None
    pool = [r for r in wb_store.accounts() if _usable_now(r) and str(r.get("uid")) not in exclude]
    if not pool:
        return None
    if cfg.get("mode") == "credit-priority":
        def key(rec: dict[str, Any]):
            qc = rec.get("quota_cache") or {}
            rem = qc.get("remaining")
            # None（未知）排最后但不挡轮询；unlimited 视为最高优先
            if qc.get("unlimited"):
                return (0, 0, str(rec.get("uid")))
            if rem is None:
                return (2, 0, str(rec.get("uid")))
            return (1, -int(rem), str(rec.get("uid")))
        pool.sort(key=key)
    rec = pool[_ROTATION_CURSOR % len(pool)]
    _ROTATION_CURSOR = (_ROTATION_CURSOR + 1) % max(len(pool), 1)
    return rec


async def _token_refresher_loop() -> None:
    while True:
        try:
            now = time.time() * 1000
            margin_ms = REFRESH_MARGIN_MIN * 60 * 1000
            for rec in wb_store.accounts():
                if rec.get("needs_relogin") or not rec.get("model_enabled", True):
                    continue
                exp = int(rec.get("expires_at") or 0)
                if exp and exp - margin_ms <= now:
                    try:
                        await wb_client.refresh_token(rec)
                    except wb_client.WbAccountDead as exc:
                        logger.warning("wb-polling: refresh dead uid=%s (%s)", rec.get("uid"), exc)
                    except Exception as exc:
                        logger.error("wb-polling: refresh error uid=%s (%s)", rec.get("uid"), exc)
        except Exception as exc:
            logger.error("wb-polling: token loop error %s", exc)
        await asyncio.sleep(TOKEN_SCAN_INTERVAL_S)


async def _credits_refresher_loop() -> None:
    while True:
        try:
            for rec in wb_store.accounts():
                if not rec.get("model_enabled", True) or rec.get("needs_relogin"):
                    continue
                try:
                    quota = await wb_client.fetch_credits(rec)
                    rec["quota_cache"] = quota
                    if isinstance(quota.get("remaining"), (int, float)):
                        if quota["remaining"] <= 0 and rec.get("model_enabled", True):
                            rec["model_enabled"] = False
                            rec["last_error"] = "quota_empty"
                            logger.info("wb-polling: uid=%s quota empty -> disabled", rec.get("uid"))
                        elif quota["remaining"] > 0 and rec.get("last_error") == "quota_empty":
                            rec["model_enabled"] = True
                            rec["last_error"] = None
                            logger.info("wb-polling: uid=%s quota restored -> enabled", rec.get("uid"))
                    wb_store.save()
                except wb_client.WbAccountDead:
                    logger.warning("wb-polling: credits dead uid=%s", rec.get("uid"))
                except Exception as exc:
                    logger.error("wb-polling: credits error uid=%s (%s)", rec.get("uid"), exc)
                await asyncio.sleep(1.5)  # 账号间节流
        except Exception as exc:
            logger.error("wb-polling: credits loop error %s", exc)
        await asyncio.sleep(CREDITS_INTERVAL_MIN * 60)


def start_background() -> None:
    if _TASKS:
        return
    _TASKS.append(asyncio.create_task(_token_refresher_loop()))
    _TASKS.append(asyncio.create_task(_credits_refresher_loop()))
    logger.info("wb-polling: background loops started (%d accounts)", len(wb_store.accounts()))


async def stop_background() -> None:
    for t in _TASKS:
        t.cancel()
    for t in _TASKS:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    _TASKS.clear()
