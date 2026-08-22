"""互动面试判分：自由作答的双轨判分。

与跟读（score_repeat）区别：面试是自由表达，无标准原文，reference_text=None。
判分双轨：
1. 音频轨（有道）：发音 + 流利度（客观音频评测）；
2. 内容轨（LLM）：语法 + 词汇 + 逻辑 + 内容（理解语义）。

合并返回结构化 JSON，并复用 record_from_analysis 写进度。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from services.llm import score_content
from services.orchestration._audio_utils import (
    AudioDecodeError,
    decode_data_url,
    mime_ext,
)
from services.orchestration.analyze_speech import analyze_speech
from services.pronunciation.audio import ensure_wav16k
from services.progress import record_from_analysis

# 兼容：面试判分输入错误沿用 AudioDecodeError。
InterviewScoreError = AudioDecodeError


def _audio_payload(analysis: Any) -> dict[str, Any]:
    """从 SpeechAnalysis 提取音频维度（发音/流利度）与问题音素。"""
    report = analysis.pronunciation_report
    payload: dict[str, Any] = {
        "pronunciation": None,
        "fluency": None,
        "speed_wpm": None,
        "problem_phonemes": [],
        "stress_issues": [],
        "cefr": {},
    }
    if report is not None:
        payload["pronunciation"] = report.pronunciation
        payload["fluency"] = report.fluency
        payload["speed_wpm"] = report.speed
        payload["problem_phonemes"] = report.problem_phonemes()
        payload["stress_issues"] = report.stress_issues()
    payload["cefr"] = analysis.audio_cefr or {}
    return payload


async def score_interview(
    *,
    audio_data_url: str,
    transcript: str,
    question_prompt: str,
    topic_id: int = 0,
    question_seq: int = 0,
) -> dict[str, Any]:
    """判分一次互动面试作答。

    Args:
        audio_data_url: 学生录音的 base64 data_url。
        transcript: 前端 ASR 转写文本。
        question_prompt: 面试题目（英文，含 interviewer 引导语），用于 LLM 评分。
        topic_id: 面试主题 id（>0 时题目级练习统计记为 "interview:{topic_id}"）。
        question_seq: 主题内题号（用于统计组内覆盖）。

    Returns:
        合并后的结构化判分 JSON：
        {
          "transcript": str,
          "audio_scores": {pronunciation, fluency, speed_wpm, ...},
          "llm_scores": {grammar, vocabulary, logic, content},
          "cefr": str,
          "problem_phonemes": [...],
        }

    Raises:
        InterviewScoreError: 输入无效（缺参数 / data_url 非法）。
    """
    if not transcript or not transcript.strip():
        raise InterviewScoreError("missing_transcript")
    if not question_prompt or not question_prompt.strip():
        raise InterviewScoreError("missing_question_prompt")

    # 1. 音频轨：解码 → wav16k → analyze_speech(reference_text=None)
    mime, raw = decode_data_url(audio_data_url)
    ext = mime_ext(mime)
    tmp_dir = Path(tempfile.mkdtemp(prefix="langmate_interview_"))
    audio_payload: dict[str, Any]
    analysis = None
    try:
        audio_path = tmp_dir / f"recording{ext}"
        audio_path.write_bytes(raw)
        wav_path = ensure_wav16k(audio_path)
        analysis = await analyze_speech(transcript, wav_path, reference_text=None)
        audio_payload = _audio_payload(analysis)
    except AudioDecodeError:
        raise
    except Exception as exc:
        audio_payload = {
            "pronunciation": None,
            "fluency": None,
            "speed_wpm": None,
            "problem_phonemes": [],
            "stress_issues": [],
            "cefr": {},
            "audio_error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 2. 内容轨：LLM 四维评分（失败降级为空态，不阻断）
    try:
        llm_scores = await score_content(
            question_prompt=question_prompt,
            transcript=transcript,
        )
    except Exception as exc:
        llm_scores = {
            "grammar": {"score": None, "comment": ""},
            "vocabulary": {"score": None, "comment": ""},
            "logic": {"score": None, "comment": ""},
            "content": {"score": None, "comment": ""},
            "llm_error": f"{type(exc).__name__}: {exc}",
        }

    # 3. 合并 CEFR（优先音频轨的 pronunciation/fluency 短板）
    cefr_map = audio_payload.get("cefr", {})
    pron_cefr = cefr_map.get("pronunciation", "")
    flu_cefr = cefr_map.get("fluency", "")
    overall_cefr = pron_cefr or flu_cefr or ""

    result: dict[str, Any] = {
        "transcript": transcript,
        "audio_scores": {
            "pronunciation": audio_payload.get("pronunciation"),
            "fluency": audio_payload.get("fluency"),
            "speed_wpm": audio_payload.get("speed_wpm"),
        },
        "llm_scores": llm_scores,
        "cefr": overall_cefr,
        "problem_phonemes": audio_payload.get("problem_phonemes", []),
        "stress_issues": audio_payload.get("stress_issues", []),
    }
    if audio_payload.get("audio_error"):
        result["audio_error"] = audio_payload["audio_error"]
    if "llm_error" in llm_scores:
        result["llm_error"] = llm_scores.pop("llm_error")

    # 4. 写进度库（question_type="interview"，由 reference_text=None 自动判定）。
    if analysis is not None and not audio_payload.get("audio_error"):
        try:
            record_from_analysis(
                analysis,
                None,
                question_key=f"interview:{topic_id}" if topic_id > 0 else "",
                question_seq=question_seq,
            )
        except Exception:
            pass  # 写进度失败不阻断

    return result
