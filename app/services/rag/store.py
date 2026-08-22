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

    def append(self, vectors: np.ndarray, chunks: list[Chunk]) -> None:
        """追加新向量与 chunk（faiss index.add 增量追加，不重建已有向量）。"""
        if len(chunks) == 0:
            return
        mat = np.asarray(vectors, dtype=np.float32)
        faiss.normalize_L2(mat)
        self.index.add(mat)
        self.chunks.extend(chunks)

    def save(self, index_dir: str | Path) -> None:
        index_dir = Path(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss_path = index_dir / f"{self.source}.faiss"
        meta_path = index_dir / f"{self.source}.json"
        # 先写临时文件再原子重命名，避免中途崩溃导致索引与元数据损坏/不一致。
        tmp_faiss = index_dir / f"{self.source}.faiss.tmp"
        tmp_meta = index_dir / f"{self.source}.json.tmp"
        faiss.write_index(self.index, str(tmp_faiss))
        payload = [c.to_dict() for c in self.chunks]
        tmp_meta.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_faiss, faiss_path)
        os.replace(tmp_meta, meta_path)

    @classmethod
    def load(cls, source: str, index_dir: str | Path) -> "RagIndex":
        index_dir = Path(index_dir)
        idx_path = index_dir / f"{source}.faiss"
        meta_path = index_dir / f"{source}.json"
        idx_exists = idx_path.exists()
        meta_exists = meta_path.exists()
        # 两者都不存在 → 正常首次创建；只有一个存在 → 视为损坏，明确报错
        # （而非静默重建覆盖尚存的那个文件，防止数据丢失）。
        if idx_exists != meta_exists:
            raise RuntimeError(
                f"索引文件不完整（faiss={idx_exists}, json={meta_exists}）："
                f"{idx_path.name} 与 {meta_path.name} 应同时存在。"
                f"请手动补齐或删除 {index_dir} 下该 source 的两个文件后重新入库"
            )
        if not idx_exists:
            raise FileNotFoundError(f"索引不存在: {source}（先运行 ingest）")
        index = faiss.read_index(str(idx_path))
        chunks = [Chunk.from_dict(d) for d in json.loads(meta_path.read_text(encoding="utf-8"))]
        obj = cls.__new__(cls)
        obj.source = source
        obj.chunks = chunks
        obj.index = index
        return obj
