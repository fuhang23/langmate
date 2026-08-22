"""FavoritesStore：核心表达收藏的 SQLite 存储。

仿照 ProgressStore 的成熟模式：单机单用户、标准库 sqlite3、短连接用完即关。
SQLite 文件默认落在 app/data/toefl_favorites.db（相对运行目录），
可用环境变量 LANGMATE_FAVORITES_DB 覆盖。该文件已加入 .gitignore。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from services.favorites.models import Favorite, FavoriteGroup

_SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expression TEXT NOT NULL UNIQUE,
    translation TEXT NOT NULL DEFAULT '',
    example TEXT NOT NULL DEFAULT '',
    topic_id INTEGER NOT NULL,
    topic_title TEXT NOT NULL DEFAULT '',
    question_seq INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_favorites_topic ON favorites(topic_id);
"""


def default_db_path() -> Path:
    """默认 SQLite 文件路径（可用环境变量覆盖）。"""
    env = os.environ.get("LANGMATE_FAVORITES_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "toefl_favorites.db"


def extract_example(reference_answer: str, expression: str) -> str:
    """从参考回答中本地提取包含该词组的句子作为例句。

    纯字符串操作、零成本：按 `.?!` 切句，找第一个「包含该词组（忽略
    大小写）」的句子，规整空白后返回。找不到返回空串。
    """
    if not reference_answer or not expression:
        return ""
    needle = expression.strip().lower()
    if not needle:
        return ""

    sentences: list[str] = []
    current: list[str] = []
    for ch in reference_answer:
        current.append(ch)
        if ch in ".!?":
            sentences.append("".join(current).strip())
            current = []
    if current:
        sentences.append("".join(current).strip())

    for sentence in sentences:
        if needle in sentence.lower():
            clean = " ".join(sentence.split())
            if clean:
                return clean
    return ""


class FavoritesStore:
    """核心表达收藏存储：建表、幂等增删、按主题分组查询。"""

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
    def _row_to_favorite(row: sqlite3.Row) -> Favorite:
        return Favorite(
            expression=row["expression"],
            translation=row["translation"],
            example=row["example"],
            topic_id=row["topic_id"],
            topic_title=row["topic_title"],
            question_seq=row["question_seq"],
            created_at=row["created_at"],
        )

    def get(self, expression: str) -> Favorite | None:
        """按词组查询一条收藏（不存在返回 None）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM favorites WHERE expression = ?", (expression,)
            ).fetchone()
        return self._row_to_favorite(row) if row else None

    def add(self, favorite: Favorite) -> tuple[bool, Favorite]:
        """幂等插入，返回 (是否新增, 库中的完整记录)。

        同一词组全局只存一条：已存在时直接返回旧记录（added=False），
        不做覆盖，保留首次收藏时的释义与出处。
        """
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO favorites"
                " (expression, translation, example, topic_id, topic_title,"
                "  question_seq, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    favorite.expression,
                    favorite.translation,
                    favorite.example,
                    favorite.topic_id,
                    favorite.topic_title,
                    favorite.question_seq,
                    favorite.created_at,
                ),
            )
            conn.commit()
            added = cur.rowcount > 0
        record = self.get(favorite.expression)
        return added, record if record else favorite

    def remove(self, expression: str) -> bool:
        """按词组删除收藏，返回是否确实删除了记录。"""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM favorites WHERE expression = ?", (expression,)
            )
            conn.commit()
            return cur.rowcount > 0

    def update_translation(self, expression: str, translation: str) -> bool:
        """更新某条收藏的中文释义（后台异步补释义用），返回是否命中记录。"""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE favorites SET translation = ? WHERE expression = ?",
                (translation, expression),
            )
            conn.commit()
            return cur.rowcount > 0

    def list_grouped(self) -> list[FavoriteGroup]:
        """读取全部收藏，按主题分组（保持收藏时间顺序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM favorites ORDER BY id ASC"
            ).fetchall()

        groups: list[FavoriteGroup] = []
        index: dict[int, FavoriteGroup] = {}
        for row in rows:
            favorite = self._row_to_favorite(row)
            group = index.get(favorite.topic_id)
            if group is None:
                group = FavoriteGroup(
                    topic_id=favorite.topic_id,
                    topic_title=favorite.topic_title,
                )
                index[favorite.topic_id] = group
                groups.append(group)
            group.items.append(favorite)
        return groups
