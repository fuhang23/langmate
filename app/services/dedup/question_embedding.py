"""题目题干向量缓存存储：供题目去重检测复用，避免每次采集都重复向量化已有题库。

独立 SQLite `data/dedup.db`（可用环境变量 LANGMATE_DEDUP_DB 覆盖）。
每行存一道题的题干文本 + 1024 维 embedding（JSON 数组），按 category 分组。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS question_embedding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    question_key TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(category, question_key)
);
CREATE INDEX IF NOT EXISTS idx_question_embedding_category
    ON question_embedding(category);
"""


def default_db_path() -> Path:
    env = os.environ.get("LANGMATE_DEDUP_DB")
    if env:
        return Path(env)
    return Path("data") / "dedup.db"


def question_key(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]


class QuestionEmbeddingStore:
    """题目题干 embedding 缓存存储。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def upsert(self, category: str, prompt_text: str, embedding: list[float]) -> None:
        """插入或更新一条题干向量（按 category + question_key 幂等）。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO question_embedding"
                " (category, question_key, prompt_text, embedding_json, created_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(category, question_key) DO UPDATE SET"
                " prompt_text=excluded.prompt_text,"
                " embedding_json=excluded.embedding_json",
                (
                    category,
                    question_key(prompt_text),
                    prompt_text,
                    json.dumps(embedding),
                    now,
                ),
            )
            conn.commit()

    def list_by_category(self, category: str) -> list[dict]:
        """返回某 category 下所有题干向量 [{prompt_text, embedding}]。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT prompt_text, embedding_json FROM question_embedding"
                " WHERE category = ? ORDER BY id ASC",
                (category,),
            ).fetchall()
        result: list[dict] = []
        for r in rows:
            try:
                embedding = json.loads(r["embedding_json"])
            except (ValueError, TypeError):
                continue
            result.append({"prompt_text": r["prompt_text"], "embedding": embedding})
        return result

    def count_by_category(self, category: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM question_embedding WHERE category = ?",
                (category,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def delete_by_prompt(self, category: str, prompt_text: str) -> int:
        """按 category + question_key 删除一条题干向量缓存，返回删除行数。

        用于删除题目或编辑改题干后清理旧向量，避免残留向量导致后续去重误判。
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM question_embedding"
                " WHERE category = ? AND question_key = ?",
                (category, question_key(prompt_text)),
            )
            conn.commit()
        return int(cur.rowcount)
