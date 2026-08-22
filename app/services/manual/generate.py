"""手动录题的 AI 辅助：参考内容生成 + 听后复述意群自动断句。

均为可选能力，由前端按钮触发，失败由调用方降级处理。
"""

from __future__ import annotations

from typing import Any

from services.llm.deepseek import chat_json


async def generate_reference(category: str, payload: dict[str, Any]) -> dict[str, Any]:
    """按题型生成参考内容（范文 / 参考回答 + 核心表达）。

    返回：
    - writing（email/discussion）：{"reference_answer": str}
    - speaking_interview：{"reference_answers": [str], "core_expressions": [[str]]}
    """
    if category in ("writing_email", "writing_discussion"):
        return await _generate_writing(category, payload)
    if category == "speaking_interview":
        return await _generate_interview(payload)
    return {}


async def _generate_writing(category: str, payload: dict[str, Any]) -> dict[str, Any]:
    prompt_en = (payload.get("prompt_en") or "").strip()
    if not prompt_en:
        return {}
    task = "Write an Email" if category == "writing_email" else "Write for an Academic Discussion"
    system = "你是托福写作评分专家，请根据题目写一篇高分参考范文（英文）。"
    user = (
        f"题型：{task}\n"
        f"题目：\n{prompt_en}\n\n"
        "请写一篇参考范文（邮件约 120 词，学术讨论约 100~150 词），"
        "只输出 JSON：{\"reference_answer\": \"范文全文\"}"
    )
    data = await chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.5,
        timeout=60.0,
    )
    return {"reference_answer": (data.get("reference_answer") or "").strip()}


async def _generate_interview(payload: dict[str, Any]) -> dict[str, Any]:
    questions = payload.get("questions") or []
    prompts = [(q.get("prompt_en") or "").strip() for q in questions if (q.get("prompt_en") or "").strip()]
    if not prompts:
        return {}
    system = "你是托福口语老师，请为每个面试题写参考回答并提炼核心表达。"
    user = (
        "面试题：\n"
        + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(prompts))
        + "\n\n请为每题写 reference_answer（45 秒口语参考回答，约 90~120 词）"
        "和 core_expressions（3~5 个核心表达词组）。"
        "只输出 JSON：{\"items\": [{\"reference_answer\": \"...\", \"core_expressions\": [\"...\"]}]}"
    )
    data = await chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.5,
        timeout=60.0,
    )
    items = data.get("items") or []
    return {
        "reference_answers": [(it.get("reference_answer") or "").strip() for it in items],
        "core_expressions": [it.get("core_expressions") or [] for it in items],
    }


async def chunk_sentences(sentences: list[str]) -> list[list[str]]:
    """把每个英文句子按意群切分，返回与输入对齐的 chunks 数组。

    失败或无法切分的句子降级为整句（单 chunk）。
    """
    cleaned = [s.strip() for s in sentences if s and s.strip()]
    if not cleaned:
        return []
    system = "你是托福口语老师。请把每个英文句子按意群（sense group）切分，用于跟读复述的节奏标注。"
    user = (
        "句子列表：\n"
        + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(cleaned))
        + "\n\n请把每句按意群切分成若干片段（保持原词序，不增删改单词）。"
        "只输出 JSON：{\"chunks\": [[\"片段\", \"片段\"], ...]}"
    )
    try:
        data = await chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            timeout=60.0,
        )
    except Exception:
        return [[s] for s in cleaned]
    chunks = data.get("chunks") or []
    result: list[list[str]] = []
    for i, s in enumerate(cleaned):
        if i < len(chunks) and isinstance(chunks[i], list):
            parts = [str(c).strip() for c in chunks[i] if str(c).strip()]
            result.append(parts if parts else [s])
        else:
            result.append([s])
    return result
