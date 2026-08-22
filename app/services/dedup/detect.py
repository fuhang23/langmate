"""内容去重检测：基于 embedding 余弦相似度。

- detect_rag_duplicates：RAG chunk 级去重（与知识库已有 chunk 比较）。
- detect_question_duplicates：题目级去重（与题库已有题干比较，混合粒度）。
- sync_question_embeddings：确认入库后把新题题干向量写入缓存表。

判据：向量 L2 归一化后内积 = 余弦相似度。去重检测失败一律降级为
「不重复」，不阻断采集主流程（与现有 RAG 降级模式一致）。
"""

from __future__ import annotations

import os

import faiss
import numpy as np

from services.rag import embed_bailian
from services.dedup.question_embedding import QuestionEmbeddingStore

_DEFAULT_RAG_THRESHOLD = 0.95
_DEFAULT_QUESTION_THRESHOLD = 0.90


def _rag_threshold() -> float:
    try:
        return float(os.environ.get("DEDUP_RAG_THRESHOLD", str(_DEFAULT_RAG_THRESHOLD)))
    except ValueError:
        return _DEFAULT_RAG_THRESHOLD


def _question_threshold() -> float:
    try:
        return float(os.environ.get("DEDUP_QUESTION_THRESHOLD", str(_DEFAULT_QUESTION_THRESHOLD)))
    except ValueError:
        return _DEFAULT_QUESTION_THRESHOLD


def detect_rag_duplicates(
    chunks: list[str],
    source: str = "ingested-articles",
    threshold: float | None = None,
) -> list[dict]:
    """检测每个 chunk 是否与知识库已有 chunk 高度相似。

    返回与 chunks 顺序一致的 list[{duplicate: bool, similarity: float}]。
    相似度为余弦相似度（-1~1），duplicate 表示 similarity >= threshold。
    """
    threshold = threshold if threshold is not None else _rag_threshold()
    results = [{"duplicate": False, "similarity": 0.0} for _ in chunks]
    if not chunks:
        return results

    try:
        from services.rag.store import RagIndex, default_index_dir

        index = RagIndex.load(source, default_index_dir())
    except Exception:
        return results  # 索引不存在/损坏 → 全非重复

    try:
        vectors = embed_bailian.embed_texts(chunks)
    except Exception:
        return results

    for i, vec in enumerate(vectors):
        try:
            matches = index.search_with_scores(np.asarray(vec, dtype=np.float32), top_k=1)
        except Exception:
            continue
        if matches:
            sim = float(matches[0][1])
            results[i]["similarity"] = round(sim, 4)
            results[i]["duplicate"] = sim >= threshold
    return results


def _question_prompt(item: dict, category: str) -> str:
    """按 category 从 item 构造题干文本（混合粒度）。"""
    if category in ("writing_discussion", "writing_email"):
        return (item.get("prompt_en") or "").strip()
    if category == "speaking_repeat":
        sentences = item.get("sentences") or []
        return " ".join(
            (s.get("text") or "").strip()
            for s in sentences
            if (s.get("text") or "").strip()
        )
    if category == "speaking_interview":
        questions = item.get("questions") or []
        return " ".join(
            (q.get("prompt_en") or "").strip()
            for q in questions
            if (q.get("prompt_en") or "").strip()
        )
    return ""


def _backfill(category: str, qe: QuestionEmbeddingStore) -> None:
    """惰性回填：从题库把某 category 现有题目题干向量写入缓存表。"""
    try:
        from services.corpus import CorpusStore, default_corpus_db_path

        cs = CorpusStore(default_corpus_db_path())
        prompts = cs.iter_questions_for_dedup(category)
    except Exception:
        return
    if not prompts:
        return
    try:
        vectors = embed_bailian.embed_texts(prompts)
    except Exception:
        return
    for prompt, vec in zip(prompts, vectors):
        qe.upsert(category, prompt, vec)


def detect_question_duplicates(
    items: list[dict],
    category: str,
    threshold: float | None = None,
    exclude_prompt: str | None = None,
) -> list[dict]:
    """检测每个题目 item 是否与题库已有题高度相似。

    返回与 items 顺序一致的 list[{duplicate: bool, similarity: float}]。
    首次检测某 category 时若缓存为空，会从题库惰性回填题干向量。
    exclude_prompt：编辑场景传入被编辑题的旧题干文本，比对时排除自身，
    避免「与自己旧版本判重」。
    """
    threshold = threshold if threshold is not None else _question_threshold()
    results = [{"duplicate": False, "similarity": 0.0} for _ in items]
    if not items:
        return results

    prompts = [_question_prompt(it, category) for it in items]
    qe = QuestionEmbeddingStore()
    if qe.count_by_category(category) == 0:
        _backfill(category, qe)

    existing = qe.list_by_category(category)
    if exclude_prompt:
        existing = [e for e in existing if e["prompt_text"] != exclude_prompt]
    if not existing:
        return results

    try:
        new_vecs = np.asarray(embed_bailian.embed_texts(prompts), dtype=np.float32)
    except Exception:
        return results
    faiss.normalize_L2(new_vecs)

    existing_mat = np.asarray([e["embedding"] for e in existing], dtype=np.float32)
    faiss.normalize_L2(existing_mat)

    sims = new_vecs @ existing_mat.T  # (n_new, n_existing)，内积即余弦相似度
    for i in range(len(items)):
        if not prompts[i] or sims.shape[1] == 0:
            continue
        max_sim = float(sims[i].max())
        results[i]["similarity"] = round(max_sim, 4)
        results[i]["duplicate"] = max_sim >= threshold
    return results


def sync_question_embeddings(items: list[dict], category: str) -> None:
    """确认入库成功后，把新题题干向量写入缓存表（供后续去重复用）。"""
    prompts = [_question_prompt(it, category) for it in items]
    valid = [p for p in prompts if p]
    if not valid:
        return
    try:
        vectors = embed_bailian.embed_texts(valid)
    except Exception:
        return
    qe = QuestionEmbeddingStore()
    for prompt, vec in zip(valid, vectors):
        qe.upsert(category, prompt, vec)
