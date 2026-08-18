"""AnalyzeSpeechTool：学生口语录音的双轨分析。

封装 services.orchestration.analyze_speech：
- 轨道 A 文本由 nanobot ASR 转写后随消息传入（本工具不重复转写）；
- 轨道 B 把原始音频送有道智云发音评测，产出音素级报告
  （连读/弱读/重音/语调/流利度），并把发音/流利度两维映射到 CEFR。

返回 JSON 字符串注入教学智能体上下文，由其综合出五维评分。
评测失败返回带 assessment_error 的结果，教学智能体用文字维度兜底。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.context import ToolContext

from services.orchestration import analyze_speech


@tool_parameters({
    "type": "object",
    "properties": {
        "audio_path": {
            "type": "string",
            "description": "学生录音文件的本地路径（消息附件里的音频路径）",
            "minLength": 1,
        },
        "transcript": {
            "type": "string",
            "description": "这段录音的 ASR 转写文本（即学生消息的文字内容）",
            "minLength": 1,
        },
        "reference_text": {
            "type": "string",
            "description": "复述题的标准原文；互动面试等自由作答不要传",
        },
    },
    "required": ["audio_path", "transcript"],
})
class AnalyzeSpeechTool(Tool):
    """分析学生口语录音：发音评测 + 双轨融合。"""

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls()

    @property
    def name(self) -> str:
        return "analyze_speech"

    @property
    def description(self) -> str:
        return (
            "分析学生的一段口语录音：对原始音频做音素级发音评测"
            "（发音准确度/流利度/连读弱读/重音，并给出 CEFR 级别），"
            "与 ASR 转写文本融合后返回结构化结果。"
            "学生每次提交语音作答后都应调用一次，再基于结果做五维评分。"
            "复述题必须传 reference_text；自由作答（互动面试）不传。"
        )

    async def execute(
        self,
        audio_path: str,
        transcript: str,
        reference_text: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if not Path(audio_path).exists():
            return ToolResult.error(f"Error: 音频文件不存在: {audio_path}")

        analysis = await analyze_speech(
            transcript,
            audio_path,
            reference_text=reference_text or "",
        )
        return analysis.to_prompt_json()
