"""本地规则分块：按段落聚合至目标字数 + 块间少量重叠。

不调用大模型，确定性、零成本。先按空行切段落，再贪心聚合到约 target 字；
flush 时把当前 chunk 尾部约 overlap 字带入下一个 chunk 的开头，避免切断语义。
"""

from __future__ import annotations

import re

_TARGET = 500
_OVERLAP = 80


def _split_paragraphs(text: str) -> list[str]:
    """按空行切段落并清洗每段内部空白。"""
    raw = re.split(r"\n\s*\n", text)
    paragraphs: list[str] = []
    for block in raw:
        cleaned = re.sub(r"\s+", " ", block).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def chunk_text(text: str, target: int = _TARGET, overlap: int = _OVERLAP) -> list[str]:
    """把文本切分为 chunk 列表。每个 chunk 目标 target 字，块间 overlap 字重叠。

    - 单段超过 target 时按字符滑动窗口硬切（步长 target - overlap）。
    - 正常情况按段落聚合到约 target 字，flush 时尾部 overlap 字带入下一块。
    """
    text = (text or "").strip()
    if not text:
        return []

    target = max(target, 100)
    overlap = min(max(overlap, 0), target // 2)
    step = max(target - overlap, 1)

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        chunks.append(" ".join(current).strip())
        current = []

    for para in paragraphs:
        # 单段过长 → 滑动窗口硬切，段内自带重叠。
        if len(para) > target:
            flush()
            start = 0
            while start < len(para):
                piece = para[start:start + target].strip()
                if piece:
                    chunks.append(piece)
                if start + target >= len(para):
                    break
                start += step
            continue

        # 当前块装不下该段 → flush，并把尾部 overlap 字带入下一块开头。
        if current and sum(len(p) for p in current) + len(current) + len(para) + 1 > target:
            flush()
            tail = chunks[-1][-overlap:] if overlap and chunks else ""
            if tail:
                current = [tail]

        current.append(para)

    flush()
    return [c for c in chunks if c.strip()]
