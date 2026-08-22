"""内容采集编排：抓取 → 判断（过滤+打标）→ 存 pending；确认入库；忽略；知识库管理。"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from services.ingest.analyze_article import analyze_article, analyze_tags
from services.ingest.chunker import chunk_text
from services.ingest.extract_file import extract_file
from services.ingest.fetch_article import fetch_article
from services.ingest.store import IngestStore

# 采集文章统一进入该 RAG source（与固定文档 lesson-plan-writing 分开）。
_INGEST_RAG_SOURCE = "ingested-articles"

# 文件上传大小上限（与前端提示一致）。
_MAX_FILE_SIZE = 10 * 1024 * 1024

_EXAM_LABELS = {"ielts": "雅思", "gre": "GRE", "other": "其他考试"}


def _apply_filter(result: dict[str, Any]) -> dict[str, Any]:
    """过滤规则：is_ad 或 非托福 → 强制 category=ignore，并说明原因。"""
    if result.get("is_ad"):
        result["category"] = "ignore"
        result["content_type"] = "ad"
        result["reason"] = result.get("reason") or "广告/推广内容，不入库"
    elif result.get("exam") and result["exam"] != "toefl":
        label = _EXAM_LABELS.get(result["exam"], result["exam"])
        result["category"] = "ignore"
        result["reason"] = result.get("reason") or f"非托福内容（{label}），不入库"
    return result


def _build_rag_chunks(record: dict[str, Any]) -> list[Any]:
    """把一条 RAG 记录的 result_json 里的 chunks 构造成 Chunk 列表（带标签 meta）。"""
    from services.rag import Chunk

    result = json.loads(record.get("result_json") or "{}")
    chunks = result.get("chunks") or []
    kind = record.get("kind", "link")
    filename = record.get("filename", "")
    display_title = record.get("summary_title", "") or record.get("title", "")
    meta: dict[str, str] = {
        "kind": kind,
        # record_key 用于逻辑删除后的检索过滤（唯一对应 ingest_records.url）。
        "record_key": record.get("url", ""),
        "exam": record.get("exam", "") or result.get("exam", ""),
        "subject": record.get("subject", "") or result.get("subject", ""),
        "content_type": record.get("content_type", "") or result.get("content_type", ""),
    }
    if kind == "link":
        meta["url"] = record.get("url", "")
        meta["origin_title"] = record.get("title", "")
    elif filename:
        meta["filename"] = filename

    return [
        Chunk(
            text=c.get("text", "").strip(),
            source=_INGEST_RAG_SOURCE,
            title=display_title,
            meta=meta,
        )
        for c in chunks
        if isinstance(c, dict) and c.get("text", "").strip()
    ]


async def fetch_and_analyze(url: str) -> dict[str, Any]:
    """抓取文章 + 大模型判断（过滤+打标）+ 存 pending，返回预览结果。"""
    article = fetch_article(url)
    result = await analyze_article(title=article["title"], raw_text=article["raw_text"])
    result = _apply_filter(result)

    store = IngestStore()
    store.upsert(
        url=url,
        title=article["title"],
        source=article["source"],
        raw_text=article["raw_text"],
        category=result["category"],
        result_json=json.dumps(result, ensure_ascii=False),
        status="pending",
        exam=result.get("exam", ""),
        subject=result.get("subject", ""),
        content_type=result.get("content_type", ""),
        summary_title=result.get("summary_title", ""),
    )

    return {
        "url": url,
        "title": article["title"],
        "summary_title": result.get("summary_title", ""),
        "source": article["source"],
        "category": result["category"],
        "reason": result["reason"],
        "exam": result.get("exam", ""),
        "is_ad": result.get("is_ad", False),
        "subject": result.get("subject", ""),
        "content_type": result.get("content_type", ""),
        "items": result["items"],
        "chunks": result["chunks"],
        "status": "pending",
    }


async def upload_and_prepare(filename: str, content_base64: str) -> dict[str, Any]:
    """上传文件：解码 → 提取 → 轻量判断（考试/广告/打标）→ 本地分块 → 存 pending。

    与链接导入统一做「只留托福 + 广告必过滤」；文件保持纯 RAG 定位（不抽题），
    分块仍走本地 chunker。key 用内容哈希合成键（ingest_records.url 唯一）。
    """
    filename = (filename or "").strip()
    if not filename:
        raise RuntimeError("缺少文件名")

    try:
        raw = base64.b64decode(content_base64 or "", validate=True)
    except Exception as exc:
        raise RuntimeError(f"文件内容解码失败：{exc}") from exc

    if len(raw) > _MAX_FILE_SIZE:
        raise RuntimeError(f"文件超过 10MB 上限（当前 {len(raw) // (1024 * 1024)}MB）")

    text = extract_file(filename, raw)
    if not text.strip():
        raise RuntimeError("未从文件中提取到文本内容")

    tags = await analyze_tags(title=filename, raw_text=text)
    result = _apply_filter(
        {
            "category": "rag",
            "reason": tags.get("reason", ""),
            "exam": tags.get("exam", ""),
            "is_ad": tags.get("is_ad", False),
            "subject": tags.get("subject", ""),
            "content_type": tags.get("content_type", ""),
            "summary_title": tags.get("summary_title", ""),
            "items": [],
            "chunks": [],
        }
    )

    chunks: list[dict[str, str]] = []
    if result["category"] != "ignore":
        chunks = [{"text": t} for t in chunk_text(text)]
        if not chunks:
            raise RuntimeError("未从文件中提取到可入库的文本内容")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    key = f"file://{digest}"

    store = IngestStore()
    store.upsert(
        url=key,
        title=filename,
        source="",
        raw_text=text,
        category=result["category"],
        result_json=json.dumps({**result, "chunks": chunks}, ensure_ascii=False),
        status="pending",
        kind="file",
        filename=filename,
        exam=result.get("exam", ""),
        subject=result.get("subject", ""),
        content_type=result.get("content_type", ""),
        summary_title=result.get("summary_title", ""),
    )

    return {
        "key": key,
        "url": key,
        "filename": filename,
        "title": filename,
        "summary_title": result.get("summary_title", ""),
        "source": "",
        "category": result["category"],
        "reason": result.get("reason", ""),
        "exam": result.get("exam", ""),
        "is_ad": result.get("is_ad", False),
        "subject": result.get("subject", ""),
        "content_type": result.get("content_type", ""),
        "items": [],
        "chunks": chunks,
        "status": "pending",
    }


def confirm_ingest(key: str) -> dict[str, Any]:
    """确认入库：按 category 写入题库 / RAG，更新 status=confirmed。

    key 是 ingest_records.url（链接导入为文章 URL，文件上传为 file://<hash>）。
    """
    store = IngestStore()
    record = store.get(key)
    if record is None or record["status"] != "pending":
        raise RuntimeError("记录不存在或已处理")

    result = json.loads(record["result_json"])
    category = result["category"]
    items = result.get("items") or []

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
        from services.rag import rag_append

        rag_chunks = _build_rag_chunks(record)
        if rag_chunks:
            counts["chunks"] = rag_append(_INGEST_RAG_SOURCE, rag_chunks)

    store.set_status(key, "confirmed")
    counts["status"] = "confirmed"
    return counts


def ignore_ingest(key: str) -> None:
    """忽略该记录（文章或文件），不入库。"""
    IngestStore().set_status(key, "ignored")


def list_knowledge_base(
    subject: str | None = None,
    content_type: str | None = None,
) -> list[dict[str, Any]]:
    """列出已入库的知识记录（含标签与知识点数量），供前端浏览/筛选。"""
    return IngestStore().list_knowledge_base(subject=subject, content_type=content_type)


def delete_knowledge(key: str) -> dict[str, Any]:
    """逻辑删除一条知识记录（deleted=1），不重建向量索引。

    向量仍在 faiss 里（僵尸向量），检索时由 search_knowledge_base 过滤，
    零 embedding 成本、零延迟。后续（方案 C）再按阈值用缓存向量物理重建。
    """
    store = IngestStore()
    record = store.get(key)
    if record is None:
        raise RuntimeError("记录不存在")

    store.mark_deleted(key)
    return {"status": "deleted", "rebuilt_chunks": 0}


def search_knowledge_base(
    query: str,
    subject: str | None = None,
    top_k: int = 3,
) -> list[Any]:
    """检索用户知识库（ingested-articles），排除已逻辑删除的内容。

    先多召回 top_k*3，再按 chunk.meta["record_key"] 过滤掉已删除的僵尸向量，
    最后取前 top_k。检索失败降级为空（不阻断判分）。
    """
    from services.rag import rag_search

    deleted = set(IngestStore().list_deleted_keys())
    chunks = rag_search(
        query,
        source=_INGEST_RAG_SOURCE,
        top_k=max(top_k * 3, top_k),
        subject=subject,
    )
    if not deleted:
        return chunks[:top_k]
    return [
        c for c in chunks if (c.meta or {}).get("record_key", "") not in deleted
    ][:top_k]
