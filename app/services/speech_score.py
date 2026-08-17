"""口语评分服务（Phase 3）。

职责划分：
- 文本维度（流利度/词汇/语法/内容与连贯）：由主 LLM（DeepSeek）按 SKILL.md 里的
  评分标准直接完成，无需本服务。
- 发音维度（音素级 / 重音 / 语调）：需要音频 + 专业引擎，本服务负责封装。

当前状态：骨架占位。待接入「豆包语音评测」或「Azure Speech Pronunciation
Assessment」后，提供 `score_pronunciation(audio_path) -> dict` 接口。
"""

from __future__ import annotations

from typing import Any


def score_pronunciation(audio_path: str) -> dict[str, Any]:
    """对音频做音素级发音评分（待实现）。

    目标返回结构：
        {
            "pronunciation_score": 0.0,   # 0-4 分
            "words": [                    # 逐词发音
                {"word": "think", "accuracy": 0.92, "phoneme": "/θɪŋk/"},
            ],
            "issues": [                   # 具体发音问题
                {"phoneme": "/θ/", "note": "发成了 /s/"},
            ],
        }
    """
    raise NotImplementedError(
        "发音评分引擎尚未接入。可选方案：豆包语音评测 / Azure Speech Pronunciation "
        "Assessment。接入后在此实现。"
    )
