"""RecordProgressTool：把一次练习的评分结果写入本地进度库。

供教学智能体在学生每次完整作答并评分后调用，把 CEFR 级别、
五维分、薄弱点写入 SQLite（services.progress.ProgressStore），
学习仪表盘据此展示水平与进度。

职责边界：本工具只负责「记录」，不做「分析/评分」——评分由
AnalyzeSpeechTool + 教学智能体完成，本工具接收它们产出的结果。
写库失败时降级（记 warning、返回提示），不阻断口语教学流程。
"""

from __future__ import annotations

import logging
from typing import Any

from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.context import ToolContext

from services.progress import PracticeRecord, ProgressStore, default_db_path

logger = logging.getLogger(__name__)


@tool_parameters({
    "type": "object",
    "properties": {
        "section": {
            "type": "string",
            "description": "练习所属部分：speaking/listening/reading/writing/vocab",
            "enum": ["speaking", "listening", "reading", "writing", "vocab"],
        },
        "cefr": {
            "type": "string",
            "description": "本次练习综合出的 CEFR 级别，如 A1/A2/B1/B2/C1/C2",
        },
        "question_type": {
            "type": "string",
            "description": "题型，如口语的 listen_and_repeat（复述）或 interview（互动面试）",
        },
        "scores": {
            "type": "object",
            "description": "五维评分（0-4 制），如 {\"pronunciation\": 3.0, \"fluency\": 2.5}",
        },
        "weak_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "本次暴露的薄弱点，如 [\"think 的 /θ/ 发成 /s/\", \"连读不稳定\"]",
        },
    },
    "required": ["section", "cefr"],
})
class RecordProgressTool(Tool):
    """记录一次练习的评分结果到本地进度库。"""

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls()

    @property
    def name(self) -> str:
        return "record_progress"

    @property
    def description(self) -> str:
        return (
            "把一次练习的评分结果（CEFR 级别、五维分、薄弱点）写入本地进度库，"
            "用于学习仪表盘展示水平与进度。学生每次完整作答并评分后调用一次。"
            "section 取值：speaking/listening/reading/writing/vocab。"
        )

    async def execute(
        self,
        section: str,
        cefr: str,
        question_type: str = "",
        scores: dict[str, Any] | None = None,
        weak_points: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        record = PracticeRecord(
            section=section,
            question_type=question_type or "",
            scores=scores or {},
            cefr=cefr,
            weak_points=weak_points or [],
        )
        try:
            store = ProgressStore(default_db_path())
            store.add_record(record)
        except Exception as e:  # 写库失败不阻断教学，仅降级
            logger.warning("RecordProgressTool 写入失败（不阻断对话）: %s", e)
            return f"进度记录未保存成功（{e}），但不影响本次教学，请继续。"

        return (
            f"已记录本次练习进度：{section} / CEFR {cefr}"
            f" / 薄弱点 {len(record.weak_points)} 项。"
        )
