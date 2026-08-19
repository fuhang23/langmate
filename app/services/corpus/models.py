"""跟读复述题库的数据模型。

listen and repeat.docx 的结构：
  每个场景 = 标题行（如 "Making salad"）+ 情景说明段落
           + 7 个编号句子（如 "1. Begin by / washing the vegetables."，
             用 '/' 标注意群断句）。

入库后按「场景 → 句子」两级组织，句子保留意群断句，供前端逐句展示
与判分（`analyze_speech` 的 reference_text 取句子完整文本）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RepeatSentence:
    """跟读题的一个句子。"""

    scenario_id: int
    seq: int                # 1-7，对应官方 8/10/12 秒建议时长（难度递增）
    text: str               # 完整句子（去掉 '/' 后的纯文本，用于 TTS 与判分）
    chunks: list[str] = field(default_factory=list)  # 意群断句（按 '/' 切分）

    @property
    def suggested_seconds(self) -> int:
        """按题号映射官方作答时长：1-2→8s，3-5→10s，6-7→12s。"""
        if self.seq <= 2:
            return 8
        if self.seq <= 5:
            return 10
        return 12


@dataclass
class RepeatScenario:
    """跟读题的一个场景（含 7 个句子）。"""

    id: int
    title: str              # 场景标题，如 "Making salad"
    context_prompt: str     # 情景说明，如 "You are volunteering at ..."
    sentences: list[RepeatSentence] = field(default_factory=list)


@dataclass
class InterviewQuestion:
    """互动面试的一个题（每题 45 秒自由表达）。"""

    topic_id: int
    seq: int                        # 1-4，递进式提问
    prompt_en: str                  # 英文题目（含 interviewer 递进引导语）
    prompt_zh: str = ""             # 中文翻译 / 要点
    reference_answer: str = ""      # 参考回答（英文范文）
    core_expressions: list[str] = field(default_factory=list)  # 核心表达


@dataclass
class InterviewTopic:
    """互动面试的一个主题（含 4 道递进题）。"""

    id: int
    title: str              # 主题名，如 "网络购物：习惯、利弊与实体店未来"
    description: str = ""   # 一句话说明 / 场景设定
    questions: list[InterviewQuestion] = field(default_factory=list)
