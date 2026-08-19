"""双轨融合编排层。

把 nanobot ASR 转写文本（轨道 A）与有道智云发音评测报告（轨道 B）
融合成结构化结果，供教学智能体综合出五维评分。
"""

from services.orchestration.analyze_speech import (
    SpeechAnalysis,
    analyze_speech,
)
from services.orchestration.score_interview import (
    InterviewScoreError,
    score_interview,
)
from services.orchestration.score_repeat import RepeatScoreError, score_repeat

__all__ = [
    "SpeechAnalysis",
    "analyze_speech",
    "score_repeat",
    "RepeatScoreError",
    "score_interview",
    "InterviewScoreError",
]
