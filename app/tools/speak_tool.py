"""SpeakTool：把文字合成语音并发送到当前对话。

封装 services.tts.doubao（豆包 TTS），生成的 mp3 存入 nanobot media 目录，
通过 OutboundMessage.media 投递到 WebUI，前端渲染为音频播放器。

用法场景（由 toefl-speaking Skill 引导）：
- 复述题播题：读题目句子；
- 发音示范：读正确的连读/重音示范；
- 反馈播报：把点评读出来。

TTS 不可用时返回 ToolResult.error，教学智能体用文字兜底。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.context import ToolContext, current_request_context
from nanobot.bus.events import OutboundMessage
from nanobot.config.paths import get_media_dir

from services.tts.doubao import DEFAULT_VOICE, synthesize


@tool_parameters({
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "要朗读并发送的英文文字（题目、发音示范或反馈）",
            "minLength": 1,
        },
        "voice_type": {
            "type": "string",
            "description": "可选，火山 TTS 音色 ID；不填用默认音色",
        },
        "note": {
            "type": "string",
            "description": "可选，随语音一起展示的一行文字说明（如「第 2 遍示范」）",
        },
    },
    "required": ["text"],
})
class SpeakTool(Tool):
    """把文字合成语音（豆包 TTS）并发送到当前对话。"""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ) -> None:
        self._send_callback = send_callback

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls(send_callback=ctx.bus.publish_outbound if ctx.bus else None)

    @property
    def name(self) -> str:
        return "speak"

    @property
    def description(self) -> str:
        return (
            "把英文文字合成语音（TTS）并发送到当前对话，学生会听到朗读，"
            "同时语音下方会展示朗读的英文原文（无需你另外发一遍文字）。"
            "用于：复述题播题、正确发音示范、把点评读出来。"
            "如需额外说明（如「第 2 遍示范」），用 note 参数传一行文字。"
        )

    async def execute(
        self,
        text: str,
        voice_type: str | None = None,
        note: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if not self._send_callback:
            return ToolResult.error("Error: 消息通道不可用，无法发送语音")

        try:
            audio = synthesize(text, voice_type=voice_type or DEFAULT_VOICE)
        except Exception as e:
            logger.warning("SpeakTool TTS 失败: {}", e)
            return ToolResult.error(
                f"Error: TTS 合成失败（{type(e).__name__}: {e}），请改用文字教学"
            )

        out_path = get_media_dir("tts") / f"speak_{uuid.uuid4().hex[:12]}.mp3"
        try:
            out_path.write_bytes(audio)
        except OSError as e:
            return ToolResult.error(f"Error: 语音文件保存失败: {e}")

        request_ctx = current_request_context()
        if request_ctx is None or not request_ctx.channel or not request_ctx.chat_id:
            return ToolResult.error("Error: 无当前对话上下文，无法投递语音")

        # LangMate: 语音消息同时携带朗读的英文原文，让学生能边听边看文字参考。
        # note（如有）作为一行说明，text 作为正文展示。
        content = f"{note}\n{text}" if note else text
        msg = OutboundMessage(
            channel=request_ctx.channel,
            chat_id=request_ctx.chat_id,
            content=content,
            media=[str(out_path)],
        )
        try:
            await self._send_callback(msg)
        except Exception as e:
            logger.exception("SpeakTool 语音投递失败: {}", e)
            return ToolResult.error(f"Error: 语音投递失败: {e}")

        return f"已合成并发送语音（{len(audio)} 字节）: {text[:50]}"
