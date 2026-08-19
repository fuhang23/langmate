"""预置聊天模式场景主题库。

用法（在 app/ 目录下运行）：
    python scripts/seed_chat_scenarios.py

幂等写入 data/corpus.db 的 chat_scenario 表（重复运行不重复插入）。
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.corpus import CorpusStore, default_corpus_db_path  # noqa: E402

# 聊天模式场景：标题（中英）/ 情景说明 / 教学点。
_SCENARIOS: list[dict[str, str]] = [
    {
        "title": "餐厅点餐 / Ordering at a Restaurant",
        "context_prompt": "You are ordering food at a restaurant. The waiter is ready to take your order.",
        "teaching_point": "练习礼貌请求表达（I'd like... / Could I have...）与一般现在时",
    },
    {
        "title": "校园生活 / Campus Life",
        "context_prompt": "You are a new student talking about your daily routine and classes.",
        "teaching_point": "练习一般现在时、时间介词与日常活动词汇",
    },
    {
        "title": "旅行出行 / Travel and Trips",
        "context_prompt": "You just came back from a trip and a friend is asking about it.",
        "teaching_point": "练习一般过去时、地点与交通方式表达",
    },
    {
        "title": "求职面试 / Job Interview",
        "context_prompt": "You are in a job interview, introducing yourself and your experience.",
        "teaching_point": "练习自我介绍、经历描述与现在完成时",
    },
    {
        "title": "购物 / Shopping",
        "context_prompt": "You are shopping for clothes and asking the shop assistant for help.",
        "teaching_point": "练习比较级、尺码颜色词汇与购物用语",
    },
    {
        "title": "健康与运动 / Health and Exercise",
        "context_prompt": "You are talking with a friend about your exercise habits and staying healthy.",
        "teaching_point": "练习频度副词（always/usually/sometimes）、运动与健康词汇",
    },
    {
        "title": "兴趣爱好 / Hobbies and Interests",
        "context_prompt": "You are telling a new friend about your hobbies and how you spend free time.",
        "teaching_point": "练习动名词（I enjoy + -ing）、兴趣相关表达",
    },
    {
        "title": "天气与季节 / Weather and Seasons",
        "context_prompt": "You are chatting about the weather today and your favorite season.",
        "teaching_point": "练习天气表达、季节词汇与比较级（warmer/cooler）",
    },
    {
        "title": "家庭与朋友 / Family and Friends",
        "context_prompt": "You are introducing your family or describing a close friend.",
        "teaching_point": "练习人物外貌性格描述、家庭成员词汇",
    },
    {
        "title": "工作与学习 / Work and Study",
        "context_prompt": "You are talking about your job or studies and your future plans.",
        "teaching_point": "练习将来时（be going to / will）、职业与学习规划表达",
    },
]


def main() -> int:
    store = CorpusStore(default_corpus_db_path())
    inserted = store.seed_chat_scenarios(_SCENARIOS)

    scenarios = store.list_chat_scenarios()
    print(f"预置完成：本次新增 {inserted} 个，当前共 {len(scenarios)} 个聊天场景")
    print(f"数据库文件：{store.db_path}")
    print()
    for s in scenarios:
        print(f"  [{s['id']:>2}] {s['title']}")
        print(f"       教学点：{s['teaching_point']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
