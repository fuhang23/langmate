"""音频格式转换。

前端录音（WebM/Opus）与各评测/识别服务要求的 WAV（PCM 16kHz 16bit 单声道）
之间做转换，统一走 ffmpeg 子进程。

约定：所有对外的语音服务接口都只接受「已转换好的 wav 路径」，
格式差异在本模块内消化。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

TARGET_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16bit

WAV_SUFFIXES = {".wav"}


class AudioConversionError(RuntimeError):
    """音频转换失败（ffmpeg 缺失或源文件损坏等）。"""


def ensure_wav16k(audio_path: str | Path, *, out_dir: str | Path | None = None) -> Path:
    """把任意常见音频转成 wav 16kHz 16bit 单声道，返回 wav 文件路径。

    - 若已是 wav，仍统一重编码一次（保证采样率/声道/位深符合要求）；
    - out_dir 为空时写到系统临时目录；调用方负责清理临时文件。

    Raises:
        AudioConversionError: ffmpeg 不可用或转换失败。
    """
    src = Path(audio_path)
    if not src.exists():
        raise AudioConversionError(f"音频文件不存在: {src}")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioConversionError(
            "未找到 ffmpeg。请安装 ffmpeg 并加入 PATH（conda: conda install ffmpeg），"
            "用于把浏览器录音（webm）转成评测所需的 wav。"
        )

    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        dst = Path(out_dir) / f"{src.stem}.wav"
    else:
        dst = Path(tempfile.mkstemp(suffix=".wav", prefix="langmate_")[1])

    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-ac", str(TARGET_CHANNELS),
        "-ar", str(TARGET_RATE),
        "-sample_fmt", "s16",
        "-f", "wav",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0 or not dst.exists():
        raise AudioConversionError(
            f"ffmpeg 转换失败（{src.suffix} → wav）: {proc.stderr.strip()[:300]}"
        )
    return dst
