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


@dataclass
class ChatScenario:
    """聊天模式的一个主题场景（每节课围绕它展开对话）。

    与备考模式的题库不同，聊天场景是「教学引导素材」而非「题目」：
    给 agent 提供一个情景设定 + 一个隐性教学点，agent 据此开场、
    提问、选择性纠错。纯 seed 数据（无 docx 来源）。
    """

    id: int
    title: str              # 中英标题，如 "餐厅点餐 / Ordering at a Restaurant"
    context_prompt: str     # 情景说明，如 "You are ordering food at a restaurant..."
    teaching_point: str     # 教学点，如 "练习一般现在时与礼貌请求表达"


@dataclass
class WritingQuestion:
    """托福写作的一道题（2026 改革后两个主观题型之一）。

    与口语题库不同，写作题「一题一话题」：每个话题是一道独立题，
    无「主题 → 多题」二级层级。前端按话题卡片列出，点卡片进入作答。

    Attributes:
        task_type: "email"（写邮件）或 "discussion"（学术讨论）。
        title: 中文话题标题（卡片展示，如 "餐厅用餐反馈"）。
        prompt_en: 完整英文题目——邮件题含「背景 + 任务清单」；
            讨论题含「教授提问 + 两位同学回帖」。
        prompt_zh: 中文提示（可选，当前题库无，预留）。
        reference_answer: 参考范文（英文）。
    """

    id: int
    task_type: str          # "email" | "discussion"
    title: str              # 中文话题标题
    prompt_en: str          # 完整英文题目
    prompt_zh: str = ""     # 中文提示（预留）
    reference_answer: str = ""  # 参考范文
