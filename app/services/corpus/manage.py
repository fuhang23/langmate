"""题库管理编排：四种题型的删除与更新（物理删除 + 同步清理去重向量缓存）。

四种题型：speaking_repeat（听后复述）/ speaking_interview（互动面试）/
writing_email（邮件写作）/ writing_discussion（学术讨论写作）。

与 services.manual.add（手动录题）共用 items 结构与校验逻辑；
删除/更新后同步维护 dedup.db 的题干向量缓存，避免残留向量误判。
"""

from __future__ import annotations

from typing import Any

from services.dedup import detect_question_duplicates, sync_question_embeddings
from services.dedup.detect import _question_prompt
from services.dedup.question_embedding import QuestionEmbeddingStore
from services.manual.add import VALID_CATEGORIES, to_items, validate


def _get_old_item(cs, category: str, question_id: int) -> dict[str, Any] | None:
    """取旧题目并转成与 to_items 同构的 item（用于构造旧题干文本）。"""
    if category == "speaking_repeat":
        sc = cs.get_scenario(question_id)
        if sc is None:
            return None
        return {
            "title": sc.title,
            "context_prompt": sc.context_prompt,
            "sentences": [
                {"seq": s.seq, "text": s.text, "chunks": s.chunks}
                for s in sc.sentences
            ],
        }
    if category == "speaking_interview":
        tp = cs.get_interview_topic(question_id)
        if tp is None:
            return None
        return {
            "title": tp.title,
            "description": tp.description,
            "questions": [
                {
                    "seq": q.seq,
                    "prompt_en": q.prompt_en,
                    "prompt_zh": q.prompt_zh,
                    "reference_answer": q.reference_answer,
                    "core_expressions": q.core_expressions,
                }
                for q in tp.questions
            ],
        }
    # writing_email / writing_discussion
    wq = cs.get_writing_question(question_id)
    if wq is None:
        return None
    return {
        "task_type": wq.task_type,
        "title": wq.title,
        "prompt_en": wq.prompt_en,
        "prompt_zh": wq.prompt_zh,
        "reference_answer": wq.reference_answer,
    }


def _clean_embedding(category: str, prompt_text: str) -> None:
    """清理题干向量缓存（失败降级，不阻断主流程）。"""
    if not prompt_text:
        return
    try:
        QuestionEmbeddingStore().delete_by_prompt(category, prompt_text)
    except Exception:
        pass


async def delete_question(category: str, question_id: int) -> dict[str, Any]:
    """删除一道题/一组题（物理删除），并同步清理题干向量缓存。

    返回：
    - {"status": "deleted"}：删除成功
    - {"status": "not_found"}：题目不存在
    - {"status": "invalid_category"}：非法题型
    """
    if category not in VALID_CATEGORIES:
        return {"status": "invalid_category"}

    from services.corpus import CorpusStore, default_corpus_db_path

    cs = CorpusStore(default_corpus_db_path())

    old_item = _get_old_item(cs, category, question_id)
    if old_item is None:
        return {"status": "not_found"}

    if category == "speaking_repeat":
        deleted = cs.delete_repeat_scenario(question_id)
    elif category == "speaking_interview":
        deleted = cs.delete_interview_topic(question_id)
    else:
        deleted = cs.delete_writing_question(question_id)
    if not deleted:
        return {"status": "not_found"}

    # 清理题干向量缓存（失败降级）。
    _clean_embedding(category, _question_prompt(old_item, category))
    return {"status": "deleted"}


async def update_question(
    category: str,
    question_id: int,
    payload: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    """更新一道题/一组题（表单结构与手动录题一致），同步维护去重向量缓存。

    返回：
    - {"status": "updated"}：更新成功
    - {"status": "duplicate", "similarity": float}：与库内其他题重复且未 force
    - {"status": "invalid", "message": str}：表单校验失败（不更新）
    - {"status": "not_found"}：题目不存在
    - {"status": "invalid_category"}：非法题型
    """
    if category not in VALID_CATEGORIES:
        return {"status": "invalid_category"}

    from services.corpus import CorpusStore, default_corpus_db_path

    cs = CorpusStore(default_corpus_db_path())

    old_item = _get_old_item(cs, category, question_id)
    if old_item is None:
        return {"status": "not_found"}

    items = to_items(category, payload)

    # 听后复述：空 chunks 自动按意群断句（与手动录题一致，失败降级为整句）。
    if category == "speaking_repeat" and items:
        from services.manual.generate import chunk_sentences

        sentences = items[0]["sentences"]
        need = [s for s in sentences if not s["chunks"]]
        if need:
            chunks_list = await chunk_sentences([s["text"] for s in need])
            for s, cs_chunks in zip(need, chunks_list):
                s["chunks"] = cs_chunks

    err = validate(category, items)
    if err:
        return {"status": "invalid", "message": err}

    # 去重检测（排除自身旧题干，避免与自己旧版本判重）。
    old_prompt = _question_prompt(old_item, category)
    marks = detect_question_duplicates(items, category, exclude_prompt=old_prompt)
    if marks and marks[0].get("duplicate") and not force:
        return {"status": "duplicate", "similarity": marks[0].get("similarity", 0.0)}

    item = items[0]
    if category == "speaking_repeat":
        updated = cs.update_repeat_scenario(
            question_id,
            item["title"],
            (payload.get("context_prompt") or "").strip(),
            item["sentences"],
        )
    elif category == "speaking_interview":
        updated = cs.update_interview_topic(
            question_id,
            item["title"],
            (payload.get("description") or "").strip(),
            item["questions"],
        )
    else:
        updated = cs.update_writing_question(
            question_id,
            item["task_type"],
            item["title"],
            item["prompt_en"],
            item.get("prompt_zh", ""),
            item.get("reference_answer", ""),
        )
    if not updated:
        return {"status": "not_found"}

    # 同步向量缓存：清旧题干 + 写新题干（均失败降级）。
    _clean_embedding(category, old_prompt)
    try:
        sync_question_embeddings(items, category)
    except Exception:
        pass
    return {"status": "updated"}
