"""ETS 官方写作评分标准（2025 版，覆盖 2026 改革后两个新题型）。

从 writing-rubrics.pdf 提取。判分时按题型把对应 rubric 全文注入 system
prompt，不运行时解析 PDF、不向量化（与 RAG 长文档检索分开）。
"""

from __future__ import annotations

# 两个题型共同的 0 分描述。
_ZERO_BAND = (
    "Score 0: The response is blank, rejects the topic, is not in English, "
    "is entirely copied from the prompt, is entirely unconnected to the prompt, "
    "or consists of arbitrary keystrokes."
)

# 写邮件（Write an Email）0-5 分 holistic rubric。
EMAIL_RUBRIC_TEXT = f"""Write an Email — Scoring Guide (0-5):

Score 5 — A fully successful response:
The response is effective, is clearly expressed, and shows consistent facility in the use of language.
• Elaboration that effectively supports the communicative purpose
• Effective syntactic variety and precise, idiomatic word choice
• Consistent use of appropriate social conventions (e.g., politeness, register, organization of information and formulation of actions such as requests, refusals, criticisms, etc.)
• Almost no lexical or grammatical errors other than those expected from a competent writer writing under timed conditions (e.g., common typos or common misspellings or substitutions like there/their)

Score 4 — A generally successful response:
The response is mostly effective and easily understood. Language facility is adequate to the task.
• Adequate elaboration to support the communicative purpose
• Syntactic variety and appropriate word choice
• Mostly appropriate social conventions
• Few lexical or grammatical errors

Score 3 — A partially successful response:
The response generally accomplishes the task. Limitations in language facility may prevent parts of the message from being fully clear and effective.
• Elaboration that partially supports the communicative purpose
• A moderate range of syntax and vocabulary
• Some noticeable errors in structure, word forms, use of idiomatic language and/or social conventions

Score 2 — A mostly unsuccessful response:
The response reflects an attempt to address the task, but it is mostly ineffective. The message may be limited or difficult to interpret.
• Limited or irrelevant elaboration
• Some connected sentence-level language, with a limited range of syntax and vocabulary
• An accumulation of errors in sentence structure and/or language use

Score 1 — An unsuccessful response:
The response reflects an ineffective attempt to address the task. The message may be limited to the point of being unintelligible.
• Very little elaboration, if any
• Telegraphic language (i.e., short and/or disconnected phrases and sentences) with a very limited range of vocabulary
• Serious and frequent errors in the use of language
• Minimal original language; any coherent language is mostly borrowed from the stimulus

{_ZERO_BAND}"""

# 学术讨论（Write for an Academic Discussion）0-5 分 holistic rubric。
DISCUSSION_RUBRIC_TEXT = f"""Write for an Academic Discussion — Scoring Guide (0-5):

Score 5 — A fully successful response:
The response is a relevant and very clearly expressed contribution to the online discussion, and it demonstrates consistent facility in the use of language.
• Relevant and well-elaborated explanations, exemplifications and/or details
• Effective use of a variety of syntactic structures and precise, idiomatic word choice
• Almost no lexical or grammatical errors other than those expected from a competent writer writing under timed conditions (e.g., common typos or common misspellings or substitutions like there/their)

Score 4 — A generally successful response:
The response is a relevant contribution to the online discussion, and facility in the use of language allows the writer's ideas to be easily understood.
• Relevant and adequately elaborated explanations, exemplifications and/or details
• A variety of syntactic structures and appropriate word choice
• Few lexical or grammatical errors

Score 3 — A partially successful response:
The response is a mostly relevant and mostly understandable contribution to the online discussion, and there is some facility in the use of language.
• Elaboration in which part of an explanation, example or detail may be missing, unclear or irrelevant
• Some variety in syntactic structures and a range of vocabulary
• Some noticeable lexical and grammatical errors in sentence structure, word form or use of idiomatic language

Score 2 — A mostly unsuccessful response:
The response reflects an attempt to contribute to the online discussion, but limitations in the use of language may make ideas hard to follow.
• Ideas that may be poorly elaborated or only partially relevant
• A limited range of syntactic structures and vocabulary
• An accumulation of errors in sentence structure, word forms or use

Score 1 — An unsuccessful response:
The response reflects an ineffective attempt to contribute to the online discussion, and limitations in the use of language may prevent the expression of ideas.
• Words and phrases that indicate an attempt to address the task, but with few or no coherent ideas
• Severely limited range of syntactic structures and vocabulary
• Serious and frequent errors in the use of language
• Minimal original language; any coherent language is mostly borrowed from the stimulus

{_ZERO_BAND}"""

# 判分时的分维度反馈维度（供 LLM 输出 dimension_comments 时对齐）。
EMAIL_DIMENSIONS = [
    {"key": "elaboration", "label": "详述充分度", "en": "elaboration"},
    {"key": "syntax_variety", "label": "句式多样", "en": "syntactic variety"},
    {"key": "word_choice", "label": "用词精确", "en": "word choice"},
    {"key": "social_conventions", "label": "社交得体性", "en": "social conventions (politeness/register/organization)"},
    {"key": "errors", "label": "词汇语法错误量", "en": "lexical and grammatical errors"},
]

DISCUSSION_DIMENSIONS = [
    {"key": "relevance", "label": "观点相关性", "en": "relevance"},
    {"key": "elaboration", "label": "详述与例证", "en": "elaboration, exemplifications and details"},
    {"key": "syntax", "label": "句式结构", "en": "syntactic structures"},
    {"key": "word_choice", "label": "用词", "en": "word choice"},
    {"key": "errors", "label": "词汇语法错误量", "en": "lexical and grammatical errors"},
]

# 汇总表：判分层按 task_type 取用。
RUBRICS: dict[str, dict[str, object]] = {
    "email": {
        "task_label": "Write an Email",
        "text": EMAIL_RUBRIC_TEXT,
        "dimensions": EMAIL_DIMENSIONS,
    },
    "discussion": {
        "task_label": "Write for an Academic Discussion",
        "text": DISCUSSION_RUBRIC_TEXT,
        "dimensions": DISCUSSION_DIMENSIONS,
    },
}


def rubric_for(task_type: str) -> dict[str, object] | None:
    """返回某题型的 rubric 配置；未知题型返回 None。"""
    return RUBRICS.get(task_type)
