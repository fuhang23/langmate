"""ProgressStore：练习进度的 SQLite 存储。

单机单用户，数据量小，直接用标准库 sqlite3，零额外依赖。
每个方法建立短连接、用完即关，避免跨线程复用连接的问题
（nanobot 的 HTTP/websocket 都可能触发写入/读取）。

SQLite 文件默认落在 app/data/toefl_progress.db（相对运行目录），
可用环境变量 LANGMATE_PROGRESS_DB 覆盖。该文件已在 .gitignore 中忽略。
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from services.progress.models import SECTIONS, PracticeRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS practice_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    question_type TEXT NOT NULL DEFAULT '',
    scores TEXT NOT NULL DEFAULT '{}',
    cefr TEXT NOT NULL DEFAULT '',
    weak_points TEXT NOT NULL DEFAULT '[]',
    question_key TEXT NOT NULL DEFAULT '',
    question_seq INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_section ON practice_records(section);
CREATE INDEX IF NOT EXISTS idx_records_created ON practice_records(created_at);
"""

# 老库幂等补列（CREATE TABLE IF NOT EXISTS 不会给旧表加列）。
_EXTRA_COLUMNS = (
    ("question_key", "TEXT NOT NULL DEFAULT ''"),
    ("question_seq", "INTEGER NOT NULL DEFAULT 0"),
)


def default_db_path() -> Path:
    """默认 SQLite 文件路径（可用环境变量覆盖）。"""
    env = os.environ.get("LANGMATE_PROGRESS_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "toefl_progress.db"


class ProgressStore:
    """练习记录存储：建表、插入、聚合查询。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # WAL + busy_timeout：跨进程（webui 运行中手动跑脚本）并发安全。
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # 老库幂等补列：PRAGMA table_info 检查后 ALTER TABLE。
            existing = {
                row["name"] for row in conn.execute("PRAGMA table_info(practice_records)")
            }
            for col, ddl in _EXTRA_COLUMNS:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE practice_records ADD COLUMN {col} {ddl}"
                    )
            # 索引依赖新列，须在补列之后创建。
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_question_key"
                " ON practice_records(question_key)"
            )
            conn.commit()

    def add_record(self, record: PracticeRecord) -> None:
        """写入一条练习记录。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO practice_records"
                " (section, question_type, scores, cefr, weak_points,"
                " question_key, question_seq, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.section,
                    record.question_type,
                    json.dumps(record.scores, ensure_ascii=False),
                    record.cefr,
                    json.dumps(record.weak_points, ensure_ascii=False),
                    record.question_key,
                    record.question_seq,
                    record.created_at,
                ),
            )
            conn.commit()

    def current_level(self, section: str) -> str | None:
        """某部分最近一次练习的 CEFR 级别（无记录返回 None）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cefr FROM practice_records"
                " WHERE section = ? AND cefr != ''"
                " ORDER BY id DESC LIMIT 1",
                (section,),
            ).fetchone()
        return row["cefr"] if row else None

    def practice_count(self, section: str) -> int:
        """某部分的累计练习次数。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM practice_records WHERE section = ?",
                (section,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def latest_updated_at(self, section: str) -> str | None:
        """某部分最近一次练习的时间（ISO 字符串）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM practice_records"
                " WHERE section = ?"
                " ORDER BY id DESC LIMIT 1",
                (section,),
            ).fetchone()
        return row["created_at"] if row else None

    def summary(self) -> dict[str, dict[str, Any]]:
        """仪表盘聚合：每个 section 返回 {level, count, updatedAt}。

        所有 section 都返回（无数据时 level/updatedAt 为 None、count 为 0），
        前端无需处理缺失键。
        """
        result: dict[str, dict[str, Any]] = {}
        for section in SECTIONS:
            result[section] = {
                "level": self.current_level(section),
                "count": self.practice_count(section),
                "updatedAt": self.latest_updated_at(section),
            }
        return result

    def question_stats(self) -> dict[str, dict[str, Any]]:
        """题目级练习统计：按 question_key 聚合。

        返回 {"repeat:12": {"count": 14, "covered": 7}, ...}：
        - count：该题判分事件总次数
        - covered：组内覆盖数（跟读 = 已练句子数、面试 = 已练题数；写作恒为 1）
        空 question_key（agent 对话链路 / 历史记录）不参与统计。

        covered 只统计 question_seq > 0 的记录：只传 question_key 不传
        sentence_seq 的旧数据（seq=0）不虚增覆盖数（7 句场景不会显示 8/7）。
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT question_key, COUNT(*) AS cnt,"
                " COUNT(DISTINCT CASE WHEN question_seq > 0 THEN question_seq END)"
                " AS covered"
                " FROM practice_records WHERE question_key != ''"
                " GROUP BY question_key"
            ).fetchall()
        return {
            row["question_key"]: {"count": int(row["cnt"]), "covered": int(row["covered"])}
            for row in rows
        }
