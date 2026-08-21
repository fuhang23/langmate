"""统一检索接口：query → 百炼向量化 → faiss 余弦检索 → 返回 Chunk 列表。"""

from __future__ import annotations

import numpy as np

from services.rag import embed_bailian
from services.rag.schema import Chunk
from services.rag.store import RagIndex, default_index_dir


def rag_search(
    query: str,
    source: str = "lesson-plan-writing",
    top_k: int = 3,
    index_dir: str | None = None,
) -> list[Chunk]:
    """检索与 query 最相关的官方资料片段。

    任何一步失败（索引未建 / 未配 key / 网络异常）都降级为空列表，
    不阻断判分主流程。
    """
    try:
        index = RagIndex.load(source, index_dir or default_index_dir())
        vec = embed_bailian.embed_one(query)
        return index.search(np.asarray(vec, dtype=np.float32), top_k=top_k)
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
    try:
        index = RagIndex.load(source, index_dir)
        index.append(np.asarray(vectors, dtype=np.float32), chunks)
    except FileNotFoundError:
        index = RagIndex(source, np.asarray(vectors, dtype=np.float32), chunks)
    index.save(index_dir)
    return len(index.chunks)
