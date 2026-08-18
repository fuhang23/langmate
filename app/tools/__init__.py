"""LangMate 的 nanobot Tool 适配层。

薄封装：把 services/ 的业务能力按 nanobot Tool 基类暴露给 agent。
通过 app/pyproject.toml 的 entry_points（group=nanobot.tools）注册，
经 `pip install -e app/` 后被 nanobot ToolLoader 自动发现。
"""

from tools.analyze_speech_tool import AnalyzeSpeechTool
from tools.speak_tool import SpeakTool

__all__ = ["AnalyzeSpeechTool", "SpeakTool"]
