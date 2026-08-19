"""导入跟读题库：把 listen and repeat.docx 解析入库。

用法（在 app/ 目录下运行，保证 services 可 import）：
    python scripts/import_corpus.py [docx_path]

默认读 app/data/corpus/口语/listen and repeat.docx，写入 data/corpus.db。
运行后打印导入的场景数与句子数，便于校验。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把 app/ 加入 sys.path，确保 services 可 import（独立运行脚本时）。
APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.corpus import CorpusStore, default_corpus_db_path  # noqa: E402

DEFAULT_DOCX = APP_DIR / "data" / "corpus" / "口语" / "listen and repeat.docx"


def main() -> int:
    docx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOCX
    if not docx_path.exists():
        print(f"[错误] 找不到题库文件: {docx_path}")
        return 1

    store = CorpusStore(default_corpus_db_path())
    imported = store.import_repeat_docx(docx_path)

    scenarios = store.list_scenarios()
    print(f"导入完成：{imported} 句，{len(scenarios)} 个场景")
    print(f"数据库文件：{store.db_path}")
    print()
    for s in scenarios:
        sc = store.get_scenario(s["id"])
        print(f"  [{s['id']:>2}] {s['title']}  ({len(sc.sentences)} 句)")
        if sc and sc.sentences:
            first = sc.sentences[0]
            print(f"        例：{first.text[:60]}{'...' if len(first.text) > 60 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
