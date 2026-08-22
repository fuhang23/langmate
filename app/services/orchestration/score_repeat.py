"""跟读复述判分：把「音频 data_url + 转写 + 原文」变成结构化判分结果。

供跟读播放器直连评测使用（不走 agent 对话）。职责：
1. 解码 base64 data_url 落盘临时文件；
2. 转 wav 16k（ensure_wav16k）；
3. 调 analyze_speech（reference_text = 原文）做双轨评测 + 逐字比对；
4. 返回前端可直接渲染的结构化 JSON（逐字比对、发音/流利度/完整度分、
   问题音素、重音问题、弱词、CEFR）；
5. 复用 record_from_analysis 自动写进度库。

本模块不依赖 nanobot 内部，只依赖 services.*，可独立测试。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from services.orchestration._audio_utils import (
    AudioDecodeError,
    decode_data_url,
    mime_ext,
)
from services.orchestration.analyze_speech import analyze_speech
from services.pronunciation.audio import ensure_wav16k
from services.progress import record_from_analysis

# 兼容旧引用：RepeatScoreError 即 AudioDecodeError（跟读判分输入无效）。
RepeatScoreError = AudioDecodeError


def _score_payload(analysis: Any, reference_text: str) -> dict[str, Any]:
    """把 SpeechAnalysis 转成前端可渲染的判分 JSON。"""
    report = analysis.pronunciation_report
    transcript = analysis.transcript or ""
    payload: dict[str, Any] = {
        "transcript": transcript,
        "reference_text": reference_text,
        "matches_reference": transcript.strip().lower()
        == reference_text.strip().lower(),
    }
    if report is not None:
        payload["scores_0_100"] = {
            "overall": report.overall,
            "pronunciation": report.pronunciation,
            "fluency": report.fluency,
            "integrity": report.integrity,
        }
        payload["speed_wpm"] = report.speed
        payload["problem_phonemes"] = report.problem_phonemes()
        payload["stress_issues"] = report.stress_issues()
        payload["weak_words"] = [
            {"word": w.word, "ipa": w.ipa, "score": w.pronunciation}
            for w in report.words
            if w.pronunciation < 60
        ]
        # LangMate: 透出完整词级列表（含每个词的得分/音标/音素明细），
        # 供前端「逐词三档标色 + 点击展开音素详情」。纯透出、零逻辑。
        payload["words"] = [
            {
                "word": w.word,
                "ipa": w.ipa,
                "score": w.pronunciation,
                "phonemes": [
                    {
                        "phoneme": p.phoneme,
                        "score": p.pronunciation,
                        "correct": p.correct,
                        "heard_as": p.calibration,
                        "stress_ref": p.stress_ref,
                        "stress_detect": p.stress_detect,
                    }
                    for p in w.phonemes
                ],
            }
            for w in report.words
        ]
    else:
        payload["scores_0_100"] = None
        payload["problem_phonemes"] = []
        payload["stress_issues"] = []
        payload["weak_words"] = []
        payload["words"] = []
    payload["audio_cefr"] = analysis.audio_cefr
    if analysis.error:
        payload["assessment_error"] = analysis.error
    return payload


async def score_repeat(
    *,
    audio_data_url: str,
    sentence_text: str,
    transcript: str = "",
    scenario_id: int = 0,
    sentence_seq: int = 0,
) -> dict[str, Any]:
    """判分一次跟读复述。

    Args:
        audio_data_url: 学生录音的 base64 data_url（webm/opus 等）。
        sentence_text: 跟读题的原文（用于逐字比对与发音评测 reference_text）。
        transcript: 前端 ASR 转写文本（学生实际说了什么）。可选：
            空串表示「尚未转写」，此时仅做发音评测（逐字比对 matches_reference
            记为 False，由前端拿到真实转写后本地重算覆盖）。
        scenario_id: 跟读场景 id（>0 时题目级练习统计记为 "repeat:{scenario_id}"）。
        sentence_seq: 场景内句子 seq（用于统计组内覆盖）。

    Returns:
        结构化判分 JSON（见 _score_payload）。

    Raises:
        RepeatScoreError: 输入无效（缺 sentence_text / data_url 非法）。
    """
    if not sentence_text or not sentence_text.strip():
        raise RepeatScoreError("missing_sentence_text")

    mime, raw = decode_data_url(audio_data_url)
    ext = mime_ext(mime)
    wav_path: Path | None = None
    tmp_dir = Path(tempfile.mkdtemp(prefix="langmate_repeat_"))
    try:
        audio_path = tmp_dir / f"recording{ext}"
        audio_path.write_bytes(raw)
        wav_path = ensure_wav16k(audio_path)
        analysis = await analyze_speech(
            transcript,
            wav_path,
            reference_text=sentence_text,
        )
    except RepeatScoreError:
        raise
    except Exception as exc:
        # 音频转换/评测失败：返回带 error 的空态，不抛异常（降级）。
        class _Fallback:  # 最小鸭子类型，复用 _score_payload
            transcript = transcript
            pronunciation_report = None
            audio_cefr = {}
            error = f"{type(exc).__name__}: {exc}"

        return _score_payload(_Fallback(), sentence_text)
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 评测成功后自动写进度库（复用 AnalyzeSpeechTool 同一逻辑）。
    record_from_analysis(
        analysis,
        sentence_text,
        question_key=f"repeat:{scenario_id}" if scenario_id > 0 else "",
        question_seq=sentence_seq,
    )

    return _score_payload(analysis, sentence_text)
