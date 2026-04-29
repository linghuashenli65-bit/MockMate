"""MySQL 数据库管理

提供会话、缓存、搜索历史的持久化存储。
如果 MySQL 不可用，自动回退到 JSON 文件存储。
"""
import json
import logging
import warnings
from datetime import datetime, timedelta
from typing import Optional

import aiomysql
from .config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, DATA_DIR

logger = logging.getLogger(__name__)

# 缓存 TTL
CACHE_TTL_DAYS = 90


class Database:
    """MySQL 数据库管理器"""

    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None
        self.available = False

    async def connect(self):
        """连接 MySQL，失败时标记不可用"""
        try:
            self.pool = await aiomysql.create_pool(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                db=MYSQL_DATABASE,
                charset="utf8mb4",
                autocommit=True,
                minsize=1,
                maxsize=5,
            )
            await self._init_tables()
            self.available = True
            logger.info("MySQL 连接成功")
        except Exception as e:
            self.available = False
            logger.warning(f"MySQL 不可用，使用 JSON 文件存储: {e}")

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def _init_tables(self):
        """初始化数据库表"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    await cur.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id VARCHAR(12) PRIMARY KEY,
                        position VARCHAR(255) DEFAULT '',
                        company VARCHAR(255) DEFAULT '',
                        round VARCHAR(20) DEFAULT '',
                        resume LONGTEXT,
                        profile JSON,
                        history JSON,
                        report JSON,
                        current_question JSON,
                        current_index INT DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_cache (
                        position VARCHAR(255) PRIMARY KEY,
                        data JSON,
                        summary VARCHAR(500) DEFAULT '',
                        skill_count INT DEFAULT 0,
                        topic_count INT DEFAULT 0,
                        expires_at DATETIME,
                        cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS search_history (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        position VARCHAR(255) NOT NULL,
                        summary VARCHAR(500) DEFAULT '',
                        skill_count INT DEFAULT 0,
                        topic_count INT DEFAULT 0,
                        tech_stack JSON,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_position (position),
                        INDEX idx_created (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                logger.info("数据库表初始化完成")

    # ==================== 会话管理 ====================

    async def save_session(self, session_id: str, data: dict):
        """保存或更新面试会话"""
        if not self.available:
            return await self._save_session_fallback(session_id, data)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO sessions (id, position, company, round, resume, profile, history, report,
                                         current_question, current_index, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        position=VALUES(position), company=VALUES(company),
                        round=VALUES(round),
                        resume=VALUES(resume), profile=VALUES(profile),
                        history=VALUES(history), report=VALUES(report),
                        current_question=VALUES(current_question),
                        current_index=VALUES(current_index)
                """, (
                    session_id,
                    data.get("position", ""),
                    data.get("company", ""),
                    data.get("round", ""),
                    data.get("resume", ""),
                    json.dumps(data.get("profile", {}), ensure_ascii=False),
                    json.dumps(data.get("history", []), ensure_ascii=False),
                    json.dumps(data.get("report", {}), ensure_ascii=False),
                    json.dumps(data.get("current_question", {}), ensure_ascii=False),
                    data.get("current_index", 0),
                    data.get("created_at", datetime.now().isoformat()),
                ))

    async def load_session(self, session_id: str) -> Optional[dict]:
        """加载面试会话"""
        if not self.available:
            return await self._load_session_fallback(session_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
                row = await cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return self._row_to_session(row, columns)

    async def list_sessions(self) -> list[dict]:
        """列出所有面试记录摘要"""
        if not self.available:
            return await self._list_sessions_fallback()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT id, position, company, round, created_at, history, report
                    FROM sessions ORDER BY created_at DESC LIMIT 50
                """)
                rows = await cur.fetchall()
                result = []
                for row in rows:
                    history = json.loads(row[5]) if row[5] else []
                    report = json.loads(row[6]) if row[6] else {}
                    result.append({
                        "id": row[0],
                        "position": row[1] or "未知",
                        "company": row[2] or "",
                        "round": row[3] or "",
                        "date": row[4].isoformat() if row[4] else "",
                        "total_questions": len(history),
                        "overall_score": report.get("overall_score", 0),
                    })
                return result

    async def delete_session(self, session_id: str) -> bool:
        """删除面试记录"""
        if not self.available:
            return await self._delete_session_fallback(session_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
                return cur.rowcount > 0

    def _row_to_session(self, row: tuple, columns: list) -> dict:
        """将数据库行转换为会话 dict"""
        data = dict(zip(columns, row))
        return {
            "id": data["id"],
            "position": data.get("position", ""),
            "company": data.get("company", ""),
            "round": data.get("round", ""),
            "resume": data.get("resume", ""),
            "profile": json.loads(data["profile"]) if data.get("profile") else {},
            "history": json.loads(data["history"]) if data.get("history") else [],
            "report": json.loads(data["report"]) if data.get("report") else {},
            "current_question": json.loads(data["current_question"]) if data.get("current_question") else {},
            "current_index": data.get("current_index", 0),
            "created_at": data["created_at"].isoformat() if data.get("created_at") else "",
        }

    # ==================== 缓存管理 ====================

    async def cache_get(self, position: str) -> Optional[dict]:
        """获取缓存的岗位画像"""
        if not self.available:
            return await self._cache_get_fallback(position)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT data, expires_at FROM research_cache WHERE position=%s",
                    (position,),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                if row[1] and row[1] < datetime.now():
                    await cur.execute("DELETE FROM research_cache WHERE position=%s", (position,))
                    return None
                return json.loads(row[0]) if row[0] else None

    async def cache_set(self, position: str, data: dict):
        """缓存岗位画像"""
        if not self.available:
            return await self._cache_set_fallback(position, data)
        expires = datetime.now() + timedelta(days=CACHE_TTL_DAYS)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO research_cache (position, data, summary, skill_count, topic_count, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        data=VALUES(data), summary=VALUES(summary),
                        skill_count=VALUES(skill_count), topic_count=VALUES(topic_count),
                        expires_at=VALUES(expires_at)
                """, (
                    position,
                    json.dumps(data, ensure_ascii=False),
                    data.get("summary", "")[:500],
                    len(data.get("required_skills", [])),
                    len(data.get("common_interview_topics", [])),
                    expires,
                ))

    async def cache_stats(self) -> dict:
        """缓存统计"""
        if not self.available:
            return await self._cache_stats_fallback()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT COUNT(*), SUM(CASE WHEN expires_at > NOW() THEN 1 ELSE 0 END)
                    FROM research_cache
                """)
                row = await cur.fetchone()
                total = row[0] or 0
                valid = row[1] or 0
                return {"total": total, "valid": valid, "expired": total - valid}

    async def cache_clear(self):
        """清空缓存"""
        if not self.available:
            return await self._cache_clear_fallback()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE research_cache")

    # ==================== 搜索历史 ====================

    async def save_search_history(self, position: str, data: dict):
        """记录搜索历史"""
        if not self.available:
            return
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO search_history (position, summary, skill_count, topic_count, tech_stack)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    position,
                    data.get("summary", "")[:500],
                    len(data.get("required_skills", [])),
                    len(data.get("common_interview_topics", [])),
                    json.dumps(data.get("tech_stack", []), ensure_ascii=False),
                ))

    async def get_search_history(self, limit: int = 20) -> list[dict]:
        """获取搜索历史"""
        if not self.available:
            return []
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, position, summary, skill_count, topic_count, created_at "
                    "FROM search_history ORDER BY created_at DESC LIMIT %s", (limit,)
                )
                rows = await cur.fetchall()
                return [
                    {
                        "id": r[0],
                        "position": r[1],
                        "summary": r[2] or "",
                        "skill_count": r[3],
                        "topic_count": r[4],
                        "date": r[5].isoformat() if r[5] else "",
                    }
                    for r in rows
                ]

    # ==================== JSON 文件回退 ====================

    _sessions_dir = DATA_DIR / "sessions"
    _cache_file = DATA_DIR / "research_cache.json"

    async def _save_session_fallback(self, session_id: str, data: dict):
        data["_updated_at"] = datetime.now().isoformat()
        fp = self._sessions_dir / f"{session_id}.json"
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _load_session_fallback(self, session_id: str) -> Optional[dict]:
        fp = self._sessions_dir / f"{session_id}.json"
        if fp.exists():
            return json.loads(fp.read_text(encoding="utf-8"))
        return None

    async def _list_sessions_fallback(self) -> list[dict]:
        sessions = []
        for fp in sorted(self._sessions_dir.glob("*.json"), reverse=True)[:50]:
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                sessions.append({
                    "id": fp.stem,
                    "position": data.get("position", "未知"),
                    "company": data.get("company", ""),
                    "round": data.get("round", ""),
                    "date": data.get("_updated_at", "")[:19],
                    "total_questions": len(data.get("history", [])),
                    "overall_score": data.get("report", {}).get("overall_score", 0),
                })
            except Exception:
                continue
        return sessions

    async def _delete_session_fallback(self, session_id: str) -> bool:
        fp = self._sessions_dir / f"{session_id}.json"
        if fp.exists():
            fp.unlink()
            return True
        return False

    async def _cache_get_fallback(self, position: str) -> Optional[dict]:
        try:
            if self._cache_file.exists():
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                entry = data.get(position)
                if entry:
                    expires = entry.get("_expires")
                    if expires and datetime.fromisoformat(expires) >= datetime.now():
                        return entry.get("data")
            return None
        except Exception:
            return None

    async def _cache_set_fallback(self, position: str, data: dict):
        try:
            cache_data = {}
            if self._cache_file.exists():
                cache_data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            expires = (datetime.now() + timedelta(days=CACHE_TTL_DAYS)).isoformat()
            cache_data[position] = {"data": data, "_expires": expires, "_cached_at": datetime.now().isoformat()}
            self._cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"缓存保存失败: {e}")

    async def _cache_stats_fallback(self) -> dict:
        try:
            if self._cache_file.exists():
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                now = datetime.now()
                valid = sum(1 for e in data.values()
                           if e.get("_expires") and datetime.fromisoformat(e["_expires"]) > now)
                return {"total": len(data), "valid": valid, "expired": len(data) - valid}
        except Exception:
            pass
        return {"total": 0, "valid": 0, "expired": 0}

    async def _cache_clear_fallback(self):
        if self._cache_file.exists():
            self._cache_file.write_text("{}", encoding="utf-8")


# 全局实例
db = Database()
