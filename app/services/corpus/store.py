"""CorpusStore：跟读题库的 SQLite 存储。

单机单用户，数据量小（约 30+ 场景 × 7 句），标准库 sqlite3，零额外依赖。
每个方法短连接、用完即关，避免跨线程复用连接的问题。

SQLite 文件默认落在 data/corpus.db（相对运行目录），
可用环境变量 LANGMATE_CORPUS_DB 覆盖。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from services.corpus.models import RepeatScenario, RepeatSentence

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repeat_scenario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    context_prompt TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS repeat_sentence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    chunks TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_repeat_sentence_scenario
    ON repeat_sentence(scenario_id);
"""

# 编号句子形如 "1. Begin by / washing ..."（序号 + 英文句号 + 空格）。
_SENTENCE_RE = re.compile(r"^(\d{1,2})\.\s+(.+)$")


def default_corpus_db_path() -> Path:
    """默认题库 SQLite 文件路径（可用环境变量覆盖）。"""
    env = os.environ.get("LANGMATE_CORPUS_DB")
    if env:
        return Path(env)
    return Path("data") / "corpus.db"


class CorpusStore:
    """跟读题库存储：建表、从 docx 导入、按场景/题号取题。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
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

    # -- 导入 -------------------------------------------------------------

    @staticmethod
    def _extract_paragraphs(docx_path: str | Path) -> list[str]:
        """从 docx（zip 容器）抽取段落文本，按段落分隔。"""
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        # 段落结束 → 换行；制表符 → 空白；其余标签剥除。
        xml = re.sub(r"<w:p[ >][^>]*>|<w:p>", "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
        xml = re.sub(r"<[^>]+>", "", xml)
        # 还原 XML 实体（&amp; 等）。
        import html

        return [
            html.unescape(line).strip()
            for line in xml.split("\n")
            if html.unescape(line).strip()
        ]

    def import_repeat_docx(self, docx_path: str | Path) -> int:
        """解析 listen and repeat.docx 并全量入库，返回导入的句子数。

        解析规则（结构已核实）：
        - 非编号短行 = 场景标题；
        - 紧跟标题的说明段 = 情景说明（context_prompt）；
        - "N. xxx" 编号行 = 句子，按 '/' 切意群。
        """
        paragraphs = self._extract_paragraphs(docx_path)

        current_scenario_id: int | None = None
        expecting_context = False
        imported = 0

        def _new_scenario(title: str) -> int:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO repeat_scenario (title, context_prompt)"
                    " VALUES (?, '')",
                    (title,),
                )
                conn.commit()
                return int(cur.lastrowid)

        def _set_context(sid: int, context: str) -> None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE repeat_scenario SET context_prompt = ? WHERE id = ?",
                    (context, sid),
                )
                conn.commit()

        def _add_sentence(sid: int, seq: int, text: str, chunks: list[str]) -> None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO repeat_sentence"
                    " (scenario_id, seq, text, chunks) VALUES (?, ?, ?, ?)",
                    (sid, seq, text, json.dumps(chunks, ensure_ascii=False)),
                )
                conn.commit()

        for para in paragraphs:
            m = _SENTENCE_RE.match(para)
            if m:
                # 编号句子：只有当前场景存在时才入库。
                if current_scenario_id is None:
                    continue
                seq = int(m.group(1))
                raw = m.group(2).strip()
                chunks = [c.strip() for c in raw.split("/") if c.strip()]
                text = " ".join(chunks)
                _add_sentence(current_scenario_id, seq, text, chunks)
                imported += 1
                expecting_context = False
            else:
                # 非编号行：若紧跟在场景标题后则是情景说明；否则是新场景标题。
                if expecting_context and current_scenario_id is not None:
                    _set_context(current_scenario_id, para)
                    expecting_context = False
                else:
                    current_scenario_id = _new_scenario(para)
                    expecting_context = True

        return imported

    # -- 查询 -------------------------------------------------------------

    def list_scenarios(self) -> list[dict[str, Any]]:
        """场景列表（供前端选择），每项含 id/title/context_prompt。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, context_prompt FROM repeat_scenario"
                " ORDER BY id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def scenario_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM repeat_scenario").fetchone()
        return int(row["cnt"]) if row else 0

    def get_scenario(self, scenario_id: int) -> RepeatScenario | None:
        """取某场景及其 7 句（按 seq 排序）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, context_prompt FROM repeat_scenario WHERE id = ?",
                (scenario_id,),
            ).fetchone()
            if row is None:
                return None
            sentences = conn.execute(
                "SELECT scenario_id, seq, text, chunks FROM repeat_sentence"
                " WHERE scenario_id = ? ORDER BY seq ASC",
                (scenario_id,),
            ).fetchall()

        return RepeatScenario(
            id=int(row["id"]),
            title=row["title"],
            context_prompt=row["context_prompt"],
            sentences=[
                RepeatSentence(
                    scenario_id=int(s["scenario_id"]),
                    seq=int(s["seq"]),
                    text=s["text"],
                    chunks=json.loads(s["chunks"]),
                )
                for s in sentences
            ],
        )

    def get_sentence(self, scenario_id: int, seq: int) -> RepeatSentence | None:
        """取某场景的第 seq 句。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT scenario_id, seq, text, chunks FROM repeat_sentence"
                " WHERE scenario_id = ? AND seq = ?",
                (scenario_id, seq),
            ).fetchone()
        if row is None:
            return None
        return RepeatSentence(
            scenario_id=int(row["scenario_id"]),
            seq=int(row["seq"]),
            text=row["text"],
            chunks=json.loads(row["chunks"]),
        )
