"""互动面试的内容四维评分（LLM）。

对自由作答的转写文本，评「语法 / 词汇 / 逻辑 / 内容」四个维度。
发音与流利度由有道音频评测负责，不在这里（语义无法从音频文本推断）。

输出严格 JSON：
{
  "grammar":     {"score": 0-100, "comment": "一句中文评语"},
  "vocabulary":  {"score": 0-100, "comment": "..."},
  "logic":       {"score": 0-100, "comment": "..."},
  "content":     {"score": 0-100, "comment": "..."}
}
"""

from __future__ import annotations

from loguru import logger
from typing import Any

from services.llm.deepseek import chat_json

_SYSTEM = (
    "你是托福口语（Take an Interview 题型）的评分考官。"
    "考生需在 45 秒内针对问题即兴作答。"
    "请**只**从以下四个维度评分（不要评发音、流利度，那由音频评测负责）：\n"
    "1. grammar 语法（句式复杂度、语法准确度）\n"
    "2. vocabulary 词汇（用词准确度、多样性）\n"
    "3. logic 逻辑（观点组织、衔接连贯）\n"
    "4. content 内容（是否切题、是否充分展开）\n"
    "严格按以下 JSON 结构输出，每个维度是一个对象，含 score（0-100 整数）"
    "和 comment（一句中文评语）：\n"
    '{"grammar": {"score": 80, "comment": "..."}, '
    '"vocabulary": {"score": 75, "comment": "..."}, '
    '"logic": {"score": 70, "comment": "..."}, '
    '"content": {"score": 78, "comment": "..."}}\n'
    "只输出 JSON，不要输出任何其他文字。"
)

_SCORE_SECTIONS = ("grammar", "vocabulary", "logic", "content")


async def score_content(
    *,
    question_prompt: str,
    transcript: str,
) -> dict[str, Any]:
    """对一段面试作答做内容四维评分。

    Args:
        question_prompt: 面试题目（英文，含 interviewer 引导语）。
        transcript: 学生作答的转写文本。

    Returns:
        {"grammar": {...}, "vocabulary": {...}, "logic": {...}, "content": {...}}
        每个维度含 score(int | None) 与 comment(str)。
        score 为 None 表示 LLM 未返回该维度分数（前端显示「—」）。

    Raises:
        RuntimeError: LLM 调用失败。
    """
    # RAG 检索用户知识库（口语相关，失败降级为空，不阻断评分）。
    system = _SYSTEM
    try:
        from services.ingest import search_knowledge_base

        chunks = search_knowledge_base(
            query=question_prompt,
            subject="speaking",
            top_k=2,
        )
        if chunks:
            rag_text = "\n\n".join(f"{c.source_label()}\n{c.text[:600]}" for c in chunks)
            system += f"\n\n## 参考的备考知识（可引用，用于增强评分依据）\n{rag_text}"
    except Exception:
        pass

    user = (
        f"面试题目：\n{question_prompt}\n\n"
        f"考生的作答（转写文本）：\n{transcript}\n\n"
        "请按 JSON 格式输出四个维度的评分与评语。"
    )
    data = await chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    logger.debug("LLM score_content response: {}", data)

    result: dict[str, Any] = {}
    for section in _SCORE_SECTIONS:
        item = data.get(section, {})
        if isinstance(item, dict):
            # 嵌套结构：{"grammar": {"score": 90, "comment": "..."}}
            raw_score = item.get("score")
            comment = str(item.get("comment", ""))
        else:
            # 扁平结构：{"grammar": 90}（LLM 可能简化输出）
            raw_score = item
            comment = ""
        # 区分：None（LLM 未返回）vs 数字（LLM 实际评分，包括 0）。
        score: int | None
        if raw_score is None:
            score = None
        else:
            try:
                score = max(0, min(100, int(raw_score)))
            except (TypeError, ValueError):
                score = None
        result[section] = {
            "score": score,
            "comment": comment,
        }
    return result
