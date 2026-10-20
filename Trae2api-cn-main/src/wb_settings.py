"""WorkBuddy Provider 设置：JSON 持久化（APP_DIR/data/wb_settings.json）。

线程模型：模块级 RLock + 缓存；写入 tmp+rename 原子替换。
字段语义见 DEFAULTS 注释；未设置的键回退默认值。
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging = __import__("logging").getLogger("wb-settings")

APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = APP_DIR / "data" / "wb_settings.json"

_LOCK = threading.RLock()
_CACHE: Optional[dict[str, Any]] = None

DEFAULTS: dict[str, Any] = {
    # 外观
    "theme": "system",              # light | dark | system
    "card_density": "comfortable",  # comfortable | compact
    # 轮询（运行时以 accounts.json.polling 为准，这里存 UI 偏好副本）
    "poll_mode": "credit-priority",  # credit-priority | round-robin
    "poll_enabled": True,
    # 保活与阈值
    "keepalive_days": 2,            # access token 剩余 < N 天时提前刷新
    "expiry_warn_days": 7,          # 到期警示阈值（天）
    # 自动签到
    "auto_checkin": True,           # 总开关
    "auto_checkin_time": "09:00",   # 每日签到时间（HH:MM）
    "auto_checkin_jitter_min": 30,  # 随机抖动（分钟），避免整点风控特征
    "auto_checkin_uids": [],        # 黑名单：不参与自动签到的 uid
    # 记录
    "log_retention": 5000,          # 用量记录保留条数
}

_INT_KEYS = {"keepalive_days", "expiry_warn_days", "auto_checkin_jitter_min",
             "log_retention"}
_BOOL_KEYS = {"poll_enabled", "auto_checkin"}
_LIST_KEYS = {"auto_checkin_uids"}
_STR_KEYS = {"theme", "card_density", "poll_mode", "auto_checkin_time"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS)
    if isinstance(d, dict):
        for k, v in d.items():
            if k in _INT_KEYS:
                try:
                    out[k] = max(0, int(v))
                except (TypeError, ValueError):
                    pass
            elif k in _BOOL_KEYS:
                out[k] = bool(v)
            elif k in _LIST_KEYS:
                out[k] = [str(x) for x in v] if isinstance(v, list) else []
            elif k in _STR_KEYS:
                out[k] = str(v)
    if out.get("auto_checkin_time", "") and len(str(out["auto_checkin_time"]).split(":")) != 2:
        out["auto_checkin_time"] = DEFAULTS["auto_checkin_time"]
    return out


def load(force: bool = False) -> dict[str, Any]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None and not force:
            return dict(_CACHE)
        data: dict[str, Any] = {}
        try:
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text("utf-8"))
        except Exception as exc:  # 损坏文件回退默认
            logger.warning("wb-settings load failed, use defaults: %s", exc)
            data = {}
        _CACHE = _normalize(data)
        return dict(_CACHE)


def save(patch: dict[str, Any]) -> dict[str, Any]:
    """合并写入并返回规范化后的完整设置。"""
    global _CACHE
    with _LOCK:
        cur = load()
        merged = dict(cur)
        merged.update(patch or {})
        _CACHE = _normalize(merged)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_CACHE, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(SETTINGS_PATH)
        return dict(_CACHE)


def get(key: str, default: Any = None) -> Any:
    return load().get(key, DEFAULTS.get(key, default))
