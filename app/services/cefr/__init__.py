"""CEFR 欧标统一能力底座。

- model.py：CEFR 等级枚举（A1-C2）+ 口语五维级别描述符
- mappings.py：各考试分数 → CEFR 映射（托福/雅思/北京高考）
"""

from services.cefr.mappings import (
    bj_gaokao_to_cefr,
    dimension_score_to_cefr,
    dimension_scores_to_cefr,
    ielts_to_cefr,
    toefl_speaking_to_cefr,
)
from services.cefr.model import (
    DIMENSIONS,
    CEFRLevel,
    Dimension,
    dimension_label,
    get_descriptor,
)

__all__ = [
    "CEFRLevel",
    "DIMENSIONS",
    "Dimension",
    "dimension_label",
    "get_descriptor",
    "dimension_score_to_cefr",
    "dimension_scores_to_cefr",
    "toefl_speaking_to_cefr",
    "ielts_to_cefr",
    "bj_gaokao_to_cefr",
]
