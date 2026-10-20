"""WorkBuddy 模型清单：/v3/config 动态抓取 + 缓存 + 静态兜底；对外统一 wb- 前缀。"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from . import wb_client, wb_store

logger = logging.getLogger("wb-models")

MODEL_PREFIX = os.environ.get("WB_MODEL_PREFIX", "wb-")
CONFIG_URL = os.environ.get("WB_CONFIG_URL", "https://www.workbuddy.cn/v3/config")
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "wb_models_cache.json"
CACHE_TTL_MS = 6 * 3600 * 1000

# P0 实测可用模型（2026-10-20 流式推理 200 验证；11102=模型不存在）
STATIC_MODELS: list[str] = ["kimi-k3", "deepseek-v3.2", "deepseek-v4-pro"]


def _load_cache() -> dict[str, Any]:
    try:
        data = json.loads(CACHE_PATH.read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            return data
    except Exception:
        pass
    return {"models": [], "fetched_at": 0}


def _save_cache(models: list[str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(
        {"models": models, "fetched_at": int(time.time() * 1000)}, ensure_ascii=False),
        "utf-8")


def known_models() -> list[str]:
    """已知的上游模型 ID（不含前缀）。"""
    cached = _load_cache()
    models = list(dict.fromkeys((cached.get("models") or []) + STATIC_MODELS))
    return models


def openai_models() -> list[dict[str, Any]]:
    out = []
    for m in known_models():
        out.append({
            "id": f"{MODEL_PREFIX}{m}",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "workbuddy",
        })
    return out


def is_wb_model(model: str) -> bool:
    return isinstance(model, str) and model.startswith(MODEL_PREFIX)


def upstream_model(model: str) -> str:
    return model[len(MODEL_PREFIX):] if model.startswith(MODEL_PREFIX) else model


def remember_model(upstream_id: str) -> None:
    """某模型首次推理成功后并入已知列表。"""
    if not upstream_id:
        return
    cached = _load_cache()
    models = list(dict.fromkeys((cached.get("models") or []) + STATIC_MODELS + [upstream_id]))
    if models != (cached.get("models") or []):
        _save_cache(models)


async def refresh_from_config() -> list[str]:
    """用当前可用账号的 token 抓 /v3/config，解析 models 字段。"""
    for rec in wb_store.accounts():
        if not _eligible_quick(rec):
            continue
        try:
            headers = wb_client.build_headers(rec)
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(CONFIG_URL, headers=headers)
            body = resp.json()
            data = body.get("data") or {}
            models_raw = data.get("models")
            parsed: list[str] = []
            if isinstance(models_raw, list):
                for m in models_raw:
                    if isinstance(m, str):
                        parsed.append(m)
                    elif isinstance(m, dict):
                        mid = m.get("id") or m.get("model") or m.get("name")
                        if mid:
                            parsed.append(str(mid))
            if parsed:
                _save_cache(parsed)
                logger.info("wb-models: %d models from /v3/config", len(parsed))
                return parsed
        except Exception as exc:
            logger.error("wb-models: config fetch error (%s)", exc)
    return known_models()


def _eligible_quick(rec: dict[str, Any]) -> bool:
    return (rec.get("model_enabled", True) and not rec.get("needs_relogin")
            and len(str(rec.get("access_token") or "")) > 20)
