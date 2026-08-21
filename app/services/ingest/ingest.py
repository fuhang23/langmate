"""内容采集编排：抓取 → 判断 → 存 pending；确认入库；忽略。"""

from __future__ import annotations

import json
from typing import Any

from services.ingest.analyze_article import analyze_article
from services.ingest.fetch_article import fetch_article
from services.ingest.store import IngestStore

# 采集文章统一进入该 RAG source（与固定文档 lesson-plan-writing 分开）。
_INGEST_RAG_SOURCE = "ingested-articles"


async def fetch_and_analyze(url: str) -> dict[str, Any]:
    """抓取文章 + 大模型判断 + 存 pending，返回预览结果。"""
    article = fetch_article(url)
    result = await analyze_article(title=article["title"], raw_text=article["raw_text"])

    store = IngestStore()
    store.upsert(
        url=url,
        title=article["title"],
        source=article["source"],
        raw_text=article["raw_text"],
        category=result["category"],
        result_json=json.dumps(result, ensure_ascii=False),
        status="pending",
    )

    return {
        "url": url,
        "title": article["title"],
        "source": article["source"],
        "category": result["category"],
        "reason": result["reason"],
        "items": result["items"],
        "chunks": result["chunks"],
        "status": "pending",
    }


def confirm_ingest(url: str) -> dict[str, Any]:
    """确认入库：按 category 写入题库 / RAG，更新 status=confirmed。"""
    store = IngestStore()
    record = store.get(url)
    if record is None or record["status"] != "pending":
        raise RuntimeError("记录不存在或已处理")

    result = json.loads(record["result_json"])
    category = result["category"]
    items = result.get("items") or []
    chunks = result.get("chunks") or []

    counts: dict[str, Any] = {"questions": 0, "chunks": 0}

    if category in ("writing_discussion", "writing_email"):
        from services.corpus import CorpusStore, default_corpus_db_path

        cs = CorpusStore(default_corpus_db_path())
        counts["questions"] = cs.add_writing_questions(items)
    elif category == "speaking_repeat":
        from services.corpus import CorpusStore, default_corpus_db_path

        cs = CorpusStore(default_corpus_db_path())
        counts["questions"] = cs.add_speaking_repeat(items)
    elif category == "speaking_interview":
        from services.corpus import CorpusStore, default_corpus_db_path

        cs = CorpusStore(default_corpus_db_path())
        counts["questions"] = cs.add_speaking_interview(items)
    elif category == "rag":
        from services.rag import Chunk, rag_append

        rag_chunks = [
            Chunk(
                text=c.get("text", "").strip(),
                source=_INGEST_RAG_SOURCE,
                title=record["title"],
                meta={"url": url, "origin_title": record["title"]},
            )
            for c in chunks
            if c.get("text", "").strip()
        ]
        if rag_chunks:
            counts["chunks"] = rag_append(_INGEST_RAG_SOURCE, rag_chunks)

    store.set_status(url, "confirmed")
    counts["status"] = "confirmed"
    return counts


def ignore_ingest(url: str) -> None:
    """忽略该文章，不入库。"""
    IngestStore().set_status(url, "ignored")
