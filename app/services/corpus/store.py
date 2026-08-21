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

from services.corpus.models import (
    ChatScenario,
    InterviewQuestion,
    InterviewTopic,
    RepeatScenario,
    RepeatSentence,
    WritingQuestion,
)

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

CREATE TABLE IF NOT EXISTS interview_topic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS interview_question (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    prompt_en TEXT NOT NULL,
    prompt_zh TEXT NOT NULL DEFAULT '',
    reference_answer TEXT NOT NULL DEFAULT '',
    core_expressions TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_interview_question_topic
    ON interview_question(topic_id);

CREATE TABLE IF NOT EXISTS chat_scenario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    context_prompt TEXT NOT NULL DEFAULT '',
    teaching_point TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS writing_question (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt_en TEXT NOT NULL DEFAULT '',
    prompt_zh TEXT NOT NULL DEFAULT '',
    reference_answer TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_writing_question_type
    ON writing_question(task_type);
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

    # -- 互动面试 ---------------------------------------------------------

    def import_interview_docx(self, docx_path: str | Path) -> int:
        """解析互动面试.docx 并全量入库，返回导入的题数。

        资料有两种格式混合，解析器统一处理：

        格式 A（Reading/Hobbies 等）：
            主题标题（中文，无 ## / ** 前缀）
            ## 第 N 题  →  ## 题目（或 **题目：**）
              > 英文题目   > 中文翻译
              ## 参考回答（或 **参考回答：**）  > 英文范文
              **核心表达（黄色高亮）：** 词组 / 词组
        格式 B（公园/网购等）：
            主题标题（中文）
            英文场景设定（You have signed up ...）
            N. 中文要点（维度）
            N. First... 英文题目   →   英文参考回答
        """
        paragraphs = self._extract_paragraphs(docx_path)

        # 预扫描：把「加粗」与「核心表达」等标记还原为纯文本（加粗不用于解析，
        # 核心表达是独立字段）。这里只做文本清理，不依赖加粗。
        return self._parse_interview(paragraphs)

    def _parse_interview(self, paragraphs: list[str]) -> int:
        """互动面试解析状态机。"""
        import re as _re

        # 主题标题：非 ##、非 **、非 >、非编号、非纯英文场景、非空。
        def _is_topic_title(p: str) -> bool:
            if not p or p.startswith(("##", ">", "**")):
                return False
            if _re.match(r"^\d{1,2}\.", p):
                return False
            # 场景设定是纯英文长句，主题标题含中文或短中文。
            return bool(_re.search(r"[\u4e00-\u9fff]", p))

        imported = 0
        topic_id: int | None = None
        # 当前题目的暂存字段
        cur_seq = 0
        cur_prompt_en: list[str] = []
        cur_prompt_zh: list[str] = []
        cur_ref: list[str] = []
        cur_expr: list[str] = []
        # 状态：在题目块 / 参考块 / 核心表达块
        in_prompt = False
        in_ref = False

        def _flush_question() -> None:
            nonlocal imported
            if topic_id is None or cur_seq == 0:
                return
            en = " ".join(x.strip() for x in cur_prompt_en if x.strip())
            zh = " ".join(x.strip() for x in cur_prompt_zh if x.strip())
            ref = " ".join(x.strip() for x in cur_ref if x.strip())
            expr = [e.strip() for e in cur_expr if e.strip()]
            # 清理字面加粗标记 **（作者用它标注核心词组）。
            en = _re.sub(r"\*\*", "", en)
            zh = _re.sub(r"\*\*", "", zh)
            ref = _re.sub(r"\*\*", "", ref)
            if en or ref:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO interview_question"
                        " (topic_id, seq, prompt_en, prompt_zh, reference_answer,"
                        " core_expressions) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            topic_id,
                            cur_seq,
                            en,
                            zh,
                            ref,
                            json.dumps(expr, ensure_ascii=False),
                        ),
                    )
                    conn.commit()
                imported += 1

        def _reset_question() -> None:
            nonlocal cur_seq, cur_prompt_en, cur_prompt_zh, cur_ref, cur_expr
            cur_prompt_en, cur_prompt_zh, cur_ref, cur_expr = [], [], [], []

        for p in paragraphs:
            t = p.strip()

            # 主题标题
            if _is_topic_title(t):
                _flush_question()
                _reset_question()
                cur_seq = 0
                with self._connect() as conn:
                    cur = conn.execute(
                        "INSERT INTO interview_topic (title, description) VALUES (?, '')",
                        (t,),
                    )
                    conn.commit()
                    topic_id = int(cur.lastrowid)
                continue

            # 新题：## 第 N 题
            m = _re.match(r"^##\s*第\s*(\d+)\s*题", t)
            if m:
                _flush_question()
                _reset_question()
                cur_seq = int(m.group(1))
                continue

            # 题目标记：## 题目 / **题目：**
            if t in ("## 题目",) or t.startswith("**题目") or t == "题目：":
                _reset_question()
                in_prompt = True
                in_ref = False
                continue

            # 参考回答标记
            if t in ("## 参考回答",) or t.startswith("**参考回答") or t == "参考回答：":
                in_prompt = False
                in_ref = True
                continue

            # 核心表达标记
            if t.startswith("**核心表达") or t.startswith("核心表达"):
                in_ref = False
                # 提取 "词组 / 词组"（清理残留的 ** 加粗标记）。
                content = _re.sub(r"^[^:]*[:：]\s*", "", t)
                content = _re.sub(r"\*\*", "", content)
                cur_expr = [e.strip() for e in content.split("/") if e.strip()]
                continue

            # 分隔线 / 空行
            if not t or t in ("---", "***", "___"):
                continue

            # 引用行：> ...
            if t.startswith(">"):
                content = _re.sub(r"^>\s*", "", t).strip()
                if not content:
                    continue
                if in_prompt:
                    # 第一个英文行是 prompt_en，中文行是 prompt_zh
                    if _re.search(r"[\u4e00-\u9fff]", content):
                        cur_prompt_zh.append(content)
                    else:
                        cur_prompt_en.append(content)
                elif in_ref:
                    cur_ref.append(content)
                continue

            # 格式 B：编号 + 英文题目（如 "1. First, can you tell me..."）
            mb = _re.match(r"^(\d{1,2})\.\s+(.+)$", t)
            if mb and _re.search(r"[a-zA-Z]{4,}", mb.group(2)):
                # 判断是「中文要点」（含中文）还是「英文题目」
                if _re.search(r"[\u4e00-\u9fff]", mb.group(2)):
                    continue  # 中文要点，跳过
                _flush_question()
                _reset_question()
                cur_seq = int(mb.group(1))
                cur_prompt_en.append(mb.group(2).strip())
                in_prompt = False
                in_ref = True
                continue

            # 格式 B：纯英文段落（参考回答，紧跟英文题目之后）
            if in_ref and cur_seq > 0 and _re.search(r"[a-zA-Z]{4,}", t):
                cur_ref.append(t)
                continue

        _flush_question()
        return imported

    def list_interview_topics(self) -> list[dict[str, Any]]:
        """面试主题列表（含题数），供前端选择。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.id, t.title, t.description, COUNT(q.id) AS cnt"
                " FROM interview_topic t LEFT JOIN interview_question q"
                " ON q.topic_id = t.id GROUP BY t.id ORDER BY t.id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_interview_topic(self, topic_id: int) -> InterviewTopic | None:
        """取某面试主题及其 4 题。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, description FROM interview_topic WHERE id = ?",
                (topic_id,),
            ).fetchone()
            if row is None:
                return None
            questions = conn.execute(
                "SELECT topic_id, seq, prompt_en, prompt_zh, reference_answer,"
                " core_expressions FROM interview_question"
                " WHERE topic_id = ? ORDER BY seq ASC",
                (topic_id,),
            ).fetchall()

        return InterviewTopic(
            id=int(row["id"]),
            title=row["title"],
            description=row["description"],
            questions=[
                InterviewQuestion(
                    topic_id=int(q["topic_id"]),
                    seq=int(q["seq"]),
                    prompt_en=q["prompt_en"],
                    prompt_zh=q["prompt_zh"],
                    reference_answer=q["reference_answer"],
                    core_expressions=json.loads(q["core_expressions"]),
                )
                for q in questions
            ],
        )

    # -- 聊天模式场景 -----------------------------------------------------

    def seed_chat_scenarios(self, scenarios: list[dict[str, str]]) -> int:
        """幂等预置聊天场景，返回本次新插入的条数。

        Args:
            scenarios: 每个 dict 含 title / context_prompt / teaching_point。
        """
        inserted = 0
        with self._connect() as conn:
            for s in scenarios:
                title = s.get("title", "").strip()
                if not title:
                    continue
                exists = conn.execute(
                    "SELECT id FROM chat_scenario WHERE title = ?", (title,)
                ).fetchone()
                if exists is not None:
                    continue
                conn.execute(
                    "INSERT INTO chat_scenario (title, context_prompt, teaching_point)"
                    " VALUES (?, ?, ?)",
                    (
                        title,
                        s.get("context_prompt", "").strip(),
                        s.get("teaching_point", "").strip(),
                    ),
                )
                inserted += 1
            conn.commit()
        return inserted

    def list_chat_scenarios(self) -> list[dict[str, Any]]:
        """聊天场景列表，每项含 id/title/context_prompt/teaching_point。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, context_prompt, teaching_point"
                " FROM chat_scenario ORDER BY id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def chat_scenario_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM chat_scenario").fetchone()
        return int(row["cnt"]) if row else 0

    def get_chat_scenario(self, scenario_id: int) -> ChatScenario | None:
        """取指定 id 的聊天场景。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, context_prompt, teaching_point"
                " FROM chat_scenario WHERE id = ?",
                (scenario_id,),
            ).fetchone()
        if row is None:
            return None
        return ChatScenario(
            id=int(row["id"]),
            title=row["title"],
            context_prompt=row["context_prompt"],
            teaching_point=row["teaching_point"],
        )

    def random_chat_scenario(self) -> ChatScenario | None:
        """随机取一个聊天场景（无场景时返回 None）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, context_prompt, teaching_point"
                " FROM chat_scenario ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return ChatScenario(
            id=int(row["id"]),
            title=row["title"],
            context_prompt=row["context_prompt"],
            teaching_point=row["teaching_point"],
        )

    # -- 托福写作 ---------------------------------------------------------

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """清理 docx 里残留的 markdown 加粗、引用前缀与图片批注标记。"""
        text = re.sub(r"\*\*", "", text)
        text = re.sub(r">\s*", "", text)
        text = re.sub(r"【图片批注[：:][^】]*】", "", text)
        text = re.sub(r"【[^】]*图片[^】]*】", "", text)
        return text.strip()

    def import_writing_docx(self, docx_path: str | Path, task_type: str) -> int:
        """解析写作题库 docx 并全量入库，返回导入的题数。

        Args:
            docx_path: 学术讨论.docx 或 邮件.docx。
            task_type: "discussion" 或 "email"。
        """
        paragraphs = self._extract_paragraphs(docx_path)
        if task_type == "discussion":
            items = self._parse_writing_discussion(paragraphs)
        elif task_type == "email":
            items = self._parse_writing_email(paragraphs)
        else:
            raise ValueError(f"未知写作题型: {task_type}")

        imported = 0
        with self._connect() as conn:
            # 幂等：先清空该题型的旧记录再全量重建，避免重复跑 seed 时重复插入。
            conn.execute("DELETE FROM writing_question WHERE task_type = ?", (task_type,))
            for it in items:
                title = it.get("title", "").strip()
                prompt_en = self._clean_markdown(" ".join(it.get("prompt", [])).strip())
                ref = self._clean_markdown(" ".join(it.get("essay", [])).strip())
                if not title or not prompt_en:
                    continue
                conn.execute(
                    "INSERT INTO writing_question"
                    " (task_type, title, prompt_en, prompt_zh, reference_answer)"
                    " VALUES (?, ?, ?, '', ?)",
                    (task_type, title, prompt_en, ref),
                )
                imported += 1
            conn.commit()
        return imported

    @staticmethod
    def _parse_writing_discussion(paragraphs: list[str]) -> list[dict[str, Any]]:
        """解析学术讨论.docx 为题目列表。

        结构：中文标题 → (可选 instruction 块) → 教授标记+提问 →
        学生一标记+回帖 → 学生二标记+回帖 → 范文（多数无标记，
        直接是学生二之后的非 > 英文段落；少数有 ## 图二：范文 标记）。
        """
        questions: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        # state: title / professor / student1 / student2 / essay
        state = "title"

        def _flush() -> None:
            nonlocal cur
            if cur and cur.get("title") and cur.get("prompt"):
                questions.append(cur)
            cur = None

        for raw in paragraphs:
            t = raw.strip()
            if not t or t == "---" or t in ("***", "___"):
                continue
            # 中文标题（不含标记前缀）→ 新题
            if (
                re.search(r"[\u4e00-\u9fff]", t)
                and not t.startswith(("##", "**", ">"))
                and "范文" not in t
            ):
                _flush()
                cur = {"title": t, "prompt": [], "essay": []}
                state = "title"
                continue
            # 范文标记：## 图二：范文 / ## 参考范文
            if t.startswith("##") and "范文" in t:
                state = "essay"
                continue
            # 教授 / 学生角色标记
            if "教授" in t or "学生" in t:
                if "教授" in t:
                    state = "professor"
                elif "学生一" in t:
                    state = "student1"
                elif "学生二" in t:
                    state = "student2"
                continue
            # 引用行 > ...
            if t.startswith(">"):
                content = re.sub(r"^>\s*", "", t).strip()
                if not content:
                    continue
                if state == "essay" and cur is not None:
                    cur["essay"].append(content)
                elif cur is not None:
                    cur["prompt"].append(content)
                continue
            # 非引用英文行：学生二之后 → 范文；否则（instruction 等）→ prompt
            if state in ("student2", "essay") and cur is not None:
                cur["essay"].append(t)
                state = "essay"
            elif cur is not None:
                cur["prompt"].append(t)

        _flush()
        return questions

    @staticmethod
    def _parse_writing_email(paragraphs: list[str]) -> list[dict[str, Any]]:
        """解析邮件.docx 为题目列表。

        结构：标题（中文场景名或英文标题）→ 背景 → 任务清单 → 范文
        （以 Dear/Hi/Hello 开头）。兼容前几题的 ## 图二/图三 范文标记格式。
        """
        questions: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        # state: title / prompt / essay
        state = "title"
        markers = ("**题目背景", "**任务要求", "**Your Response")

        def _flush() -> None:
            nonlocal cur
            if cur and cur.get("title") and cur.get("prompt") and cur.get("essay"):
                questions.append(cur)
            cur = None

        def _is_greeting(line: str) -> bool:
            s = line.lstrip(">").strip()
            return bool(re.match(r"^(Dear|Hi|Hello|Hey)\b", s, re.IGNORECASE))

        n = len(paragraphs)
        for i, raw in enumerate(paragraphs):
            t = raw.strip()
            if not t or t == "---" or t in ("***", "___") or t.startswith("##"):
                continue
            # 标记行
            if t.startswith(markers):
                state = "essay" if t.startswith("**Your Response") else "prompt"
                continue
            # 判断是否新标题
            is_title = False
            if state == "title":
                is_title = True
            elif state == "essay":
                # 中文标题（独立行，不以 > 开头；范文里嵌入的【图片批注】是 > 引用行，须排除），
                # 或英文标题（下一行是 --- 或 **题目背景）。
                if re.search(r"[\u4e00-\u9fff]", t) and not t.startswith(">"):
                    is_title = True
                elif not t.startswith(">") and not re.search(r"[\u4e00-\u9fff]", t):
                    nxt = paragraphs[i + 1].strip() if i + 1 < n else ""
                    if nxt == "---" or nxt.startswith("**题目背景"):
                        is_title = True
            if is_title:
                _flush()
                cur = {"title": t, "prompt": [], "essay": []}
                state = "prompt"
                continue
            if cur is None:
                continue
            # 范文开始（邮件问候语）
            if state == "prompt" and _is_greeting(t):
                state = "essay"
                cur["essay"].append(t)
                continue
            # 归入当前状态
            if state == "essay":
                cur["essay"].append(t)
            else:
                cur["prompt"].append(t)

        _flush()
        return questions

    def list_writing_questions(self, task_type: str) -> list[dict[str, Any]]:
        """某题型的题目卡片列表（id/title/task_type），供前端话题卡片。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, task_type, title FROM writing_question"
                " WHERE task_type = ? ORDER BY id ASC",
                (task_type,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_writing_question(self, question_id: int) -> WritingQuestion | None:
        """取指定 id 的写作题。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, task_type, title, prompt_en, prompt_zh, reference_answer"
                " FROM writing_question WHERE id = ?",
                (question_id,),
            ).fetchone()
        if row is None:
            return None
        return WritingQuestion(
            id=int(row["id"]),
            task_type=row["task_type"],
            title=row["title"],
            prompt_en=row["prompt_en"],
            prompt_zh=row["prompt_zh"],
            reference_answer=row["reference_answer"],
        )

    def writing_question_count(self, task_type: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM writing_question WHERE task_type = ?",
                (task_type,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    # -- 内容采集：结构化 dict 批量入库（幂等） ---------------------------

    def add_writing_questions(self, items: list[dict[str, Any]]) -> int:
        """批量插入写作题（来自内容采集的大模型输出）。幂等：task_type+title 去重。"""
        added = 0
        for it in items:
            task_type = (it.get("task_type") or "").strip()
            title = (it.get("title") or "").strip()
            prompt_en = (it.get("prompt_en") or "").strip()
            reference_answer = (it.get("reference_answer") or "").strip()
            if task_type not in ("email", "discussion") or not title or not prompt_en:
                continue
            with self._connect() as conn:
                dup = conn.execute(
                    "SELECT 1 FROM writing_question WHERE task_type = ? AND title = ?",
                    (task_type, title),
                ).fetchone()
                if dup:
                    continue
                conn.execute(
                    "INSERT INTO writing_question"
                    " (task_type, title, prompt_en, prompt_zh, reference_answer)"
                    " VALUES (?, ?, ?, '', ?)",
                    (task_type, title, prompt_en, reference_answer),
                )
                conn.commit()
            added += 1
        return added

    def add_speaking_repeat(self, items: list[dict[str, Any]]) -> int:
        """插入跟读场景+句子（来自内容采集）。幂等：scenario title 去重。"""
        added = 0
        for it in items:
            title = (it.get("title") or "").strip()
            sentences = it.get("sentences") or []
            if not title or not sentences:
                continue
            with self._connect() as conn:
                dup = conn.execute(
                    "SELECT 1 FROM repeat_scenario WHERE title = ?", (title,)
                ).fetchone()
                if dup:
                    continue
                cur = conn.execute(
                    "INSERT INTO repeat_scenario (title, context_prompt) VALUES (?, '')",
                    (title,),
                )
                sid = int(cur.lastrowid)
                for s in sentences:
                    text = (s.get("text") or "").strip()
                    if not text:
                        continue
                    chunks = s.get("chunks") or []
                    if isinstance(chunks, str):
                        chunks = [c.strip() for c in chunks.split("/") if c.strip()]
                    try:
                        seq = int(s.get("seq", 0))
                    except (TypeError, ValueError):
                        seq = 0
                    conn.execute(
                        "INSERT INTO repeat_sentence (scenario_id, seq, text, chunks)"
                        " VALUES (?, ?, ?, ?)",
                        (sid, seq, text, json.dumps(chunks, ensure_ascii=False)),
                    )
                conn.commit()
            added += 1
        return added

    def add_speaking_interview(self, items: list[dict[str, Any]]) -> int:
        """插入面试主题+题（来自内容采集）。幂等：topic title 去重。"""
        added = 0
        for it in items:
            title = (it.get("title") or "").strip()
            questions = it.get("questions") or []
            if not title or not questions:
                continue
            with self._connect() as conn:
                dup = conn.execute(
                    "SELECT 1 FROM interview_topic WHERE title = ?", (title,)
                ).fetchone()
                if dup:
                    continue
                cur = conn.execute(
                    "INSERT INTO interview_topic (title, description) VALUES (?, '')",
                    (title,),
                )
                tid = int(cur.lastrowid)
                for q in questions:
                    prompt_en = (q.get("prompt_en") or "").strip()
                    if not prompt_en:
                        continue
                    prompt_zh = (q.get("prompt_zh") or "").strip()
                    reference_answer = (q.get("reference_answer") or "").strip()
                    core = q.get("core_expressions") or []
                    if isinstance(core, str):
                        core = [core]
                    try:
                        seq = int(q.get("seq", 0))
                    except (TypeError, ValueError):
                        seq = 0
                    conn.execute(
                        "INSERT INTO interview_question"
                        " (topic_id, seq, prompt_en, prompt_zh, reference_answer,"
                        " core_expressions) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            tid,
                            seq,
                            prompt_en,
                            prompt_zh,
                            reference_answer,
                            json.dumps(core, ensure_ascii=False),
                        ),
                    )
                conn.commit()
            added += 1
        return added
