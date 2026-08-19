"""学习进度存储层。

- models.py：PracticeRecord 模型 + SECTIONS 常量
- store.py：ProgressStore（SQLite 建表/插入/聚合查询）

供口语评分流程写入练习记录，供仪表盘 API 读取聚合数据。
"""

from services.progress.models import SECTION_LABELS, SECTIONS, PracticeRecord
from services.progress.record import record_from_analysis, record_speech_result
from services.progress.store import ProgressStore, default_db_path

__all__ = [
    "PracticeRecord",
    "ProgressStore",
    "SECTIONS",
    "SECTION_LABELS",
    "default_db_path",
    "record_speech_result",
    "record_from_analysis",
]
