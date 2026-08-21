"""阿里云百炼 text-embedding-v4 向量化封装（OpenAI 兼容模式）。

云端只做 embedding 计算，不持久化；向量与原文全部存本地。
使用 httpx 直连（与 services/llm/deepseek.py 一致，避免引入 openai SDK）。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_MODEL = "text-embedding-v4"
DEFAULT_DIM = 1024
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _api_key() -> str:
    return os.environ.get("BAILIAN_API_KEY", "")


def _model() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)


def _dim() -> int:
    try:
        return int(os.environ.get("EMBEDDING_DIM", str(DEFAULT_DIM)))
    except ValueError:
        return DEFAULT_DIM


def _base_url() -> str:
    return os.environ.get("EMBEDDING_BASE_URL", DEFAULT_BASE_URL)


def _embed(texts: list[str]) -> list[list[float]]:
    """调用百炼 embedding 接口，返回与 texts 顺序一致的向量列表。"""
    key = _api_key()
    if not key:
        raise RuntimeError("BAILIAN_API_KEY 未配置，无法计算 embedding")
    body: dict[str, Any] = {
        "model": _model(),
        "input": texts,
        "encoding_format": "float",
    }
    # text-embedding-v4 支持显式维度，仅当配置与默认不同时才传。
    if _dim() != DEFAULT_DIM:
        body["dimensions"] = _dim()
    resp = httpx.post(
        f"{_base_url()}/embeddings",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"embedding 调用失败 {resp.status_code}: {resp.text}")
    data = resp.json()
    items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
    return [list(item["embedding"]) for item in items]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化（text-embedding-v4 单次 input 最多 10 条，超则分批）。"""
    vectors: list[list[float]] = []
    batch = 10
    for i in range(0, len(texts), batch):
        vectors.extend(_embed(texts[i : i + batch]))
    return vectors


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]
