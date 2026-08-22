"""口语评分的进度写库复用函数。

把「评测结果 → PracticeRecord → ProgressStore」的写库逻辑从
AnalyzeSpeechTool 中抽出，供两处复用：
1. AnalyzeSpeechTool._auto_record_progress（agent 对话链路，自动记录）；
2. nanobot webui 的跟读判分 HTTP 端点（跟读播放器直连评测链路）。

写库失败只记 warning、不抛异常——进度记录是「尽力而为」，
不能因为写库失败阻断口语教学或判分返回。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.progress.models import PracticeRecord
from services.progress.store import ProgressStore, default_db_path

logger = logging.getLogger(__name__)

# CEFR 级别排序（用于取「短板」——综合水平取较弱维度）。
_CEFR_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}


def _lower_cefr(a: str, b: str) -> str:
    """取两个 CEFR 级别中较低的一个（短板效应）。"""
    if not a:
        return b
    if not b:
        return a
    return a if _CEFR_ORDER.get(a, 0) <= _CEFR_ORDER.get(b, 0) else b


def _format_weak_points(report: Any, limit: int = 5) -> list[str]:
    """把发音报告里的问题音素/重音问题格式化成可读的薄弱点列表。"""
    points: list[str] = []
    for p in report.problem_phonemes():
        heard = f" 发成 {p['heard_as']}" if p.get("heard_as") else ""
        points.append(f"{p['word']} 的 {p['phoneme']}{heard}")
    for s in report.stress_issues():
        direction = "漏重读" if s["should_stress"] else "多读重音"
        points.append(f"{s['word']} 的 {s['phoneme']} {direction}")
    return points[:limit]


def record_speech_result(
    *,
    section: str = "speaking",
    question_type: str = "",
    scores: dict[str, Any] | None = None,
    cefr: str = "",
    weak_points: list[str] | None = None,
    question_key: str = "",
    question_seq: int = 0,
) -> bool:
    """把一次口语练习的评分结果写入进度库。

    Args:
        section: 五部分之一，默认 speaking。
        question_type: 题型，如 listen_and_repeat / interview。
        scores: 维度分（0-4 制），如 {"pronunciation": 3.0, ...}。
        cefr: 本次练习综合出的 CEFR 级别（如 "B1"）。
        weak_points: 薄弱点列表。
        question_key: 题目标识（"repeat:{id}" / "interview:{id}"），空串表示
            非题目入口（agent 对话链路），不参与题目级统计。
        question_seq: 组内序号（跟读句子 seq / 面试题号）。

    Returns:
        True 表示写入成功；False 表示写入失败（已记 warning，不抛异常）。
    """
    record = PracticeRecord(
        section=section,
        question_type=question_type or "",
        scores=scores or {},
        cefr=cefr or "",
        weak_points=weak_points or [],
        question_key=question_key or "",
        question_seq=question_seq or 0,
    )
    try:
        ProgressStore(default_db_path()).add_record(record)
        return True
    except Exception as e:
        logger.warning("记录口语进度失败（不阻断流程）: %s", e)
        return False


def record_from_analysis(
    analysis: Any,
    reference_text: str | None,
    question_key: str = "",
    question_seq: int = 0,
) -> None:
    """从 SpeechAnalysis 结果推导并写入进度库（AnalyzeSpeechTool 复用）。

    Args:
        analysis: services.orchestration.analyze_speech.SpeechAnalysis 实例。
        reference_text: 复述题原文；为 None/空 表示自由作答（互动面试）。
        question_key: 题目标识（"repeat:{id}" / "interview:{id}"），空串表示
            非题目入口。
        question_seq: 组内序号。
    """
    if analysis.error or not analysis.pronunciation_report:
        return

    report = analysis.pronunciation_report
    scores_raw = analysis.audio_cefr.get("_scores_0_4", "{}")
    scores_04 = json.loads(scores_raw) if isinstance(scores_raw, str) else scores_raw
    pron_cefr = analysis.audio_cefr.get("pronunciation", "")
    flu_cefr = analysis.audio_cefr.get("fluency", "")
    cefr = _lower_cefr(pron_cefr, flu_cefr)

    record_speech_result(
        section="speaking",
        question_type="listen_and_repeat" if reference_text else "interview",
        scores={
            "pronunciation": scores_04.get("pronunciation"),
            "fluency": scores_04.get("fluency"),
        },
        cefr=cefr,
        weak_points=_format_weak_points(report),
        question_key=question_key,
        question_seq=question_seq,
    )
    logger.info("已自动记录口语进度: %s", cefr)
