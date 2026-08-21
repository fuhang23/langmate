"""向量索引本地存储与检索（faiss IndexFlatIP）。

向量先做 L2 归一化（faiss.normalize_L2），使内积等于余弦相似度。
文件布局：<index_dir>/<source>.faiss（向量索引）+ <source>.json（chunk 元数据）。
chunk 规模小（几十到几百条），IndexFlatIP 暴力检索已足够快。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import faiss
import numpy as np

from services.rag.schema import Chunk


def default_index_dir() -> Path:
    env = os.environ.get("FAISS_INDEX_DIR")
    if env:
        return Path(env)
    return Path("data") / "rag" / "index"


class RagIndex:
    """单个文档源的向量索引（faiss 索引 + chunk 元数据）。"""

    def __init__(self, source: str, vectors: np.ndarray, chunks: list[Chunk]) -> None:
        self.source = source
        self.chunks = chunks
        # vectors: shape (n, dim)，float32，已 L2 归一化。
        mat = np.asarray(vectors, dtype=np.float32)
        faiss.normalize_L2(mat)
        self.index = faiss.IndexFlatIP(mat.shape[1])
        self.index.add(mat)

    def search(self, query_vec: np.ndarray, top_k: int = 3) -> list[Chunk]:
        """返回与 query 向量最相似的 top_k 个 chunk（按相似度降序）。"""
        if len(self.chunks) == 0 or self.index.ntotal == 0:
            return []
        q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(q)
        top_k = min(top_k, len(self.chunks))
        _, labels = self.index.search(q, top_k)
        return [self.chunks[int(i)] for i in labels[0] if i >= 0]

    def save(self, index_dir: str | Path) -> None:
        index_dir = Path(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_dir / f"{self.source}.faiss"))
        payload = [c.to_dict() for c in self.chunks]
        (index_dir / f"{self.source}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, source: str, index_dir: str | Path) -> "RagIndex":
        index_dir = Path(index_dir)
        idx_path = index_dir / f"{source}.faiss"
        meta_path = index_dir / f"{source}.json"
        if not idx_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"索引不存在: {source}（先运行 ingest）")
        index = faiss.read_index(str(idx_path))
        chunks = [Chunk.from_dict(d) for d in json.loads(meta_path.read_text(encoding="utf-8"))]
        obj = cls.__new__(cls)
        obj.source = source
        obj.chunks = chunks
        obj.index = index
        return obj
