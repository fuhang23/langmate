"""GetChatScenarioTool：从聊天场景库取一个主题场景。

供「聊天模式」（chat-mode Skill）的智能体在开场或学生要求换话题时调用，
从 services.corpus 的 chat_scenario 表取一个场景（随机或指定 id），
返回 title / context_prompt / teaching_point 文本，作为教学引导依据。

职责边界：本工具只「取场景」，不播报、不评分——播报由 SpeakTool 完成，
纠错/评分由 chat-mode Skill 引导智能体完成。
"""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ToolContext

from services.corpus import ChatScenario, CorpusStore, default_corpus_db_path


@tool_parameters({
    "type": "object",
    "properties": {
        "scenario_id": {
            "type": "integer",
            "description": "指定场景 id（可选）。不传则配合 random 取随机场景。",
        },
        "random": {
            "type": "boolean",
            "description": "随机取一个场景（默认 true）。为 false 且未传 scenario_id 时取第一个。",
        },
    },
})
class GetChatScenarioTool(Tool):
    """从聊天场景库取一个主题场景（随机或指定 id）。"""

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls()

    @property
    def name(self) -> str:
        return "get_chat_scenario"

    @property
    def description(self) -> str:
        return (
            "从聊天模式场景库取一个主题场景（含标题、情景说明、教学点），"
            "用于开场设定今天聊什么、重点练什么。学生要求换话题时再次调用。"
            "可选参数 scenario_id 指定场景，或 random=true 随机取一个。"
        )

    async def execute(
        self,
        scenario_id: int | None = None,
        random: bool = True,
        **kwargs: Any,
    ) -> Any:
        store = CorpusStore(default_corpus_db_path())

        scenario: ChatScenario | None = None
        if scenario_id is not None:
            scenario = store.get_chat_scenario(int(scenario_id))
        elif random:
            scenario = store.random_chat_scenario()
        else:
            scenarios = store.list_chat_scenarios()
            if scenarios:
                scenario = store.get_chat_scenario(int(scenarios[0]["id"]))

        if scenario is None:
            return "场景库为空，请先运行 seed 脚本预置聊天场景。"

        return (
            f"场景标题：{scenario.title}\n"
            f"情景说明：{scenario.context_prompt}\n"
            f"教学点：{scenario.teaching_point}\n"
            f"（请用中文向学生说明今天聊这个场景、重点练这个教学点，"
            f"然后用英文以开放式提问开始对话。）"
        )
