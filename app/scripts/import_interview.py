"""导入互动面试题库：把 互动面试.docx 解析入库。

用法（在 app/ 目录下运行）：
    python scripts/import_interview.py [docx_path]

默认读 app/data/corpus/口语/互动面试.docx，写入 data/corpus.db。
运行后打印导入的主题数与题数，便于校验。
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.corpus import CorpusStore, default_corpus_db_path  # noqa: E402

DEFAULT_DOCX = APP_DIR / "data" / "corpus" / "口语" / "互动面试.docx"


def main() -> int:
    docx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOCX
    if not docx_path.exists():
        print(f"[错误] 找不到题库文件: {docx_path}")
        return 1

    store = CorpusStore(default_corpus_db_path())
    imported = store.import_interview_docx(docx_path)

    topics = store.list_interview_topics()
    print(f"导入完成：{imported} 题，{len(topics)} 个主题")
    print(f"数据库文件：{store.db_path}")
    print()
    for t in topics:
        topic = store.get_interview_topic(t["id"])
        n = len(topic.questions) if topic else 0
        print(f"  [{t['id']:>2}] {t['title']}  ({n} 题)")
        if topic and topic.questions:
            q = topic.questions[0]
            has_ref = bool(q.reference_answer)
            has_expr = bool(q.core_expressions)
            print(f"       题1: {q.prompt_en[:50]}{'...' if len(q.prompt_en) > 50 else ''}")
            print(f"       参考回答: {'有' if has_ref else '无'} | 核心表达: {len(q.core_expressions)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
