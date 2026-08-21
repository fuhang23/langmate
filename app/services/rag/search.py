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
