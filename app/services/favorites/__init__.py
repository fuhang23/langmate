"""核心表达收藏存储。

提供 FavoritesStore（建表/幂等增删/按主题分组）与例句本地提取工具。
中文释义由 HTTP 层调用 services.llm 生成后随收藏一起入库。
"""

from services.favorites.models import Favorite, FavoriteGroup
from services.favorites.store import FavoritesStore, default_db_path, extract_example

__all__ = [
    "Favorite",
    "FavoriteGroup",
    "FavoritesStore",
    "default_db_path",
    "extract_example",
]
