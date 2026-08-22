"""手动录题服务：四种题型的结构化录入 + AI 辅助生成 + 自动断句。"""

from services.manual.add import add_manual_question
from services.manual.generate import chunk_sentences, generate_reference

__all__ = ["add_manual_question", "generate_reference", "chunk_sentences"]
