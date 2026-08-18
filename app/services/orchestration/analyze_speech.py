"""双轨融合：把学生一段口语的「文本 + 发音报告」融合成结构化结果。

数据流：
    nanobot ASR 转写文本（轨道 A） ─┐
                                   ├→ analyze_speech → SpeechAnalysis
    原始音频 → 有道智云评测（轨道 B）┘

职责边界（重要）：
- 本模块**不做 ASR**——转写文本由 nanobot 内置 transcription 产出后传入；
- 本模块只负责：音频格式转换 → 有道发音评测 → 把发音/流利度两维映射
  到 CEFR → 与文本打包成教学智能体可直接消费的结构；
- 词汇/语法/内容三维由教学智能体（DeepSeek + Skill）基于文本评，
  发音/流利度两维以本模块输出的 CEFR 提示为准。

分数换算：有道返回 0-100 分，本模块归一到内部 0-4 分制（SKILL.md 约定），
再映射 CEFR（services.cefr）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.cefr import CEFRLevel, dimension_score_to_cefr
from services.pronunciation import PronunciationReport, score_pronunciation
from services.pronunciation.audio import ensure_wav16k


def _score100_to_4(score100: float) -> float:
    """把 0-100 分线性归一到 0-4 分制（保留 0.5 档粒度）。"""
    raw = max(0.0, min(100.0, score100)) / 25.0
    return round(raw * 2) / 2  # 取整到 0.5 档


@dataclass
class SpeechAnalysis:
    """双轨融合结果，喂给教学智能体。"""

    transcript: str                          # 轨道 A：ASR 转写文本
    reference_text: str                      # 复述题原文（自由作答时等于 transcript）
    pronunciation_report: PronunciationReport | None  # 轨道 B：发音评测
    audio_cefr: dict[str, str] = field(default_factory=dict)  # 音频维度 CEFR
    error: str = ""                          # 评测失败时的错误信息（文本兜底）

    def to_prompt_json(self) -> str:
        """压缩成注入 LLM 上下文的 JSON 字符串。"""
        payload: dict[str, Any] = {
            "transcript": self.transcript,
            "reference_text": self.reference_text,
            "matches_reference": self.transcript.strip().lower()
                == self.reference_text.strip().lower(),
            "audio_driven_dimensions": self.audio_cefr,
        }
        if self.pronunciation_report:
            payload["pronunciation_assessment"] = (
                self.pronunciation_report.to_prompt_dict()
            )
        if self.error:
            payload["assessment_error"] = self.error
        return json.dumps(payload, ensure_ascii=False, indent=2)


async def analyze_speech(
    transcript: str,
    audio_path: str | Path,
    *,
    reference_text: str = "",
) -> SpeechAnalysis:
    """融合双轨信息。

    Args:
        transcript: nanobot ASR 转写出的文本。
        audio_path: 原始录音文件（webm/wav/mp3 等，内部统一转 wav 16k）。
        reference_text: 复述题的标准原文；互动面试等自由作答传空串，
                        此时用 transcript 作为评测文本（完整度维度会失真，
                        报告中会标注，教学智能体应忽略完整度维度）。

    Returns:
        SpeechAnalysis。评测失败时 pronunciation_report 为 None 且
        error 带原因——调用方据此用文字维度兜底，不中断教学。
    """
    ref = reference_text.strip() or transcript
    free_speech = not reference_text.strip()

    analysis = SpeechAnalysis(
        transcript=transcript,
        reference_text=ref,
        pronunciation_report=None,
    )

    try:
        wav_path = ensure_wav16k(audio_path)
        report = await score_pronunciation(wav_path, ref)
    except Exception as e:  # 网络/鉴权/格式问题都走文字兜底
        analysis.error = f"{type(e).__name__}: {e}"
        return analysis

    analysis.pronunciation_report = report

    # 音频驱动维度 → 0-4 分 → CEFR。自由作答时完整度维度失真，跳过。
    pron_4 = _score100_to_4(report.pronunciation)
    flu_4 = _score100_to_4(report.fluency)
    analysis.audio_cefr = {
        "pronunciation": dimension_score_to_cefr(pron_4).value,
        "fluency": dimension_score_to_cefr(flu_4).value,
        "_scores_0_4": json.dumps({
            "pronunciation": pron_4,
            "fluency": flu_4,
        }),
    }
    if not free_speech:
        integ_4 = _score100_to_4(report.integrity)
        analysis.audio_cefr["integrity"] = dimension_score_to_cefr(integ_4).value
    else:
        analysis.audio_cefr["integrity"] = "N/A (自由作答，完整度维度失真，请忽略)"

    return analysis
