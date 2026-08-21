"""解析 toefl-ibt-lesson-plan-writing.pdf 并入库为向量索引。

分块策略：按页切块（每页一个 chunk），通过启发式扫描为每页标注
所属 Lesson 与标题（"Writing, Lesson N" / "Title xxx" 出现在页内时更新）。
lesson-plan 是结构化文档，保留 Lesson 标题让检索更精准。
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

from pypdf import PdfReader

from services.rag import embed_bailian
from services.rag.schema import Chunk
from services.rag.store import RagIndex, default_index_dir

SOURCE = "lesson-plan-writing"

_LESSON_RE = re.compile(r"Writing,\s*Lesson\s+(\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(r"^Title\s+(.+)$", re.MULTILINE)


def _find_pdf() -> str:
    hits = glob.glob(
        "**/toefl-ibt-lesson-plan-writing.pdf", recursive=True
    )
    # 从 data/corpus 下递归查找
    if not hits:
        hits = glob.glob(
            "d:/fhfhfh/langmate/app/data/corpus/**/toefl-ibt-lesson-plan-writing.pdf",
            recursive=True,
        )
    if not hits:
        raise FileNotFoundError("未找到 toefl-ibt-lesson-plan-writing.pdf")
    return hits[0]


def _extract_pages(pdf_path: str) -> list[str]:
    reader = PdfReader(pdf_path)
    pages: list[str] = []
    for p in reader.pages:
        text = p.extract_text() or ""
        pages.append(text)
    return pages


def build_chunks(pdf_path: str) -> list[Chunk]:
    """解析 PDF 为 chunk 列表（每页一个，带 lesson/title/page metadata）。"""
    pages = _extract_pages(pdf_path)
    chunks: list[Chunk] = []
    current_lesson = ""
    current_title = ""

    for i, page_text in enumerate(pages, start=1):
        m_lesson = _LESSON_RE.search(page_text)
        if m_lesson:
            current_lesson = m_lesson.group(1)
        m_title = _TITLE_RE.search(page_text)
        if m_title:
            current_title = m_title.group(1).strip()

        # 清洗：压缩空白、去掉页眉页码（首行 "TOEFL iBT" 之前的纯页码）。
        cleaned = re.sub(r"\s+", " ", page_text).strip()
        if not cleaned:
            continue
        chunks.append(
            Chunk(
                text=cleaned,
                source=SOURCE,
                lesson=current_lesson,
                title=current_title,
                page=i,
            )
        )
    return chunks


def ingest(
    pdf_path: str | None = None,
    index_dir: str | Path | None = None,
) -> int:
    """解析 lesson-plan-writing.pdf 并生成向量索引，返回 chunk 数。

    云端百炼逐批计算 embedding，向量+原文存本地；任何异常向上抛出
    （由调用方决定是否重试）。
    """
    pdf_path = pdf_path or _find_pdf()
    index_dir = index_dir or default_index_dir()
    chunks = build_chunks(pdf_path)
    if not chunks:
        raise RuntimeError("lesson-plan-writing.pdf 解析出 0 个 chunk")

    vectors = embed_bailian.embed_texts([c.text for c in chunks])
    index = RagIndex(SOURCE, vectors, chunks)
    index.save(index_dir)
    return len(chunks)


if __name__ == "__main__":
    n = ingest()
    print(f"ingested {n} chunks into {default_index_dir()}")
