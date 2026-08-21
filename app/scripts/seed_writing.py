# -*- coding: utf-8 -*-
"""写作题库入库 + RAG 索引构建（一次性）。在 app/ 目录下运行：
    python scripts/seed_writing.py
"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# 加载 .env（与 run.bat 同逻辑，让 BAILIAN_API_KEY 生效）
_env = APP_DIR / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())


def main() -> int:
    from services.corpus import CorpusStore, default_corpus_db_path

    store = CorpusStore(default_corpus_db_path())
    disc = store.import_writing_docx(
        APP_DIR / "data" / "corpus" / "写作" / "学术讨论.docx", "discussion"
    )
    email = store.import_writing_docx(
        APP_DIR / "data" / "corpus" / "写作" / "邮件.docx", "email"
    )
    print(f"[1/2] 题库入库：学术讨论 {disc} 题，邮件 {email} 题")
    print(f"      数据库：{store.db_path}")

    # RAG 索引（需要 BAILIAN_API_KEY，已从 .env 加载）
    try:
        from services.rag.ingest_lesson_plan import ingest

        n = ingest()
        print(f"[2/2] RAG 索引：{n} 个 chunk 已向量化")
    except Exception as exc:
        print(f"[2/2] RAG 索引失败（判分仍可用，仅缺教学法增强）：{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
