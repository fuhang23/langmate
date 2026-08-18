"""LangMate 业务服务层。

纯 Python，不 import nanobot 内部，可独立测试、可随基座迁移。
按能力分模块：tts（语音合成）、pronunciation（发音评测）、
cefr（欧标能力底座）、orchestration（双轨融合）。
"""
