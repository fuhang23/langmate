"""手动录题编排：校验 → 自动断句 → 转 items → 去重 → 入库 → 同步向量。"""

from __future__ import annotations

from typing import Any

from services.dedup import detect_question_duplicates, sync_question_embeddings

VALID_CATEGORIES = (
    "speaking_repeat",
    "speaking_interview",
    "writing_email",
    "writing_discussion",
)


def to_items(category: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把表单 payload 转成 corpus.add_* / dedup 需要的 items 结构（单个 item）。"""
    if category in ("writing_email", "writing_discussion"):
        task_type = "email" if category == "writing_email" else "discussion"
        return [
            {
                "task_type": task_type,
                "title": (payload.get("title") or "").strip(),
                "prompt_en": (payload.get("prompt_en") or "").strip(),
                "prompt_zh": (payload.get("prompt_zh") or "").strip(),
                "reference_answer": (payload.get("reference_answer") or "").strip(),
            }
        ]

    if category == "speaking_repeat":
        sentences: list[dict[str, Any]] = []
        for i, s in enumerate(payload.get("sentences") or []):
            text = (s.get("text") or "").strip()
            if not text:
                continue
            chunks = s.get("chunks") or []
            if isinstance(chunks, str):
                chunks = [c.strip() for c in chunks.split("/") if c.strip()]
            sentences.append({"seq": i + 1, "text": text, "chunks": chunks})
        return [{"title": (payload.get("title") or "").strip(), "sentences": sentences}]

    if category == "speaking_interview":
        questions: list[dict[str, Any]] = []
        for i, q in enumerate(payload.get("questions") or []):
            prompt_en = (q.get("prompt_en") or "").strip()
            if not prompt_en:
                continue
            core = q.get("core_expressions") or []
            if isinstance(core, str):
                core = [core]
            questions.append(
                {
                    "seq": i + 1,
                    "prompt_en": prompt_en,
                    "prompt_zh": (q.get("prompt_zh") or "").strip(),
                    "reference_answer": (q.get("reference_answer") or "").strip(),
                    "core_expressions": core,
                }
            )
        return [{"title": (payload.get("title") or "").strip(), "questions": questions}]

    return []


def validate(category: str, items: list[dict[str, Any]]) -> str | None:
    """校验必填字段与数量，返回错误信息；通过返回 None。"""
    if not items:
        return "缺少题目内容"
    item = items[0]
    if category == "speaking_repeat":
        if not item["title"]:
            return "缺少场景标题"
        if len(item["sentences"]) < 1:
            return "听后复述至少需要 1 句"
    elif category == "speaking_interview":
        if not item["title"]:
            return "缺少主题标题"
        if len(item["questions"]) < 1:
            return "互动面试至少需要 1 题"
    else:
        if not item["title"]:
            return "缺少标题"
        if not item["prompt_en"]:
            return "缺少题目（prompt_en）"
    return None


async def add_manual_question(
    category: str,
    payload: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    """手动录入一道题/一组题：校验 + 断句 + 去重 + 入库 + 同步向量。

    返回：
    - {"status": "added", "questions": int}：入库成功（questions 为实际新增条数）
    - {"status": "duplicate", "similarity": float}：语义重复且未 force（不入库）
    - {"status": "exists", "message": str}：同标题题目已存在，title 幂等跳过（不入库）
    - {"status": "invalid", "message": str}：表单校验失败（不入库）
    """
    if category not in VALID_CATEGORIES:
        raise RuntimeError(f"未知题型: {category}")

    items = to_items(category, payload)

    # 听后复述：空 chunks 自动按意群断句（可选，失败降级为整句）。
    if category == "speaking_repeat" and items:
        from services.manual.generate import chunk_sentences

        sentences = items[0]["sentences"]
        need = [s for s in sentences if not s["chunks"]]
        if need:
            chunks_list = await chunk_sentences([s["text"] for s in need])
            for s, cs in zip(need, chunks_list):
                s["chunks"] = cs

    err = validate(category, items)
    if err:
        return {"status": "invalid", "message": err}

    # 去重检测（单个 item）。
    marks = detect_question_duplicates(items, category)
    if marks and marks[0].get("duplicate") and not force:
        return {"status": "duplicate", "similarity": marks[0].get("similarity", 0.0)}

    # 入库（复用 corpus.add_* 幂等方法；返回实际插入的子集）。
    from services.corpus import CorpusStore, default_corpus_db_path

    cs = CorpusStore(default_corpus_db_path())
    if category in ("writing_email", "writing_discussion"):
        inserted = cs.add_writing_questions(items)
    elif category == "speaking_repeat":
        inserted = cs.add_speaking_repeat(items)
    else:
        inserted = cs.add_speaking_interview(items)

    if not inserted:
        # title 幂等跳过：库中已有同标题题目，本次未入库（不能误报成功，
        # 也不能给未入库的题写向量缓存 → 幽灵向量）。
        return {"status": "exists", "message": "已存在同标题的题目，未重复入库"}

    # 同步题干向量（只对实际入库的题目，供后续去重复用）。
    sync_question_embeddings(inserted, category)

    return {"status": "added", "questions": len(inserted)}
