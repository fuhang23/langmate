"""LangMate RAG：官方资料向量检索（百炼 embedding + 本地 faiss 索引）。

对外暴露统一检索接口 rag_search；ingest 用于离线构建索引。
所有失败静默降级为空结果，不阻断判分主流程。
"""

from __future__ import annotations

from services.rag.schema import Chunk
from services.rag.search import rag_search

__all__ = ["Chunk", "rag_search"]
