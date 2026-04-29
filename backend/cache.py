"""持久化缓存模块

带过期时间的 JSON 文件缓存，用于缓存岗位画像等数据。
默认缓存 90 天。
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import DATA_DIR

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 90
CACHE_FILE = DATA_DIR / "research_cache.json"


class ResearchCache:
    """岗位画像缓存，避免重复搜索"""

    def __init__(self):
        self._data: dict[str, dict] = {}
        self._load()

    def get(self, position: str) -> Optional[dict]:
        """获取缓存的岗位画像（如果未过期）"""
        entry = self._data.get(position)
        if not entry:
            return None

        expires = entry.get("_expires")
        if expires and datetime.fromisoformat(expires) < datetime.now():
            # 已过期
            del self._data[position]
            self._save()
            return None

        return entry.get("data")

    def set(self, position: str, data: dict):
        """缓存岗位画像"""
        expires = (datetime.now() + timedelta(days=CACHE_TTL_DAYS)).isoformat()
        self._data[position] = {"data": data, "_expires": expires, "_cached_at": datetime.now().isoformat()}
        self._save()

    def clear(self):
        """清空缓存"""
        self._data.clear()
        self._save()

    def stats(self) -> dict:
        """缓存统计"""
        now = datetime.now()
        valid = 0
        expired = 0
        for entry in self._data.values():
            expires = entry.get("_expires")
            if expires and datetime.fromisoformat(expires) > now:
                valid += 1
            else:
                expired += 1
        return {"total": len(self._data), "valid": valid, "expired": expired}

    def _load(self):
        try:
            if CACHE_FILE.exists():
                self._data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                logger.info(f"已加载缓存: {len(self._data)} 条")
        except Exception as e:
            logger.warning(f"缓存加载失败: {e}")

    def _save(self):
        try:
            CACHE_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"缓存保存失败: {e}")
