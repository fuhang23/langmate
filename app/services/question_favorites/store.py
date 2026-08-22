"""题目收藏的存储：四题型题目的星标收藏（question_key 唯一）。

与 services.favorites（口语核心表达收藏）、services.writing_favorites
（写作地道表达收藏）职责分离：这里收藏的是「题目本身」
（跟读场景 / 面试主题 / 写作题），供选题列表的星标与筛选使用。

question_key 格式（由后端判分/接口层拼接，前端只透传）：
- "repeat:{scenario_id}"
- "interview:{topic_id}"
- "writing:{question_id}"
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS question_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
"""


def default_db_path() -> Path:
    """默认 SQLite 文件路径（可用环境变量覆盖）。"""
    env = os.environ.get("LANGMATE_QUESTION_FAVORITES_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "toefl_question_favorites.db"


class QuestionFavoriteStore:
    """题目收藏存储：幂等增删 + key 列表查询。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # WAL + busy_timeout：跨进程并发安全。
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def add(self, question_key: str) -> bool:
        """收藏一道题（按 question_key 幂等，重复收藏无副作用）。

        Returns:
            True 表示本次新插入；False 表示已存在（幂等命中）。
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO question_favorites (question_key, created_at)"
                " VALUES (?, ?)",
                (question_key, now),
            )
            conn.commit()
        return cur.rowcount > 0

    def remove(self, question_key: str) -> bool:
        """取消收藏一道题。Returns: True 表示删除了一行。"""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM question_favorites WHERE question_key = ?",
                (question_key,),
            )
            conn.commit()
        return cur.rowcount > 0

    def list_keys(self) -> list[str]:
        """全部已收藏的 question_key（按收藏时间正序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT question_key FROM question_favorites ORDER BY id ASC"
            ).fetchall()
        return [r["question_key"] for r in rows]
