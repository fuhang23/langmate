"""各考试分数 → CEFR 欧标映射。

设计原则：
- 内部五维评分用 0-4 分制（SKILL.md 约定），先映射 CEFR 供教学使用；
- 托福 2026 新制口语为 1-6 band，官方对标 CEFR（6=C2、5=C1、4=B2、3=B1、2=A2、1=A1）；
- 雅思 0-9 band 官方对标 CEFR，预留给后续扩展；
- 北京高考英语听口尚无官方 CEFR 对标，占位接口待补充（需教研定标）。

注意：所有映射均为「AI 自研对标」参考值，不是官方换算结果，
反馈给学生时必须如实说明（SKILL.md 第三条铁律）。
"""

from __future__ import annotations

from services.cefr.model import CEFRLevel

# 托福 2026 新制：1-6 band → CEFR（官方对齐口径）
TOEFL_BAND_TO_CEFR: dict[int, CEFRLevel] = {
    6: CEFRLevel.C2,
    5: CEFRLevel.C1,
    4: CEFRLevel.B2,
    3: CEFRLevel.B1,
    2: CEFRLevel.A2,
    1: CEFRLevel.A1,
}

# 雅思 band → CEFR（官方口径近似：9=C2、7.5-8=C1、5.5-6.5=B2、4-5=B1）
IELTS_BAND_TO_CEFR: dict[float, CEFRLevel] = {
    9.0: CEFRLevel.C2,
    8.5: CEFRLevel.C2,
    8.0: CEFRLevel.C1,
    7.5: CEFRLevel.C1,
    7.0: CEFRLevel.C1,
    6.5: CEFRLevel.B2,
    6.0: CEFRLevel.B2,
    5.5: CEFRLevel.B2,
    5.0: CEFRLevel.B1,
    4.5: CEFRLevel.B1,
    4.0: CEFRLevel.B1,
}

# 内部维度分（0-4）→ CEFR 阈值。0-4 分制与 CEFR 六级对齐（阈值须与
# _DIMENSION_THRESHOLDS 代码一致，教研口径以代码为准）：
# >=3.75 → C2，>=3.0 → C1，>=2.25 → B2，>=1.5 → B1，>=0.75 → A2，<0.75 → A1。
# C2 仅留给接近满分的情形（由 dimension_scores_to_cefr 判定）。
_DIMENSION_THRESHOLDS: list[tuple[float, CEFRLevel]] = [
    (3.75, CEFRLevel.C2),
    (3.0, CEFRLevel.C1),
    (2.25, CEFRLevel.B2),
    (1.5, CEFRLevel.B1),
    (0.75, CEFRLevel.A2),
    (0.0, CEFRLevel.A1),
]


def dimension_score_to_cefr(score: float) -> CEFRLevel:
    """把单个维度 0-4 分映射到 CEFR 级别。

    Args:
        score: 0.0-4.0（可 0.5 档）。
    """
    score = max(0.0, min(4.0, score))
    for threshold, level in _DIMENSION_THRESHOLDS:
        if score >= threshold:
            return level
    return CEFRLevel.A1


def dimension_scores_to_cefr(scores: dict[str, float]) -> CEFRLevel:
    """把五维 0-4 分综合映射为整体 CEFR 级别。

    取各维度映射级别的中位数偏保守档（最低的第 40 百分位），
    避免单一弱项被强项掩盖——口语短板效应明显。
    """
    if not scores:
        raise ValueError("scores 不能为空")
    levels = sorted(
        (dimension_score_to_cefr(s).order for s in scores.values()),
        reverse=True,
    )
    idx = min(len(levels) - 1, int(len(levels) * 0.4))
    order = levels[idx]
    return next(lv for lv in CEFRLevel if lv.order == order)


def toefl_speaking_to_cefr(band: int | float) -> CEFRLevel:
    """托福 2026 新制口语 band（1-6）→ CEFR。"""
    rounded = max(1, min(6, round(band)))
    return TOEFL_BAND_TO_CEFR[rounded]


def ielts_to_cefr(band: float) -> CEFRLevel:
    """雅思 band（0-9，0.5 档）→ CEFR。"""
    band = max(0.0, min(9.0, band))
    candidates = sorted(IELTS_BAND_TO_CEFR, reverse=True)
    for b in candidates:
        if band >= b:
            return IELTS_BAND_TO_CEFR[b]
    return CEFRLevel.A1


def bj_gaokao_to_cefr(score: float, full_score: float) -> CEFRLevel:
    """北京高考英语听口 → CEFR（占位，教研定标后实现）。

    Raises:
        NotImplementedError: 尚无官方/教研对标口径。
    """
    raise NotImplementedError(
        "北京高考听口 → CEFR 映射待教研定标后补充（无官方对标）。"
    )
