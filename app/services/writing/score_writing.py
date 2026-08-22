"""托福写作判分：纯文本 LLM 判分（无音频轨）。

一次 LLM 调用同时输出：
1. overall_score：整体 0-5 分（严格按 ETS 官方 rubric）；
2. dimension_comments：按 rubric 隐含维度的描述性点评（引用 rubric 原文）；
3. grammar_corrections：逐句语法批改（原句/修改/说明）；
4. useful_expressions：从参考范文提取的地道表达（含中文释义+例句）。

判分时：rubric 全文注入 system prompt（结构化，不走 RAG）；
用户知识库（ingested-articles，subject=writing）走 RAG 检索，增强教学法反馈。
"""

from __future__ import annotations

from typing import Any

from services.llm.deepseek import chat_json
from services.progress import PracticeRecord, ProgressStore, default_db_path
from services.writing.rubrics import rubric_for


def _cefr_from_score(score: int) -> str:
    """写作 0-5 分 → CEFR 级别（对齐官方：5=C1、4=B2、3=B1、2=A2、1=A1）。"""
    mapping = {5: "C1", 4: "B2", 3: "B1", 2: "A2", 1: "A1"}
    return mapping.get(score, "")


def _dimension_names(dimensions: list[dict[str, str]]) -> str:
    return "\n".join(f"{i+1}. {d['en']}（{d['label']}）" for i, d in enumerate(dimensions))


def _format_teaching_chunks(chunks: list[Any]) -> str:
    if not chunks:
        return "（无额外官方教学法材料）"
    return "\n\n".join(f"{c.source_label()}\n{c.text[:600]}" for c in chunks)


def _system_prompt(rubric: dict[str, Any], teaching: str) -> str:
    dims = _dimension_names(rubric["dimensions"])
    return (
        "你是托福写作评分考官，严格对标 ETS 官方评分标准。\n\n"
        f"## 题型\n{rubric['task_label']}\n\n"
        f"## ETS 官方评分标准（必须作为唯一打分依据）\n{rubric['text']}\n\n"
        f"## 官方教学法材料（可用于增强反馈，可引用来源）\n{teaching}\n\n"
        f"## 评分维度（整体评分，不拆维度分，但点评要覆盖这些维度）\n{dims}\n\n"
        "## 输出要求\n"
        "严格按以下 JSON 结构输出，只输出 JSON，不要输出任何其他文字：\n"
        '{\n'
        '  "overall_score": 0到5的整数（严格按 rubric 判定，0=空白/跑题/非英文/照抄）,\n'
        '  "dimension_comments": [\n'
        '    {"dimension": "维度英文名", "comment": "一句中文点评，指出该维度的表现与问题", '
        '"rubric_ref": "引用对应分数段的 rubric 原文一句"}\n'
        '  ],\n'
        '  "grammar_corrections": [\n'
        '    {"original": "学生原文中的错误句", "correction": "修改后的正确句", '
        '"explanation": "一句中文说明错在哪、为什么改"}\n'
        '  ],\n'
        '  "useful_expressions": [\n'
        '    {"expression": "从参考范文提取的地道表达/高分句型", '
        '"translation": "中文释义", "example": "含该表达的范文原句"}\n'
        '  ]\n'
        '}\n\n'
        "注意事项：\n"
        "1. overall_score 必须按 rubric 判定，不得随意给分。\n"
        "2. dimension_comments 覆盖所有评分维度，每条的 rubric_ref 必须原文引用对应分数段描述。\n"
        "3. grammar_corrections 只挑学生作文里真实存在的语法/用词错误，最多 5 条；"
        "没有错误则返回空数组。\n"
        "4. useful_expressions 从参考范文中提取 3-5 个最有价值的表达（不要从学生作文提取）。\n"
        "5. 所有 comment/explanation/translation 用中文。"
    )


def _user_prompt(prompt_en: str, reference_answer: str, student_text: str) -> str:
    return (
        f"## 写作题目\n{prompt_en}\n\n"
        f"## 学生作文\n{student_text}\n\n"
        f"## 参考范文（仅用于提取地道表达，不参与判分）\n{reference_answer}\n\n"
        "请按 JSON 格式输出判分结果。"
    )


def _record_progress(
    task_type: str,
    overall_score: int,
    weak_dimensions: list[str],
    question_key: str = "",
) -> None:
    try:
        record = PracticeRecord(
            section="writing",
            question_type=task_type,
            scores={"overall": overall_score},
            cefr=_cefr_from_score(overall_score),
            weak_points=weak_dimensions,
            question_key=question_key,
        )
        ProgressStore(default_db_path()).add_record(record)
    except Exception:
        pass  # 写进度失败不阻断判分


async def score_writing(
    *,
    task_type: str,
    prompt_en: str,
    reference_answer: str,
    student_text: str,
    question_id: int = 0,
) -> dict[str, Any]:
    """判分一次写作作答。

    Args:
        task_type: "email" 或 "discussion"。
        prompt_en: 完整英文题目（邮件含任务清单；讨论含教授+两学生回帖）。
        reference_answer: 参考范文（仅用于提取地道表达）。
        student_text: 学生写的作文。
        question_id: 写作题 id（>0 时题目级练习统计记为 "writing:{question_id}"）。

    Returns:
        判分结果 dict：overall_score / dimension_comments / grammar_corrections /
        useful_expressions / cefr。

    Raises:
        ValueError: task_type 未知或 student_text 为空。
    """
    rubric = rubric_for(task_type)
    if rubric is None:
        raise ValueError(f"未知写作题型: {task_type}")
    if not student_text or not student_text.strip():
        raise ValueError("student_text 为空")

    # RAG 检索用户知识库（写作相关，失败降级为空，不阻断）。
    teaching_chunks: list[Any] = []
    try:
        from services.ingest import search_knowledge_base

        teaching_chunks = search_knowledge_base(
            query=f"{rubric['task_label']} {prompt_en[:200]}",
            subject="writing",
            top_k=2,
        )
    except Exception:
        pass
    teaching = _format_teaching_chunks(teaching_chunks)

    data = await chat_json(
        [
            {"role": "system", "content": _system_prompt(rubric, teaching)},
            {"role": "user", "content": _user_prompt(prompt_en, reference_answer, student_text)},
        ],
        temperature=0.2,
        timeout=60.0,
    )

    overall_score = data.get("overall_score")
    try:
        overall_score = max(0, min(5, int(overall_score)))
    except (TypeError, ValueError):
        overall_score = 0

    dimension_comments = data.get("dimension_comments") or []
    if not isinstance(dimension_comments, list):
        dimension_comments = []
    grammar_corrections = data.get("grammar_corrections") or []
    if not isinstance(grammar_corrections, list):
        grammar_corrections = []
    useful_expressions = data.get("useful_expressions") or []
    if not isinstance(useful_expressions, list):
        useful_expressions = []

    # 薄弱维度：从 dimension_comments 里简单提取维度名（供进度画像）。
    weak_dimensions = [
        str(c.get("dimension", "")) for c in dimension_comments if c.get("dimension")
    ]

    _record_progress(
        task_type,
        overall_score,
        weak_dimensions,
        question_key=f"writing:{question_id}" if question_id > 0 else "",
    )

    return {
        "overall_score": overall_score,
        "cefr": _cefr_from_score(overall_score),
        "dimension_comments": dimension_comments,
        "grammar_corrections": grammar_corrections,
        "useful_expressions": useful_expressions,
        "teaching_sources": [c.source_label() for c in teaching_chunks],
    }
