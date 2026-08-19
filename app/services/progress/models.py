"""练习记录数据模型。

LangMate 的学习进度统一用「练习记录」来表示：学生每完成一次练习
（口语复述、听力题、阅读题、写作、背词测验），就产生一条 PracticeRecord，
写入 SQLite（ProgressStore）。仪表盘通过聚合这些记录展示水平与进度。

section 字段让同一套存储复用于托福五部分（听说读写词汇），
未来听力/阅读/词汇专门页面无需新表，直接复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# 托福各部分（section 的合法取值）。
SECTIONS: tuple[str, ...] = (
    "speaking",    # 口语
    "listening",   # 听力
    "reading",     # 阅读
    "writing",     # 写作
    "vocab",       # 词汇
    "grammar",     # 语法
)

SECTION_LABELS: dict[str, str] = {
    "speaking": "口语",
    "listening": "听力",
    "reading": "阅读",
    "writing": "写作",
    "vocab": "词汇",
    "grammar": "语法",
}


@dataclass
class PracticeRecord:
    """一次练习的评分结果。

    Attributes:
        section: 五部分之一（speaking/listening/reading/writing/vocab）。
        question_type: 题型，如口语的 listen_and_repeat / interview。
        scores: 五维分（0-4 制），如 {"pronunciation": 3.0, ...}。
        cefr: 本次练习综合出的 CEFR 级别（如 "B1"）。
        weak_points: 本次暴露的薄弱点（音素、语法点、词汇等）。
        created_at: ISO 8601 时间戳（UTC）。
    """

    section: str
    question_type: str = ""
    scores: dict[str, Any] = field(default_factory=dict)
    cefr: str = ""
    weak_points: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
