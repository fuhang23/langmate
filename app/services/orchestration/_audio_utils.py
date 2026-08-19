"""音频 data_url 解码公共工具（跟读/面试判分共用）。"""

from __future__ import annotations

import base64

# 前端录音 MIME 常见前缀（webm/opus 为主，兼容 wav/mp3/mp4）。
_ALLOWED_MIME_PREFIXES = (
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/mpeg",
    "audio/mp3",
)


class AudioDecodeError(RuntimeError):
    """音频 data_url 解码失败。"""


def decode_data_url(data_url: str) -> tuple[str, bytes]:
    """解析 base64 data_url，返回 (mime, raw_bytes)。"""
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        raise AudioDecodeError("missing_audio")
    head, _, b64 = data_url.partition(",")
    mime = head[len("data:"):].split(";", 1)[0].strip().lower()
    if not mime or not any(mime.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
        raise AudioDecodeError("mime")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise AudioDecodeError("decode")
    if not raw:
        raise AudioDecodeError("decode")
    return mime, raw


def mime_ext(mime: str) -> str:
    """按 MIME 返回临时文件扩展名。"""
    if "webm" in mime:
        return ".webm"
    if "ogg" in mime:
        return ".ogg"
    if "wav" in mime:
        return ".wav"
    if "mp4" in mime:
        return ".m4a"
    if "mpeg" in mime or "mp3" in mime:
        return ".mp3"
    return ".bin"
