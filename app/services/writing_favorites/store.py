"""WritingFavoritesStore：写作地道表达收藏的 SQLite 存储。

独立于口语 FavoritesStore（分表 writing_favorites），复用同样的单机单用户、
标准库 sqlite3、短连接模式。db 文件默认 data/toefl_writing_favorites.db，
可用环境变量 LANGMATE_WRITING_FAVORITES_DB 覆盖。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from services.writing_favorites.models import (
    WritingFavorite,
    WritingFavoriteGroup,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS writing_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expression TEXT NOT NULL UNIQUE,
    translation TEXT NOT NULL DEFAULT '',
    example TEXT NOT NULL DEFAULT '',
    task_type TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_writing_favorites_type
    ON writing_favorites(task_type);
"""


def default_db_path() -> Path:
    """默认 SQLite 文件路径（可用环境变量覆盖）。"""
    env = os.environ.get("LANGMATE_WRITING_FAVORITES_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "toefl_writing_favorites.db"


class WritingFavoritesStore:
    """写作地道表达收藏存储：建表、幂等增删、按题型分组查询。"""

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

    @staticmethod
    def _row_to_favorite(row: sqlite3.Row) -> WritingFavorite:
        return WritingFavorite(
            expression=row["expression"],
            translation=row["translation"],
            example=row["example"],
            task_type=row["task_type"],
            title=row["title"],
            created_at=row["created_at"],
        )

    def add(self, favorite: WritingFavorite) -> tuple[bool, WritingFavorite]:
        """幂等插入，返回 (是否新增, 库中完整记录)。"""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO writing_favorites"
                " (expression, translation, example, task_type, title, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    favorite.expression,
                    favorite.translation,
                    favorite.example,
                    favorite.task_type,
                    favorite.title,
                    favorite.created_at,
                ),
            )
            conn.commit()
            added = cur.rowcount > 0
        record = self.get(favorite.expression)
        return added, record if record else favorite

    def get(self, expression: str) -> WritingFavorite | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM writing_favorites WHERE expression = ?",
                (expression,),
            ).fetchone()
        return self._row_to_favorite(row) if row else None

    def remove(self, expression: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM writing_favorites WHERE expression = ?", (expression,)
            )
            conn.commit()
            return cur.rowcount > 0

    def list_grouped(self) -> list[WritingFavoriteGroup]:
        """读取全部收藏，按题型分组（email / discussion）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM writing_favorites ORDER BY id ASC"
            ).fetchall()

        groups: list[WritingFavoriteGroup] = []
        index: dict[str, WritingFavoriteGroup] = {}
        for row in rows:
            favorite = self._row_to_favorite(row)
            group = index.get(favorite.task_type)
            if group is None:
                group = WritingFavoriteGroup(task_type=favorite.task_type)
                index[favorite.task_type] = group
                groups.append(group)
            group.items.append(favorite)
        return groups
