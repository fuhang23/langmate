"""DeepSeek LLM 调用封装（OpenAI 兼容接口）。

services 层约定不依赖 nanobot 内部，用 httpx 直连 DeepSeek。
配置读环境变量：
- DEEPSEEK_API_KEY（必需）
- DEEPSEEK_BASE_URL（可选，默认 https://api.deepseek.com）
- DEEPSEEK_MODEL（可选，默认 deepseek-chat）

deepseek-chat 是 DeepSeek 的稳定别名（指向最新版），与项目 config.json
主模型保持一致。
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return key


def _base_url() -> str:
    return os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)


async def chat_json(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """调用 DeepSeek chat completions，强制 JSON 输出并解析为 dict。

    Args:
        messages: OpenAI 格式的 messages 列表。
        model: 模型名，默认取 DEEPSEEK_MODEL 或 deepseek-chat。
        temperature: 采样温度。
        timeout: 请求超时（秒）。

    Returns:
        解析后的 JSON dict。

    Raises:
        RuntimeError: 配置缺失 / 请求失败 / JSON 解析失败。
    """
    url = f"{_base_url()}/chat/completions"
    payload = {
        "model": model or _model(),
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    # DeepSeek 可能把 JSON 包在 ```json ... ``` 里。
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    return json.loads(content)
