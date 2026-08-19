"""LLM 调用层。

services 层不依赖 nanobot 内部，用 httpx 直连 DeepSeek（OpenAI 兼容接口）。
包含：chat_json（通用 JSON 调用）、score_content（互动面试内容四维评分）。
"""

from services.llm.deepseek import chat_json
from services.llm.scoring import score_content

__all__ = ["chat_json", "score_content"]
