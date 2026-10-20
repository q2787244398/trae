"""WorkBuddy 模型清单：/v3/config 动态抓取 + 缓存 + 静态兜底；对外统一前缀。

- `wb-*`  → 国内版账号池（cn）
- `wbi-*` → 国际版账号池（ai，端点待 P0' 实测，模型清单为空时不输出）
"""
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
MODEL_PREFIX_AI = os.environ.get("WB_MODEL_PREFIX_AI", "wbi-")
CONFIG_URL = os.environ.get("WB_CONFIG_URL", "https://www.workbuddy.cn/v3/config")
CONFIG_URL_AI = os.environ.get("WB_CONFIG_URL_AI", "https://www.workbuddy.ai/v3/config")
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "wb_models_cache.json"
CACHE_PATH_AI = Path(__file__).resolve().parent.parent / "data" / "wb_models_cache_ai.json"
CACHE_TTL_MS = 6 * 3600 * 1000

# P0 实测可用模型（2026-10-20 流式推理 200 验证；11102=模型不存在）
STATIC_MODELS: list[str] = ["kimi-k3", "deepseek-v3.2", "deepseek-v4-pro"]
# 国际版暂无实测清单，等 P0' 后填充
STATIC_MODELS_AI: list[str] = []


def _cache_path(variant: str) -> Path:
    return CACHE_PATH_AI if variant == "ai" else CACHE_PATH


def _load_cache(variant: str = "cn") -> dict[str, Any]:
    try:
        data = json.loads(_cache_path(variant).read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            return data
    except Exception:
        pass
    return {"models": [], "fetched_at": 0}


def _save_cache(models: list[str], variant: str = "cn") -> None:
    p = _cache_path(variant)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"models": models, "fetched_at": int(time.time() * 1000)}, ensure_ascii=False),
        "utf-8")


def variant_of(model: str) -> str:
    """根据对外模型名判断所属池。"""
    if isinstance(model, str) and model.startswith(MODEL_PREFIX_AI):
        return "ai"
    return "cn"


def known_models(variant: str = "cn") -> list[str]:
    """已知的上游模型 ID（不含前缀）。"""
    cached = _load_cache(variant)
    static = STATIC_MODELS_AI if variant == "ai" else STATIC_MODELS
    models = list(dict.fromkeys((cached.get("models") or []) + static))
    return models


def openai_models() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for variant, prefix in (("cn", MODEL_PREFIX), ("ai", MODEL_PREFIX_AI)):
        for m in known_models(variant):
            out.append({
                "id": f"{prefix}{m}",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "workbuddy-ai" if variant == "ai" else "workbuddy",
            })
    return out


def is_wb_model(model: str) -> bool:
    if not isinstance(model, str):
        return False
    return model.startswith(MODEL_PREFIX) or model.startswith(MODEL_PREFIX_AI)


def upstream_model(model: str) -> str:
    for prefix in (MODEL_PREFIX_AI, MODEL_PREFIX):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def remember_model(upstream_id: str, variant: str = "cn") -> None:
    """某模型首次推理成功后并入已知列表。"""
    if not upstream_id:
        return
    cached = _load_cache(variant)
    static = STATIC_MODELS_AI if variant == "ai" else STATIC_MODELS
    models = list(dict.fromkeys((cached.get("models") or []) + static + [upstream_id]))
    if models != (cached.get("models") or []):
        _save_cache(models, variant)


async def refresh_from_config() -> list[str]:
    """用当前可用账号的 token 抓 /v3/config，解析 models 字段（两版各自尝试）。"""
    from . import wb_client as _wc
    last: list[str] = []
    for variant, cfg_url in (("cn", CONFIG_URL), ("ai", CONFIG_URL_AI)):
        for rec in wb_store.accounts():
            if not _eligible_quick(rec):
                continue
            if _wc.normalize_variant(rec.get("variant")) != variant:
                continue
            try:
                headers = _wc.build_headers(rec)
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(cfg_url, headers=headers)
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
                    _save_cache(parsed, variant)
                    logger.info("wb-models: %d models from %s", len(parsed), cfg_url)
                    last = parsed
                    break
            except Exception as exc:
                logger.error("wb-models: config fetch error (%s)", exc)
    return last or known_models("cn")


def _eligible_quick(rec: dict[str, Any]) -> bool:
    return (rec.get("model_enabled", True) and not rec.get("needs_relogin")
            and len(str(rec.get("access_token") or "")) > 20)
