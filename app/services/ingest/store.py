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

# 扩展列（幂等迁移，旧库无这些列时 ALTER TABLE 补齐）。
_EXTRA_COLUMNS = (
    ("kind", "TEXT NOT NULL DEFAULT 'link'"),
    ("filename", "TEXT NOT NULL DEFAULT ''"),
    ("exam", "TEXT NOT NULL DEFAULT ''"),
    ("subject", "TEXT NOT NULL DEFAULT ''"),
    ("content_type", "TEXT NOT NULL DEFAULT ''"),
    ("summary_title", "TEXT NOT NULL DEFAULT ''"),
    ("deleted", "INTEGER NOT NULL DEFAULT 0"),
)


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
        self._migrate_extra_columns()

    def _migrate_extra_columns(self) -> None:
        """幂等补齐 kind/filename 列（旧库迁移）。"""
        with self._connect() as conn:
            existing = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(ingest_records)").fetchall()
            }
            for name, decl in _EXTRA_COLUMNS:
                if name not in existing:
                    conn.execute(f"ALTER TABLE ingest_records ADD COLUMN {name} {decl}")
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
        kind: str = "link",
        filename: str = "",
        exam: str = "",
        subject: str = "",
        content_type: str = "",
        summary_title: str = "",
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
                " (url, title, source, raw_text, category, result_json, status, created_at,"
                " kind, filename, exam, subject, content_type, summary_title, deleted)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)"
                " ON CONFLICT(url) DO UPDATE SET"
                " title=excluded.title, source=excluded.source, raw_text=excluded.raw_text,"
                " category=excluded.category, result_json=excluded.result_json,"
                " status=excluded.status, kind=excluded.kind, filename=excluded.filename,"
                " exam=excluded.exam, subject=excluded.subject, content_type=excluded.content_type,"
                " summary_title=excluded.summary_title, deleted=0",
                (
                    url, title, source, raw_text, category, result_json, status, now,
                    kind, filename, exam, subject, content_type, summary_title,
                ),
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
                "SELECT id, url, title, source, category, status, created_at, kind, filename,"
                " exam, subject, content_type"
                " FROM ingest_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_knowledge_base(
        self,
        *,
        subject: str | None = None,
        content_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """列出已入库（confirmed）的记录，带标签与知识点数量，供知识库浏览/筛选。

        chunks 数量从 result_json 解析；题目类入库的记录 category 非 rag，
        知识点数量为 0。仅返回 RAG 类与题目类（排除 ignore）。
        """
        clauses = ["status = 'confirmed'", "category != 'ignore'", "deleted = 0"]
        params: list[Any] = []
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, url, title, summary_title, source, category, status, created_at,"
                f" kind, filename, exam, subject, content_type, result_json"
                f" FROM ingest_records WHERE {where} ORDER BY id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["chunks"] = _count_chunks(item.pop("result_json", ""))
            result.append(item)
        return result

    def list_confirmed_rag(self) -> list[dict[str, Any]]:
        """返回所有已入库且未删除的 RAG 记录（供全量重建 ingested-articles 索引）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, title, kind, filename, subject, content_type, result_json"
                " FROM ingest_records WHERE status = 'confirmed' AND category = 'rag'"
                " AND deleted = 0 ORDER BY id ASC",
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_deleted(self, url: str) -> bool:
        """逻辑删除一条记录（deleted=1），不动向量索引。返回是否真的标记了记录。"""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE ingest_records SET deleted = 1 WHERE url = ?", (url,)
            )
            conn.commit()
            return cur.rowcount > 0

    def list_deleted_keys(self) -> list[str]:
        """返回所有已逻辑删除记录的 url（供检索时过滤僵尸向量）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url FROM ingest_records WHERE deleted = 1"
            ).fetchall()
        return [r["url"] for r in rows]

    def delete(self, url: str) -> bool:
        """物理删除一条记录。返回是否真的删除了记录。"""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM ingest_records WHERE url = ?", (url,))
            conn.commit()
            return cur.rowcount > 0


def _count_chunks(result_json: str) -> int:
    """从 result_json 解析 chunk 数量（解析失败返回 0）。"""
    if not result_json:
        return 0
    import json

    try:
        data = json.loads(result_json)
        chunks = data.get("chunks") or []
        return len(chunks) if isinstance(chunks, list) else 0
    except (ValueError, TypeError):
        return 0
