"""写作地道表达收藏存储（独立于口语核心表达收藏）。"""

from __future__ import annotations

from services.writing_favorites.models import (
    WritingFavorite,
    WritingFavoriteGroup,
)
from services.writing_favorites.store import (
    WritingFavoritesStore,
    default_db_path,
)

__all__ = [
    "WritingFavorite",
    "WritingFavoriteGroup",
    "WritingFavoritesStore",
    "default_db_path",
]
