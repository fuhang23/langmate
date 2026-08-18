"""CEFR 欧标等级模型 + 口语五维级别描述符。

CEFR（欧洲语言共同参考框架）把语言能力分为 A1/A2/B1/B2/C1/C2 六级。
LangMate 用它作为跨考试的统一能力底座：托福、雅思、北京高考听口
的分数都映射到这六级，教学智能体据此给出级别一致的反馈。

五维描述符用于两方面：
1. 给 LLM 的评分 prompt 提供「每个级别长什么样」的锚点（避免虚高/虚低）；
2. 前端展示「学生当前处于哪个欧标级别」时的文字说明。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

    @property
    def order(self) -> int:
        """数值顺序，便于比较与排序（A1=1 ... C2=6）。"""
        return _ORDER[self]

    @property
    def label(self) -> str:
        """级别中文俗称。"""
        return _LABELS[self]


_ORDER = {
    CEFRLevel.A1: 1,
    CEFRLevel.A2: 2,
    CEFRLevel.B1: 3,
    CEFRLevel.B2: 4,
    CEFRLevel.C1: 5,
    CEFRLevel.C2: 6,
}

_LABELS = {
    CEFRLevel.A1: "入门级",
    CEFRLevel.A2: "初级",
    CEFRLevel.B1: "中级",
    CEFRLevel.B2: "中高级",
    CEFRLevel.C1: "高级",
    CEFRLevel.C2: "精通级",
}


class Dimension(str, Enum):
    """口语五维评分维度（与 toefl-speaking/SKILL.md 一致）。"""

    PRONUNCIATION = "pronunciation"
    FLUENCY = "fluency"
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"
    CONTENT = "content"


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension.PRONUNCIATION,
    Dimension.FLUENCY,
    Dimension.VOCABULARY,
    Dimension.GRAMMAR,
    Dimension.CONTENT,
)

_DIMENSION_LABELS = {
    Dimension.PRONUNCIATION: "发音",
    Dimension.FLUENCY: "流利度",
    Dimension.VOCABULARY: "词汇",
    Dimension.GRAMMAR: "语法",
    Dimension.CONTENT: "内容与连贯",
}


@dataclass(frozen=True)
class DimensionDescriptor:
    """某维度在某 CEFR 级别上的表现描述。"""

    dimension: Dimension
    level: CEFRLevel
    description: str


# 五维 × 六级的描述符矩阵。描述力求可观察、可判别，
# 作为 LLM 评分锚点与教学反馈语料。
_DESCRIPTORS: dict[tuple[Dimension, CEFRLevel], str] = {
    # ---- 发音 ----
    (Dimension.PRONUNCIATION, CEFRLevel.A1):
        "能读出简单单词，但音素错误多，母语口音重，重音位置常错，基本无连读弱读意识。",
    (Dimension.PRONUNCIATION, CEFRLevel.A2):
        "常见词发音大体可懂，但 /θ/ /ð/ /v/ /r/ 等音素仍有系统性错误，逐词朗读、语调平。",
    (Dimension.PRONUNCIATION, CEFRLevel.B1):
        "发音清晰可懂，偶尔音素错误不影响理解；有意识模仿重音和语调，但连读、弱读、失去爆破不稳定。",
    (Dimension.PRONUNCIATION, CEFRLevel.B2):
        "发音自然清晰，重音、语调基本正确，能运用连读和弱读，偶有小错不影响整体节奏。",
    (Dimension.PRONUNCIATION, CEFRLevel.C1):
        "发音准确流畅，连读、弱读、失去爆破运用自如，语调能传达态度和强调，口音几乎不造成理解负担。",
    (Dimension.PRONUNCIATION, CEFRLevel.C2):
        "接近母语者，能自如运用语调、重音、节奏进行精细表达，听感自然。",
    # ---- 流利度 ----
    (Dimension.FLUENCY, CEFRLevel.A1):
        "只能说孤立的词或短句，频繁长时间停顿，语速极慢。",
    (Dimension.FLUENCY, CEFRLevel.A2):
        "能说简短句子，但停顿多、重复多，常因想词而中断。",
    (Dimension.FLUENCY, CEFRLevel.B1):
        "能以可接受的语速连续表达，偶有停顿和自我修正，但整体能持续推进。",
    (Dimension.FLUENCY, CEFRLevel.B2):
        "表达连贯流畅，停顿主要用于组织思路而非找词，自我修正少且不打断节奏。",
    (Dimension.FLUENCY, CEFRLevel.C1):
        "几乎无迟疑地连续输出，能边想边说，停顿服务于修辞效果。",
    (Dimension.FLUENCY, CEFRLevel.C2):
        "完全自然的语速和节奏，任何话题都能流畅展开。",
    # ---- 词汇 ----
    (Dimension.VOCABULARY, CEFRLevel.A1):
        "只会最常用的数百个词，表达严重受限。",
    (Dimension.VOCABULARY, CEFRLevel.A2):
        "掌握日常基础词汇，够用但单调，常用 good/bad/very 等笼统词。",
    (Dimension.VOCABULARY, CEFRLevel.B1):
        "词汇足以应付熟悉话题，会用一些搭配，但学术/抽象话题明显吃力，有中式直译。",
    (Dimension.VOCABULARY, CEFRLevel.B2):
        "词汇面较宽，能换说法（paraphrase）绕过生词，搭配大体准确，偶有小误。",
    (Dimension.VOCABULARY, CEFRLevel.C1):
        "词汇丰富精准，能按语域选词，习语和搭配使用自然。",
    (Dimension.VOCABULARY, CEFRLevel.C2):
        "用词精确且得体，细微语义差别把握到位。",
    # ---- 语法 ----
    (Dimension.GRAMMAR, CEFRLevel.A1):
        "只有简单句型，主谓一致、时态等基本规则大量错误。",
    (Dimension.GRAMMAR, CEFRLevel.A2):
        "能用简单句和常见时态，错误频繁但大意可懂。",
    (Dimension.GRAMMAR, CEFRLevel.B1):
        "基本句法掌握较好，尝试复杂句时出错（从句语序、时态呼应），但不影响理解。",
    (Dimension.GRAMMAR, CEFRLevel.B2):
        "句式有变化，复杂句基本正确，偶有小错且能自我修正。",
    (Dimension.GRAMMAR, CEFRLevel.C1):
        "语法准确度高，能灵活运用复杂结构，错误稀少。",
    (Dimension.GRAMMAR, CEFRLevel.C2):
        "语法全面掌控，结构与正式程度随语境自如调整。",
    # ---- 内容与连贯 ----
    (Dimension.CONTENT, CEFRLevel.A1):
        "只能就题目给出单词式回应，无法构成完整回答。",
    (Dimension.CONTENT, CEFRLevel.A2):
        "能回答但内容单薄，缺少理由和细节，结构松散。",
    (Dimension.CONTENT, CEFRLevel.B1):
        "能给出观点加简单理由，结构大体完整（观点-理由），但展开不足、例子笼统。",
    (Dimension.CONTENT, CEFRLevel.B2):
        "切题且结构清晰（观点-理由-例子-收尾），论证有细节，衔接词使用恰当。",
    (Dimension.CONTENT, CEFRLevel.C1):
        "内容充实有说服力，展开充分，逻辑衔接自然，能灵活回应追问。",
    (Dimension.CONTENT, CEFRLevel.C2):
        "表达精准且有深度，结构服务于表达意图，连贯性无可挑剔。",
}


def get_descriptor(dimension: Dimension, level: CEFRLevel) -> DimensionDescriptor:
    """取某维度在某级别的描述符。"""
    return DimensionDescriptor(
        dimension=dimension,
        level=level,
        description=_DESCRIPTORS[(dimension, level)],
    )


def dimension_label(dimension: Dimension) -> str:
    return _DIMENSION_LABELS[dimension]
