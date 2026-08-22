"""大模型通读内容：判断归属（category）、过滤（考试/广告）、打标签、结构化提取。

对外两个接口：
- analyze_article：链接导入用，完整判断（category + 抽题 + LLM 分块）。
- analyze_tags：文件上传用，轻量判断（只判断考试/广告/打科目·类型标签，
  不抽题、不分块；文件分块仍走本地 chunker）。

过滤规则（由 ingest 层执行）：is_ad == True 或 exam != "toefl" → 强制 ignore。

标签枚举：
- exam:        toefl / ielts / gre / other
- subject:     speaking / writing / reading / listening / vocab / grammar / general
- content_type: question / sample_essay / methodology / experience / vocabulary / news / ad
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

_EXAMS = ["toefl", "ielts", "gre", "other"]
_SUBJECTS = ["speaking", "writing", "reading", "listening", "vocab", "grammar", "general"]
_CONTENT_TYPES = [
    "question",
    "sample_essay",
    "methodology",
    "experience",
    "vocabulary",
    "news",
    "ad",
]

_SYSTEM = (
    "你是托福备考内容编辑。给定一篇公众号文章，判断它属于哪类，并结构化提取内容。\n\n"
    "## 分类规则（category）\n"
    "- writing_discussion：含「教授提问 + 同学回帖 + 范文」的学术讨论写作题；\n"
    "- writing_email：含「场景 + 任务清单 + 范文」的邮件写作题；\n"
    "- speaking_repeat：含适合跟读复述的句子（可标注意群）；\n"
    "- speaking_interview：含 45 秒即兴口语表达的面试题（含参考回答）；\n"
    "- rag：备考方法论、评分标准、答题技巧等「知识型」内容（非题目）；\n"
    "- ignore：与托福备考无关（广告、纯推广、其他考试内容等）。\n\n"
    "## 标签字段\n"
    "- exam：内容主要针对的考试，取 toefl / ielts / gre / other 之一；\n"
    "- is_ad：整篇是否为广告/课程推广/引流软文（true/false），而非正常备考内容；\n"
    "- subject：科目，取 speaking / writing / reading / listening / vocab / grammar / general（综合/通用）之一；\n"
    "- content_type：内容类型，取 question（题目）/ sample_essay（范文）/ methodology（方法论技巧）"
    "/ experience（经验贴）/ vocabulary（词汇表）/ news（资讯政策）/ ad（广告）之一；\n"
    "- summary_title：为该内容生成一个简洁中文概括标题（10~20 字），只反映干货/主题，"
    "去掉引流、营销、感叹号等话术；若原标题已足够准确可直接沿用。\n\n"
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
    '  "exam": "toefl|ielts|gre|other",\n'
    '  "is_ad": false,\n'
    '  "subject": "speaking|writing|...|general",\n'
    '  "content_type": "question|sample_essay|...",\n'
    '  "summary_title": "简洁中文概括标题",\n'
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

_TAGS_SYSTEM = (
    "你是托福备考内容编辑。给定一段文档文本，只做「过滤 + 打标签」判断，"
    "不要抽取题目、不要分块。\n\n"
    "## 判断字段\n"
    "- exam：内容主要针对的考试，取 toefl / ielts / gre / other 之一；\n"
    "- is_ad：整篇是否为广告/课程推广/引流软文（true/false）；\n"
    "- subject：科目，取 speaking / writing / reading / listening / vocab / grammar / general（综合/通用）之一；\n"
    "- content_type：内容类型，取 question（题目）/ sample_essay（范文）/ methodology（方法论技巧）"
    "/ experience（经验贴）/ vocabulary（词汇表）/ news（资讯政策）/ ad（广告）之一；\n"
    "- summary_title：为该内容生成一个简洁中文概括标题（10~20 字），只反映干货/主题，"
    "去掉引流、营销、感叹号等话术；\n"
    "- reason：一句话判断理由。\n\n"
    "## 输出 JSON 结构（严格按此，只输出 JSON）\n"
    "{\n"
    '  "exam": "toefl|ielts|gre|other",\n'
    '  "is_ad": false,\n'
    '  "subject": "speaking|writing|...|general",\n'
    '  "content_type": "question|sample_essay|...",\n'
    '  "summary_title": "简洁中文概括标题",\n'
    '  "reason": "一句话理由"\n'
    "}\n"
)


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_CHARS else text[:_MAX_CHARS]


def _norm_exam(value: Any) -> str:
    return value if value in _EXAMS else "other"


def _norm_subject(value: Any) -> str:
    return value if value in _SUBJECTS else "general"


def _norm_content_type(value: Any) -> str:
    return value if value in _CONTENT_TYPES else ""


async def analyze_article(*, title: str, raw_text: str) -> dict[str, Any]:
    """判断文章归属 + 过滤标签 + 提取内容。

    返回 {category, reason, exam, is_ad, subject, content_type, items, chunks}。
    """
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
        "exam": _norm_exam(data.get("exam")),
        "is_ad": bool(data.get("is_ad")),
        "subject": _norm_subject(data.get("subject")),
        "content_type": _norm_content_type(data.get("content_type")),
        "summary_title": (data.get("summary_title") or "").strip(),
        "items": items,
        "chunks": chunks,
    }


async def analyze_tags(*, title: str, raw_text: str) -> dict[str, Any]:
    """轻量判断：只输出过滤标签（考试/广告/科目/类型），不抽题不分块。

    返回 {exam, is_ad, subject, content_type, reason}。
    """
    user = (
        f"## 文档标题\n{title or '(无标题)'}\n\n"
        f"## 文档正文（截断）\n{_truncate(raw_text)}\n\n"
        "请判断考试/广告/科目/类型标签。"
    )
    data = await chat_json(
        [
            {"role": "system", "content": _TAGS_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        timeout=60.0,
    )
    return {
        "exam": _norm_exam(data.get("exam")),
        "is_ad": bool(data.get("is_ad")),
        "subject": _norm_subject(data.get("subject")),
        "content_type": _norm_content_type(data.get("content_type")),
        "summary_title": (data.get("summary_title") or "").strip(),
        "reason": data.get("reason") or "",
    }
