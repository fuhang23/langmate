"""IngestStore：内容采集记录存储（去重 + 溯源 + 重解析）。

单机单用户，SQLite（data/ingest.db）。每条记录保存原文 URL、抓取的原始
全文、大模型判断结果与状态，供去重、预览确认、失败重解析与版权溯源。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ingest_records_status
    ON ingest_records(status);
"""


def default_db_path() -> Path:
    env = os.environ.get("LANGMATE_INGEST_DB")
    if env:
        return Path(env)
    return Path("data") / "ingest.db"


class IngestStore:
    """内容采集记录存储。"""

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

    def upsert(
        self,
        *,
        url: str,
        title: str = "",
        source: str = "",
        raw_text: str = "",
        category: str = "",
        result_json: str = "",
        status: str = "pending",
    ) -> bool:
        """插入或更新一条记录（url 唯一）。返回是否为新记录。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existed = (
                conn.execute(
                    "SELECT 1 FROM ingest_records WHERE url = ?", (url,)
                ).fetchone()
                is not None
            )
            conn.execute(
                "INSERT INTO ingest_records"
                " (url, title, source, raw_text, category, result_json, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(url) DO UPDATE SET"
                " title=excluded.title, source=excluded.source, raw_text=excluded.raw_text,"
                " category=excluded.category, result_json=excluded.result_json,"
                " status=excluded.status",
                (url, title, source, raw_text, category, result_json, status, now),
            )
            conn.commit()
        return not existed

    def get(self, url: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ingest_records WHERE url = ?", (url,)
            ).fetchone()
        return dict(row) if row else None

    def set_status(self, url: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE ingest_records SET status = ? WHERE url = ?", (status, url)
            )
            conn.commit()

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, url, title, source, category, status, created_at"
                " FROM ingest_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
