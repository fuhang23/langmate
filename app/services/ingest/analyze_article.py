"""大模型通读文章，判断归属并结构化提取（题目 / RAG 知识点）。

用 chat_json 输出结构化结果：category（归属）+ items（题目）+ chunks（知识点）。
category 取值：
- writing_discussion / writing_email：学术讨论 / 邮件写作题
- speaking_repeat / speaking_interview：跟读 / 面试口语题
- rag：备考方法论 / 知识点（分块进 RAG 知识库）
- ignore：无关内容（留学资讯、广告等）
"""

from __future__ import annotations

from typing import Any

from services.llm.deepseek import chat_json

# 一篇文章截断到该长度再喂给 LLM（够判断与提取，避免超长）。
_MAX_CHARS = 8000

_CATEGORIES = [
    "writing_discussion",
    "writing_email",
    "speaking_repeat",
    "speaking_interview",
    "rag",
    "ignore",
]

_SYSTEM = (
    "你是托福备考内容编辑。给定一篇公众号文章，判断它属于哪类，并结构化提取内容。\n\n"
    "## 分类规则\n"
    "- writing_discussion：含「教授提问 + 同学回帖 + 范文」的学术讨论写作题；\n"
    "- writing_email：含「场景 + 任务清单 + 范文」的邮件写作题；\n"
    "- speaking_repeat：含适合跟读复述的句子（可标注意群）；\n"
    "- speaking_interview：含 45 秒即兴口语表达的面试题（含参考回答）；\n"
    "- rag：备考方法论、评分标准、答题技巧、留学资讯等「知识型」内容（非题目）；\n"
    "- ignore：与托福备考无关（广告、纯推广等）。\n\n"
    "## 提取要求\n"
    "1. 一篇文章只归一个主类别；若既含题目又含方法论，优先归为题目类。\n"
    "2. 题目类要忠实提取题目原文（英文题目保留英文，不要改写）；标题生成简洁中文。\n"
    "3. 跟读题：把每个句子按意群断句（chunks），text 为去掉断句符的完整句子。\n"
    "4. 面试题：提取 prompt_en（英文题目）、prompt_zh（中文要点）、reference_answer（参考回答）、core_expressions（核心表达词组）。\n"
    "5. 写作题：提取 prompt_en（完整题目，含教授提问/同学回帖或任务清单）、reference_answer（参考范文）。\n"
    "6. rag 类：把正文按段落/主题切成若干知识点 chunk（每条 100-400 字）。\n"
    "7. 提取不到的内容填空数组，不要编造。\n\n"
    "## 输出 JSON 结构（严格按此）\n"
    "{\n"
    '  "category": "写作/口语/rag/ignore 之一",\n'
    '  "reason": "一句话判断理由",\n'
    '  "items": [ /* 题目，结构随 category */ ],\n'
    '  "chunks": [ /* rag 时：{"text": "...", "title": "..."} */ ]\n'
    "}\n\n"
    "题目类 items 结构：\n"
    "- writing_discussion / writing_email："
    '{"task_type": "discussion|email", "title": "中文标题", "prompt_en": "...", "reference_answer": "..."}\n'
    "- speaking_repeat："
    '{"title": "场景标题", "sentences": [{"seq": 1, "text": "...", "chunks": ["...", "..."]}]}\n'
    "- speaking_interview："
    '{"title": "主题", "questions": [{"seq": 1, "prompt_en": "...", "prompt_zh": "...", "reference_answer": "...", "core_expressions": ["..."]}]}\n'
)


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_CHARS else text[:_MAX_CHARS]


async def analyze_article(*, title: str, raw_text: str) -> dict[str, Any]:
    """判断文章归属并提取内容，返回 {category, reason, items, chunks}。"""
    user = (
        f"## 文章标题\n{title or '(无标题)'}\n\n"
        f"## 文章正文\n{_truncate(raw_text)}\n\n"
        "请判断分类并按要求提取。"
    )
    data = await chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        timeout=60.0,
    )

    category = data.get("category") or "ignore"
    if category not in _CATEGORIES:
        category = "ignore"

    items = data.get("items") or []
    chunks = data.get("chunks") or []
    if not isinstance(items, list):
        items = []
    if not isinstance(chunks, list):
        chunks = []

    return {
        "category": category,
        "reason": data.get("reason") or "",
        "items": items,
        "chunks": chunks,
    }
