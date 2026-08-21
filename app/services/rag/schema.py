"""RAG 数据模型：Chunk 与元数据字段。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """一个可检索的文本片段（向量检索后返回给判分层）。"""

    text: str
    source: str = ""          # 文档名（如 "lesson-plan-writing"）
    lesson: str = ""          # 所属 Lesson（结构化文档用，如 "3"）
    title: str = ""           # Lesson 标题（如 "Write an Email Sample Response"）
    page: int = 0             # 起始页码（1-based）
    meta: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "lesson": self.lesson,
            "title": self.title,
            "page": self.page,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(
            text=d.get("text", ""),
            source=d.get("source", ""),
            lesson=d.get("lesson", ""),
            title=d.get("title", ""),
            page=int(d.get("page", 0)),
            meta=dict(d.get("meta", {})),
        )

    def source_label(self) -> str:
        """生成可展示的来源标签（如 "[ETS Lesson Plan Writing, Lesson 3, p.12]"）。"""
        parts = ["ETS Lesson Plan Writing"]
        if self.lesson:
            parts.append(f"Lesson {self.lesson}")
        if self.title:
            parts.append(self.title)
        if self.page:
            parts.append(f"p.{self.page}")
        return "[" + ", ".join(parts) + "]"
