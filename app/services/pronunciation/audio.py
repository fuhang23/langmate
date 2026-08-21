"""音频格式转换。

前端录音（WebM/Opus）与各评测/识别服务要求的 WAV（PCM 16kHz 16bit 单声道）
之间做转换，统一走 ffmpeg 子进程。

约定：所有对外的语音服务接口都只接受「已转换好的 wav 路径」，
格式差异在本模块内消化。
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

TARGET_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16bit

WAV_SUFFIXES = {".wav"}


class AudioConversionError(RuntimeError):
    """音频转换失败（ffmpeg 缺失或源文件损坏等）。"""


def _is_wav16k_pcm_mono(path: Path) -> bool:
    """检测 wav 是否已是 PCM 16kHz 16bit 单声道（满足则无需重编码）。

    读取 WAV RIFF 头（前 44 字节）判断音频格式/声道/采样率/位深，
    与 TARGET_* 常量对齐。解析失败或头不完整则返回 False（保守重编码）。
    """
    try:
        header = path.read_bytes()[:44]
        if len(header) < 44:
            return False
        if header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
            return False
        if header[12:16] != b"fmt ":
            return False
        audio_format = struct.unpack("<H", header[20:22])[0]
        channels = struct.unpack("<H", header[22:24])[0]
        sample_rate = struct.unpack("<I", header[24:28])[0]
        bits_per_sample = struct.unpack("<H", header[34:36])[0]
        return (
            audio_format == 1  # 1 = PCM
            and channels == TARGET_CHANNELS
            and sample_rate == TARGET_RATE
            and bits_per_sample == TARGET_SAMPLE_WIDTH * 8
        )
    except (OSError, struct.error):
        return False


def ensure_wav16k(audio_path: str | Path, *, out_dir: str | Path | None = None) -> Path:
    """把任意常见音频转成 wav 16kHz 16bit 单声道，返回 wav 文件路径。

    - 若已是 PCM 16kHz 16bit 单声道 wav，则原样返回（跳过重复转码）；
    - 否则用 ffmpeg 重编码；out_dir 为空时写到系统临时目录，调用方负责清理。

    Raises:
        AudioConversionError: ffmpeg 不可用或转换失败。
    """
    src = Path(audio_path)
    if not src.exists():
        raise AudioConversionError(f"音频文件不存在: {src}")

    # 已是合规 wav 则跳过重编码，避免链路里 wav→wav 的二次 ffmpeg 转码。
    if src.suffix.lower() in WAV_SUFFIXES and _is_wav16k_pcm_mono(src):
        return src

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
