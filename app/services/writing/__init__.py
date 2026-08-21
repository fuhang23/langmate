"""LangMate 写作判分：rubric 结构化 + LLM 判分 + RAG 增强。"""

from __future__ import annotations

from services.writing.rubrics import RUBRICS, rubric_for
from services.writing.score_writing import score_writing

__all__ = ["RUBRICS", "rubric_for", "score_writing"]
