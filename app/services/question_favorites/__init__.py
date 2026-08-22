"""题目收藏服务：四题型题目的星标收藏（question_key 唯一键）。"""

from services.question_favorites.store import (
    QuestionFavoriteStore,
    default_db_path,
)

__all__ = [
    "QuestionFavoriteStore",
    "default_db_path",
]
