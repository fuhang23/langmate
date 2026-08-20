"""核心表达收藏的数据模型。

收藏的是互动面试「核心表达」（英文词组）。每收藏一条，除了词组本身，
还附带：中文释义（LLM 生成）、例句（从该题参考回答中本地提取）、
出处（主题 + 题号），方便学生回顾时理解词组在什么场景、怎么用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Favorite:
    """一条核心表达收藏。

    Attributes:
        expression: 英文词组（去重键，如 "take the initiative"）。
        translation: 中文释义（LLM 生成，失败时为空串）。
        example: 出自参考回答的例句（本地提取，提取不到为空串）。
        topic_id: 出处主题 id。
        topic_title: 出处主题名（冗余存，避免 join）。
        question_seq: 出处题号（该主题下的第几题）。
        created_at: ISO 8601 时间戳（UTC）。
    """

    expression: str
    translation: str = ""
    example: str = ""
    topic_id: int = 0
    topic_title: str = ""
    question_seq: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "translation": self.translation,
            "example": self.example,
            "topicId": self.topic_id,
            "topicTitle": self.topic_title,
            "questionSeq": self.question_seq,
            "createdAt": self.created_at,
        }


@dataclass
class FavoriteGroup:
    """按主题分组的收藏集合（前端列表页按此展示）。"""

    topic_id: int
    topic_title: str
    items: list[Favorite] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topicId": self.topic_id,
            "topicTitle": self.topic_title,
            "items": [item.to_dict() for item in self.items],
        }
