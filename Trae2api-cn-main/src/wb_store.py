"""WorkBuddy 账号库：JSON 持久化 + 读写锁 + 导入。

存储文件: APP_DIR/data/workbuddy_accounts.json（与 Trae 的 accounts.json 完全隔离）
线程模型: 模块级 RLock 串行化所有读改写；写入采用 tmp+rename 原子替换。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("wb-store")

APP_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_PATH = APP_DIR / "data" / "workbuddy_accounts.json"
USAGE_PATH = APP_DIR / "data" / "wb_usage_records.json"
USAGE_MAX = 5000

_LOCK = threading.RLock()
_CACHE: Optional[dict[str, Any]] = None

DEFAULT_POLLING = {"enabled": True, "mode": "credit-priority"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _empty() -> dict[str, Any]:
    return {"version": 1, "updated_at": _now_ms(), "polling": dict(DEFAULT_POLLING), "accounts": []}


def _ensure_defaults(rec: dict[str, Any]) -> dict[str, Any]:
    """老记录兼容升级：补 variant / auto_checkin 等新字段。"""
    rec.setdefault("variant", "cn")
    rec.setdefault("auto_checkin", True)
    return rec


def load(force: bool = False) -> dict[str, Any]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None and not force:
            return _CACHE
        if ACCOUNTS_PATH.exists():
            try:
                data = json.loads(ACCOUNTS_PATH.read_text("utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
                    raise ValueError("bad shape")
            except Exception as exc:  # 损坏自愈为空池
                logger.error("wb-store: load failed (%s), starting empty pool", exc)
                data = _empty()
        else:
            data = _empty()
        data.setdefault("polling", dict(DEFAULT_POLLING))
        data.setdefault("accounts", [])
        data.setdefault("version", 1)
        for rec in data["accounts"]:
            _ensure_defaults(rec)
        _CACHE = data
        return data


def save() -> None:
    with _LOCK:
        data = load()
        data["updated_at"] = _now_ms()
        ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = ACCOUNTS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, ACCOUNTS_PATH)


def accounts() -> list[dict[str, Any]]:
    return load()["accounts"]


def get(uid: str) -> Optional[dict[str, Any]]:
    uid = str(uid or "")
    for rec in accounts():
        if str(rec.get("uid")) == uid:
            return rec
    return None


def upsert(record: dict[str, Any]) -> dict[str, Any]:
    uid = str(record.get("uid") or "").strip()
    if not uid:
        raise ValueError("uid required")
    with _LOCK:
        data = load()
        for i, rec in enumerate(data["accounts"]):
            if str(rec.get("uid")) == uid:
                merged = {**rec, **record, "uid": uid}
                data["accounts"][i] = merged
                save()
                return merged
        data["accounts"].append({**record, "uid": uid})
        save()
        return record


def remove(uid: str) -> bool:
    with _LOCK:
        data = load()
        before = len(data["accounts"])
        data["accounts"] = [r for r in data["accounts"] if str(r.get("uid")) != str(uid)]
        changed = len(data["accounts"]) != before
        if changed:
            save()
        return changed


def set_enabled(uid: str, enabled: bool) -> bool:
    rec = get(uid)
    if not rec:
        return False
    rec["model_enabled"] = bool(enabled)
    save()
    return True


def polling_cfg() -> dict[str, Any]:
    cfg = dict(load().get("polling") or DEFAULT_POLLING)
    cfg.setdefault("enabled", True)
    cfg.setdefault("mode", "credit-priority")
    return cfg


def set_polling(cfg: dict[str, Any]) -> None:
    with _LOCK:
        load()["polling"] = {
            "enabled": bool(cfg.get("enabled", True)),
            "mode": str(cfg.get("mode") or "credit-priority"),
        }
        save()


def _sanitize(acct: dict[str, Any]) -> dict[str, Any]:
    """管理台输出：token 只留尾 8 位。"""
    out = json.loads(json.dumps(acct, ensure_ascii=False))
    for key in ("access_token", "refresh_token"):
        val = out.get(key)
        if isinstance(val, str) and len(val) > 12:
            out[key] = "..." + val[-8:]
        elif val:
            out[key] = "<set>"
    return out


def list_sanitized() -> list[dict[str, Any]]:
    return [_sanitize(r) for r in accounts()]


# ---------- 导入 ----------

def _jwt_claims(token_str: str) -> dict[str, Any]:
    """解析 JWT payload（不验签，仅取声明）。"""
    import base64 as _b64
    try:
        p = token_str.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(_b64.urlsafe_b64decode(p))
    except Exception:
        return {}


def _uid_from_jwt(token_str: str) -> str:
    """从 access token (JWT) 提取 uid —— /login/account 不返回 uid 时的兑底。"""
    claims = _jwt_claims(token_str)
    return str(claims.get("uid") or claims.get("sub") or "").strip()


def import_token_payload(token: dict[str, Any], account: dict[str, Any],
                         nickname_plain: str = "") -> dict[str, Any]:
    """将 OAuth (auth/token + login/account) 结果并入账号库。

    token: {accessToken, refreshToken, expiresIn, refreshExpiresIn, expiresAt?, tokenType?, scope?}
    account: {uid, uin?, type?, ...}
    """
    at = str(token.get("accessToken") or token.get("access_token") or "").strip()
    rt = str(token.get("refreshToken") or token.get("refresh_token") or "").strip()
    if not at or not rt:
        raise ValueError("token payload missing accessToken/refreshToken")
    uid = str(account.get("uid") or token.get("uid") or "").strip()
    claims: dict[str, Any] = {}
    if not uid:
        claims = _jwt_claims(at)
        uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    if not uid:
        raise ValueError("account payload missing uid")
    if not nickname_plain and not (account.get("nickname") or account.get("uin")):
        claims = claims or _jwt_claims(at)
        nickname_plain = str(claims.get("nickname") or claims.get("preferred_username") or "").strip()
    exp = int(token.get("expiresAt") or 0)
    if not exp:
        exp = _now_ms() + int(float(token.get("expiresIn") or 2419200) * 1000)
    rexp = int(token.get("refreshExpiresAt") or 0)
    if not rexp:
        rexp = _now_ms() + int(float(token.get("refreshExpiresIn") or 2592000) * 1000)
    rec = {
        "uid": uid,
        "nickname_plain": nickname_plain or str(account.get("nickname") or account.get("uin") or uid[:8]),
        "uin": str(account.get("uin") or ""),
        "domain": str(account.get("domain") or "www.workbuddy.cn"),
        "edition_type": str(account.get("editionType") or account.get("type") or "personal"),
        "access_token": at,
        "refresh_token": rt,
        "token_type": str(token.get("tokenType") or "Bearer"),
        "session_state": str(token.get("sessionState") or ""),
        "scopes": str(token.get("scope") or ""),
        "expires_at": exp,
        "refresh_expires_at": rexp,
        "model_enabled": True,
        "needs_relogin": False,
        "last_error": None,
        "last_refresh_at": 0,
        "consecutive_failures": 0,
        "disabled_until": 0,
        "quota_cache": {"remaining": None, "total": None, "expire_at": None, "checked_at": 0},
    }
    return upsert(rec)


# ---------- 备份导出 / 导入 ----------

EXPORT_VERSION = 2


def export_accounts(include_tokens: bool = True) -> dict[str, Any]:
    """导出账号库（备份用）。include_tokens=False 时剥离 token（仅配置迁移）。"""
    data = load()
    out_accounts: list[dict[str, Any]] = []
    for rec in data["accounts"]:
        r = json.loads(json.dumps(rec, ensure_ascii=False))
        if not include_tokens:
            r.pop("access_token", None)
            r.pop("refresh_token", None)
        out_accounts.append(r)
    return {"wb_backup_version": EXPORT_VERSION, "exported_at": _now_ms(),
            "polling": dict(data.get("polling") or {}), "accounts": out_accounts}


def import_accounts(payload: dict[str, Any], overwrite: bool = True) -> dict[str, Any]:
    """从备份导入：按 uid 合并。返回 {added, updated, skipped}。"""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("payload.accounts must be a list")
    added = updated = skipped = 0
    with _LOCK:
        data = load()
        known = {str(r.get("uid")) for r in data["accounts"]}
        for raw in accounts:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            rec = _ensure_defaults(dict(raw))
            uid = str(rec.get("uid") or "").strip()
            if not uid:
                skipped += 1
                continue
            rec["uid"] = uid
            if uid in known:
                if not overwrite:
                    skipped += 1
                    continue
                for i, r in enumerate(data["accounts"]):
                    if str(r.get("uid")) == uid:
                        data["accounts"][i] = {**r, **rec, "uid": uid}
                        break
                updated += 1
            else:
                if not rec.get("access_token") or not rec.get("refresh_token"):
                    skipped += 1
                    continue
                data["accounts"].append(rec)
                known.add(uid)
                added += 1
        if payload.get("polling") and isinstance(payload["polling"], dict):
            data["polling"] = {**dict(DEFAULT_POLLING), **payload["polling"]}
        save()
    return {"added": added, "updated": updated, "skipped": skipped}


def set_auto_checkin(uid: str, enabled: bool) -> bool:
    with _LOCK:
        rec = get(str(uid))
        if not rec:
            return False
        rec["auto_checkin"] = bool(enabled)
        save()
        return True


# ---------- 用量 ----------

def apply_log_retention(max_records: int) -> int:
    """按设置裁剪用量记录到最近 N 条；返回裁剪后条数。"""
    global USAGE_MAX
    if max_records and int(max_records) > 0:
        USAGE_MAX = int(max_records)
    with _LOCK:
        try:
            recs = json.loads(USAGE_PATH.read_text("utf-8")) if USAGE_PATH.exists() else []
        except Exception:
            return 0
        if not isinstance(recs, list):
            return 0
        if len(recs) <= USAGE_MAX:
            return len(recs)
        recs = recs[-USAGE_MAX:]
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = USAGE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(recs, ensure_ascii=False), "utf-8")
        tmp.replace(USAGE_PATH)
        return len(recs)

def record_usage(uid: str, model: str, stream: bool,
                 prompt_tokens: int = 0, completion_tokens: int = 0,
                 status: str = "ok", error: str = "") -> None:
    with _LOCK:
        try:
            recs = json.loads(USAGE_PATH.read_text("utf-8")) if USAGE_PATH.exists() else []
            if not isinstance(recs, list):
                recs = []
        except Exception:
            recs = []
        recs.append({
            "ts": _now_ms(), "provider": "workbuddy", "account_uid": uid,
            "model": model, "stream": bool(stream),
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "status": status, "error": error[:200],
        })
        if len(recs) > USAGE_MAX:
            recs = recs[-USAGE_MAX:]
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = USAGE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(recs, ensure_ascii=False), "utf-8")
        os.replace(tmp, USAGE_PATH)


# ---------------- 积分快照（积分统计页趋势数据源） ----------------
# 口径与 wb-switch 相同：余额在连续快照间的正差值即消耗。
# 去重：同一 uid 余额未变化且距上次记录 < 30 分钟时不重复落盘。
SNAPSHOTS_PATH = APP_DIR / "data" / "wb_credit_snapshots.json"
SNAPSHOTS_MAX = 20000
SNAPSHOT_DEDUPE_MS = 30 * 60 * 1000

def record_credit_snapshot(uid: str, remaining, total) -> None:
    try:
        rem = round(float(remaining), 2)
        tot = round(float(total), 2) if total is not None else None
    except (TypeError, ValueError):
        return
    with _LOCK:
        try:
            recs = json.loads(SNAPSHOTS_PATH.read_text("utf-8")) if SNAPSHOTS_PATH.exists() else []
            if not isinstance(recs, list):
                recs = []
        except Exception:
            recs = []
        now = _now_ms()
        for r in reversed(recs):
            if str(r.get("uid")) != str(uid):
                continue
            if abs(float(r.get("remaining") or 0) - rem) < 0.005 and now - int(r.get("ts") or 0) < SNAPSHOT_DEDUPE_MS:
                return
            break
        recs.append({"ts": now, "uid": str(uid), "remaining": rem, "total": tot})
        if len(recs) > SNAPSHOTS_MAX:
            recs = recs[-SNAPSHOTS_MAX:]
        SNAPSHOTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SNAPSHOTS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(recs, ensure_ascii=False), "utf-8")
        os.replace(tmp, SNAPSHOTS_PATH)

def credit_snapshots() -> list[dict]:
    try:
        recs = json.loads(SNAPSHOTS_PATH.read_text("utf-8")) if SNAPSHOTS_PATH.exists() else []
        return recs if isinstance(recs, list) else []
    except Exception:
        return []
