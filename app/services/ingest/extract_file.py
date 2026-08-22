"""本地文件文本提取：pdf(pypdf) / docx(zipfile) / md / txt。

文件上传功能不调用大模型，纯本地提取。PDF 用 pypdf 逐页抽取；DOCX 用
zipfile 读 word/document.xml 并剥标签还原段落（与 corpus 的 docx 解析
思路一致，避免引入 python-docx）；md/txt 直接 UTF-8 解码（回退 latin-1）。
"""

from __future__ import annotations

import html
import re
import zipfile
from io import BytesIO
from pathlib import Path

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


class FileExtractionError(Exception):
    """文件提取失败（格式不支持 / 超限 / 解析失败 / 空文本）。"""


def validate_filename(filename: str) -> str:
    """校验文件名与扩展名，返回小写扩展名；不合法抛 FileExtractionError。"""
    name = (filename or "").strip()
    if not name:
        raise FileExtractionError("缺少文件名")
    ext = Path(name).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise FileExtractionError(
            f"不支持的文件类型 {ext or '(无扩展名)'}，仅支持 pdf / docx / md / txt"
        )
    return ext


def check_size(data: bytes) -> None:
    """校验文件大小（上限 10MB），超限抛 FileExtractionError。"""
    if len(data) > _MAX_FILE_SIZE:
        raise FileExtractionError(
            f"文件超过 10MB 上限（当前 {len(data) // (1024 * 1024)}MB）"
        )


def extract_file(filename: str, data: bytes) -> str:
    """从文件字节提取纯文本。失败抛 FileExtractionError。"""
    ext = validate_filename(filename)
    check_size(data)

    if ext == ".pdf":
        text = _extract_pdf(data)
    elif ext == ".docx":
        text = _extract_docx(data)
    else:  # .md / .txt
        text = _extract_text(data)

    cleaned = re.sub(r"[ \t]+", " ", text).strip()
    if not cleaned:
        raise FileExtractionError("未从文件中提取到文本内容（可能是扫描件或空文档）")
    return cleaned


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise FileExtractionError("PDF 解析依赖 pypdf 未安装") from exc
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(page.strip() for page in pages if page.strip())
    except FileExtractionError:
        raise
    except Exception as exc:
        raise FileExtractionError(f"PDF 解析失败：{exc}") from exc


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise FileExtractionError(f"DOCX 解析失败：{exc}") from exc

    # 段落结束 → 换行；制表符 → 空白；其余标签剥除。
    xml = re.sub(r"<w:p[ >][^>]*>|<w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    lines = [html.unescape(line).strip() for line in xml.split("\n")]
    return "\n".join(line for line in lines if line)


def _extract_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")
