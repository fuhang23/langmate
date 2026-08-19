"""跟读复述（Listen and Repeat）题库内容层。

与 services/progress（进度）职责分离：这里只存「内容」（场景 + 句子），
进度存 services/progress。题库来自本地资料 listen and repeat.docx，
结构化入库 SQLite，供跟读播放器按「场景 + 题号 + 意群」精确取题。
"""

from services.corpus.models import (
    InterviewQuestion,
    InterviewTopic,
    RepeatScenario,
    RepeatSentence,
)
from services.corpus.store import CorpusStore, default_corpus_db_path

__all__ = [
    "RepeatScenario",
    "RepeatSentence",
    "InterviewTopic",
    "InterviewQuestion",
    "CorpusStore",
    "default_corpus_db_path",
]
