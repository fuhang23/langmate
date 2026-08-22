"""统一检索接口：query → 百炼向量化 → faiss 余弦检索 → 返回 Chunk 列表。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from services.rag import embed_bailian
from services.rag.schema import Chunk
from services.rag.store import RagIndex, default_index_dir


def _subject_matches(chunk: Chunk, subject: str) -> bool:
    """宽松匹配：meta.subject 为空（旧数据）/ general / 等于目标 subject 均保留。"""
    meta = chunk.meta or {}
    s = meta.get("subject", "")
    return not s or s == "general" or s == subject


def rag_search(
    query: str,
    source: str = "lesson-plan-writing",
    top_k: int = 3,
    index_dir: str | None = None,
    subject: str | None = None,
) -> list[Chunk]:
    """检索与 query 最相关的资料片段，可选的按 subject 过滤。

    任何一步失败（索引未建 / 未配 key / 网络异常）都降级为空列表，
    不阻断判分主流程。
    """
    try:
        index = RagIndex.load(source, index_dir or default_index_dir())
        vec = embed_bailian.embed_one(query)
        search_k = top_k if subject is None else max(top_k * 5, top_k)
        chunks = index.search(np.asarray(vec, dtype=np.float32), top_k=search_k)
        if subject is not None:
            chunks = [c for c in chunks if _subject_matches(c, subject)][:top_k]
        return chunks
    except Exception:
        return []


def rag_append(
    source: str,
    chunks: list[Chunk],
    index_dir: str | None = None,
) -> int:
    """向某 source 追加 chunk（faiss 增量，不存在则新建）。返回追加后 chunk 总数。

    与 rag_search 不同，本函数失败会向上抛异常（内容采集确认入库时应感知失败）。
    """
    index_dir = index_dir or default_index_dir()
    vectors = embed_bailian.embed_texts([c.text for c in chunks])
    mat = np.asarray(vectors, dtype=np.float32)
    if mat.ndim != 2 or mat.shape[0] != len(chunks):
        raise RuntimeError(f"embedding 数量与 chunk 数量不一致: {mat.shape[0]} != {len(chunks)}")
    try:
        index = RagIndex.load(source, index_dir)
        index.append(mat, chunks)
    except FileNotFoundError:
        # 仅在「索引完全不存在」时新建；部分文件缺失由 load 抛 RuntimeError，
        # 不会被这里吞掉，从而避免静默覆盖。
        index = RagIndex(source, mat, chunks)
    index.save(index_dir)
    return len(index.chunks)


def rag_rebuild(
    source: str,
    chunks: list[Chunk],
    index_dir: str | None = None,
) -> int:
    """全量重建某 source 的向量索引（覆盖旧索引）。返回重建后的 chunk 总数。

    chunks 为空时删除该 source 的索引文件（faiss 只增难删，删除走全量重建）。
    失败向上抛异常（知识库删除时应感知失败）。
    """
    index_dir = Path(index_dir or default_index_dir())
    if not chunks:
        for suffix in (".faiss", ".json"):
            p = index_dir / f"{source}{suffix}"
            if p.exists():
                p.unlink()
        return 0

    vectors = embed_bailian.embed_texts([c.text for c in chunks])
    mat = np.asarray(vectors, dtype=np.float32)
    if mat.ndim != 2 or mat.shape[0] != len(chunks):
        raise RuntimeError(f"embedding 数量与 chunk 数量不一致: {mat.shape[0]} != {len(chunks)}")
    index = RagIndex(source, mat, chunks)
    index.save(index_dir)
    return len(index.chunks)
