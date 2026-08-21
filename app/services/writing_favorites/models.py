"""写作地道表达收藏的数据模型（独立于口语核心表达收藏）。

写作收藏的是「地道表达 / 高分句型」（书面表达），与口语的「核心表达」
（口语词组）分表存放——两者的表达性质不同，需要分开积累回顾。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class WritingFavorite:
    """一条写作地道表达收藏。

    Attributes:
        expression: 英文地道表达 / 高分句型（去重键，如 "I would appreciate it if..."）。
        translation: 中文释义（判分时 LLM 已生成）。
        example: 含该表达的范文原句。
        task_type: 来源题型（"email" 或 "discussion"）。
        title: 出处题目标题。
        created_at: ISO 8601 时间戳（UTC）。
    """

    expression: str
    translation: str = ""
    example: str = ""
    task_type: str = ""
    title: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "translation": self.translation,
            "example": self.example,
            "taskType": self.task_type,
            "title": self.title,
            "createdAt": self.created_at,
        }


@dataclass
class WritingFavoriteGroup:
    """按题型分组的写作收藏集合（前端列表页按此展示）。"""

    task_type: str
    items: list[WritingFavorite] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskType": self.task_type,
            "items": [item.to_dict() for item in self.items],
        }
