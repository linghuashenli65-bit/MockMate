"""MySQL 数据库管理

提供会话、缓存、搜索历史的持久化存储。
如果 MySQL 不可用，自动回退到 JSON 文件存储。
多用户模式下，所有数据查询按 user_id 隔离。
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
                        user_id INT DEFAULT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_user_id (user_id)
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
                        user_id INT DEFAULT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_user_id (user_id),
                        INDEX idx_created (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                    await cur.execute("""
                    CREATE TABLE IF NOT EXISTS favorites (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        session_id VARCHAR(12) DEFAULT '',
                        question TEXT NOT NULL,
                        type VARCHAR(20) DEFAULT '',
                        difficulty VARCHAR(10) DEFAULT '',
                        topic VARCHAR(100) DEFAULT '',
                        user_answer TEXT,
                        overall_score INT DEFAULT 0,
                        notes TEXT,
                        user_id INT DEFAULT NULL,
                        saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                    await cur.execute("""
                    CREATE TABLE IF NOT EXISTS custom_questions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        question TEXT NOT NULL,
                        type VARCHAR(20) DEFAULT '技术',
                        difficulty VARCHAR(10) DEFAULT 'medium',
                        topic VARCHAR(100) DEFAULT '',
                        expected_points JSON,
                        tags VARCHAR(200) DEFAULT '',
                        user_id INT DEFAULT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                    await cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INT PRIMARY KEY,
                        provider VARCHAR(20) DEFAULT 'mimo',
                        mimo_key TEXT,
                        deepseek_key TEXT,
                        qwen_key TEXT,
                        zhipu_key TEXT,
                        models JSON,
                        tts_enabled TINYINT DEFAULT 1,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                    # 迁移：补齐旧表可能缺失的字段
                    for tbl, col, definition in [
                        ("sessions", "user_id", "INT DEFAULT NULL"),
                        ("search_history", "user_id", "INT DEFAULT NULL"),
                        ("favorites", "user_id", "INT DEFAULT NULL"),
                        ("custom_questions", "user_id", "INT DEFAULT NULL"),
                    ]:
                        try:
                            await cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {definition}")
                        except Exception:
                            pass  # 字段已存在则忽略
                    # 迁移：补齐缺失的索引
                    for tbl, idx, col in [
                        ("sessions", "idx_user_id", "user_id"),
                        ("favorites", "idx_fav_user_saved", "user_id, saved_at"),
                    ]:
                        try:
                            await cur.execute(f"CREATE INDEX {idx} ON {tbl} ({col})")
                        except Exception:
                            pass
                    logger.info("数据库表初始化完成")

    # ==================== 用户设置 ====================

    async def get_user_settings(self, user_id: int) -> Optional[dict]:
        """获取用户设置；未配置时返回 None"""
        if not self.available:
            return self._get_user_settings_fallback(user_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT provider, mimo_key, deepseek_key, qwen_key, zhipu_key, models, tts_enabled "
                    "FROM user_settings WHERE user_id=%s",
                    (user_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                models = row.get("models") or {}
                if isinstance(models, str):
                    try:
                        models = json.loads(models)
                    except Exception:
                        models = {}
                return {
                    "provider": row.get("provider") or "mimo",
                    "keys": {
                        "mimo": row.get("mimo_key") or "",
                        "deepseek": row.get("deepseek_key") or "",
                        "qwen": row.get("qwen_key") or "",
                        "zhipu": row.get("zhipu_key") or "",
                    },
                    "models": models if isinstance(models, dict) else {},
                    "tts_enabled": bool(row.get("tts_enabled", 1)),
                }

    async def save_user_settings(self, user_id: int, data: dict) -> None:
        """保存用户设置（整体覆盖存储字段）"""
        if not self.available:
            return self._save_user_settings_fallback(user_id, data)
        keys = data.get("keys", {})
        models = data.get("models", {})
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO user_settings (user_id, provider, mimo_key, deepseek_key, qwen_key, zhipu_key, models, tts_enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        provider=VALUES(provider),
                        mimo_key=VALUES(mimo_key),
                        deepseek_key=VALUES(deepseek_key),
                        qwen_key=VALUES(qwen_key),
                        zhipu_key=VALUES(zhipu_key),
                        models=VALUES(models),
                        tts_enabled=VALUES(tts_enabled)
                    """,
                    (
                        user_id,
                        data.get("provider", "mimo"),
                        keys.get("mimo", ""),
                        keys.get("deepseek", ""),
                        keys.get("qwen", ""),
                        keys.get("zhipu", ""),
                        json.dumps(models, ensure_ascii=False),
                        1 if data.get("tts_enabled", True) else 0,
                    ),
                )

    def _get_user_settings_fallback(self, user_id: int) -> Optional[dict]:
        """JSON 文件回退：读取用户设置"""
        all_settings = self._load_user_settings_file()
        return all_settings.get(str(user_id))

    def _save_user_settings_fallback(self, user_id: int, data: dict) -> None:
        """JSON 文件回退：保存用户设置"""
        all_settings = self._load_user_settings_file()
        merged = dict(all_settings.get(str(user_id), {}))
        merged.update(data)
        all_settings[str(user_id)] = merged
        (DATA_DIR / "user_settings.json").write_text(
            json.dumps(all_settings, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    @staticmethod
    def _load_user_settings_file() -> dict:
        path = DATA_DIR / "user_settings.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    # ==================== 会话管理 ====================

    async def save_session(self, session_id: str, data: dict, user_id: int = None):
        """保存或更新面试会话"""
        if not self.available:
            return await self._save_session_fallback(session_id, data)

        # 将 written_questions/written_total 嵌入 current_question JSON 字段（避免改表结构）
        cq = data.get("current_question", {})
        written_qs = data.get("written_questions", [])
        written_total = data.get("written_total", 0)
        if isinstance(cq, dict):
            extra = {}
            if written_qs:
                extra["__written_questions__"] = written_qs
            if written_total:
                extra["__written_total__"] = written_total
            if extra:
                cq = {**cq, **extra}

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO sessions (id, position, company, round, resume, profile, history, report,
                                         current_question, current_index, created_at, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    json.dumps(cq, ensure_ascii=False),
                    data.get("current_index", 0),
                    data.get("created_at", datetime.now().isoformat()),
                    user_id,
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

    async def list_sessions(self, user_id: int = None) -> list[dict]:
        """列出面试记录摘要（按 user_id 隔离）"""
        if not self.available:
            return await self._list_sessions_fallback()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute("""
                        SELECT id, position, company, round, created_at, history, report
                        FROM sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT 50
                    """, (user_id,))
                else:
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
                        "type": "mock" if (row[3] or "") == "mock" else "normal",
                        "position": row[1] or "未知",
                        "company": row[2] or "",
                        "round": row[3] or "",
                        "date": row[4].isoformat() if row[4] else "",
                        "total_questions": len(history),
                        "overall_score": report.get("overall_score", 0),
                        "coverage": report.get("coverage", {}),
                        "score_breakdown": report.get("score_breakdown", {}),
                        "weaknesses": report.get("weaknesses", []),
                        "preparation_advice": report.get("preparation_advice", []),
                    })
                return result

    async def delete_session(self, session_id: str, user_id: int = None) -> bool:
        """删除面试记录（校验 user_id 所有权）"""
        if not self.available:
            return await self._delete_session_fallback(session_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute("DELETE FROM sessions WHERE id=%s AND user_id=%s", (session_id, user_id))
                else:
                    await cur.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
                return cur.rowcount > 0

    def _row_to_session(self, row: tuple, columns: list) -> dict:
        """将数据库行转换为会话 dict"""
        data = dict(zip(columns, row))
        current_question = json.loads(data["current_question"]) if data.get("current_question") else {}
        written_questions = []
        written_total = 0
        if isinstance(current_question, dict):
            written_questions = current_question.pop("__written_questions__", [])
            written_total = current_question.pop("__written_total__", 0)
        return {
            "id": data["id"],
            "type": "mock" if (data.get("round") or "") == "mock" else "normal",
            "position": data.get("position", ""),
            "company": data.get("company", ""),
            "round": data.get("round", ""),
            "resume": data.get("resume", ""),
            "profile": json.loads(data["profile"]) if data.get("profile") else {},
            "history": json.loads(data["history"]) if data.get("history") else [],
            "report": json.loads(data["report"]) if data.get("report") else {},
            "current_question": current_question,
            "current_index": data.get("current_index", 0),
            "user_id": data.get("user_id"),
            "created_at": data["created_at"].isoformat() if data.get("created_at") else "",
            "written_questions": written_questions,
            "written_total": written_total,
        }

    # ==================== 题目收藏 ====================

    async def save_favorite(self, data: dict, user_id: int = None) -> int:
        """收藏题目，返回收藏 ID"""
        if not self.available:
            return await self._save_favorite_fallback(data)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO favorites (session_id, question, type, difficulty, topic, user_answer, overall_score, notes, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.get("session_id", ""),
                    data["question"],
                    data.get("type", ""),
                    data.get("difficulty", ""),
                    data.get("topic", ""),
                    data.get("user_answer", ""),
                    data.get("overall_score", 0),
                    data.get("reference_answer", "") or data.get("notes", ""),
                    user_id,
                ))
                return cur.lastrowid

    async def list_favorites(self, user_id: int = None, page: int = 1, page_size: int = 10, search: str = "") -> dict:
        """列出收藏题目（分页+搜索），返回 { items, pagination }"""
        if not self.available:
            items = await self._list_favorites_fallback()
            total = len(items)
            return {
                "items": items,
                "pagination": {"page": 1, "page_size": total, "total": total, "total_pages": 1},
            }

        offset = (page - 1) * page_size
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 构建 WHERE 条件（共享参数）
                where_parts = ["user_id=%s"]
                params = [user_id]

                if search:
                    kw = f"%{search}%"
                    where_parts.append("(question LIKE %s OR topic LIKE %s OR type LIKE %s)")
                    params.extend([kw, kw, kw])

                where_clause = " AND ".join(where_parts)

                # 总数查询
                await cur.execute(f"SELECT COUNT(*) FROM favorites WHERE {where_clause}", params)
                total = (await cur.fetchone())[0]

                # 数据查询
                await cur.execute(
                    f"SELECT id, session_id, question, type, difficulty, topic, "
                    f"user_answer, overall_score, notes, saved_at "
                    f"FROM favorites WHERE {where_clause} ORDER BY saved_at DESC LIMIT %s OFFSET %s",
                    params + [page_size, offset],
                )
                rows = await cur.fetchall()

                items = [
                    {
                        "id": r[0],
                        "session_id": r[1],
                        "question": r[2],
                        "type": r[3],
                        "difficulty": r[4],
                        "topic": r[5],
                        "user_answer": r[6] or "",
                        "overall_score": r[7],
                        "reference_answer": r[8] or "",
                        "saved_at": r[9].isoformat() if r[9] else "",
                    }
                    for r in rows
                ]

                total_pages = max(1, (total + page_size - 1) // page_size)

                return {
                    "items": items,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "total_pages": total_pages,
                    },
                }

    async def delete_favorite(self, fav_id: int, user_id: int = None) -> bool:
        """删除收藏题目（校验 user_id 所有权）"""
        if not self.available:
            return await self._delete_favorite_fallback(fav_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute("DELETE FROM favorites WHERE id=%s AND user_id=%s", (fav_id, user_id))
                else:
                    await cur.execute("DELETE FROM favorites WHERE id=%s", (fav_id,))
                return cur.rowcount > 0

    # ==================== 自定义题目 ====================

    async def create_custom_question(self, data: dict, user_id: int = None) -> int:
        """创建自定义题目，返回题目 ID"""
        if not self.available:
            return await self._create_custom_question_fallback(data)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO custom_questions (question, type, difficulty, topic, expected_points, tags, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    data["question"],
                    data.get("type", "技术"),
                    data.get("difficulty", "medium"),
                    data.get("topic", ""),
                    json.dumps(data.get("expected_points", []), ensure_ascii=False),
                    data.get("tags", ""),
                    user_id,
                ))
                return cur.lastrowid

    async def list_custom_questions(self, user_id: int = None) -> list[dict]:
        """列出所有自定义题目（按 user_id 隔离）"""
        if not self.available:
            return await self._list_custom_questions_fallback()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute(
                        "SELECT id, question, type, difficulty, topic, expected_points, tags, created_at, updated_at "
                        "FROM custom_questions WHERE user_id=%s ORDER BY updated_at DESC", (user_id,)
                    )
                else:
                    await cur.execute(
                        "SELECT id, question, type, difficulty, topic, expected_points, tags, created_at, updated_at "
                        "FROM custom_questions ORDER BY updated_at DESC"
                    )
                rows = await cur.fetchall()
                return [
                    {
                        "id": r[0],
                        "question": r[1],
                        "type": r[2],
                        "difficulty": r[3],
                        "topic": r[4] or "",
                        "expected_points": json.loads(r[5]) if r[5] else [],
                        "tags": r[6] or "",
                        "created_at": r[7].isoformat() if r[7] else "",
                        "updated_at": r[8].isoformat() if r[8] else "",
                    }
                    for r in rows
                ]

    async def get_custom_question(self, qid: int) -> Optional[dict]:
        """获取单个自定义题目"""
        if not self.available:
            return await self._get_custom_question_fallback(qid)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, question, type, difficulty, topic, expected_points, tags FROM custom_questions WHERE id=%s",
                    (qid,),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "question": row[1],
                    "type": row[2],
                    "difficulty": row[3],
                    "topic": row[4] or "",
                    "expected_points": json.loads(row[5]) if row[5] else [],
                    "tags": row[6] or "",
                }

    async def update_custom_question(self, qid: int, data: dict, user_id: int = None) -> bool:
        """更新自定义题目（校验 user_id 所有权）"""
        if not self.available:
            return await self._update_custom_question_fallback(qid, data)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    sql = """UPDATE custom_questions SET question=%s, type=%s, difficulty=%s, topic=%s,
                             expected_points=%s, tags=%s WHERE id=%s AND user_id=%s"""
                    params = (data["question"], data.get("type", "技术"), data.get("difficulty", "medium"),
                              data.get("topic", ""), json.dumps(data.get("expected_points", []), ensure_ascii=False),
                              data.get("tags", ""), qid, user_id)
                else:
                    sql = """UPDATE custom_questions SET question=%s, type=%s, difficulty=%s, topic=%s,
                             expected_points=%s, tags=%s WHERE id=%s"""
                    params = (data["question"], data.get("type", "技术"), data.get("difficulty", "medium"),
                              data.get("topic", ""), json.dumps(data.get("expected_points", []), ensure_ascii=False),
                              data.get("tags", ""), qid)
                await cur.execute(sql, params)
                return cur.rowcount > 0

    async def delete_custom_question(self, qid: int, user_id: int = None) -> bool:
        """删除自定义题目（校验 user_id 所有权）"""
        if not self.available:
            return await self._delete_custom_question_fallback(qid)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute("DELETE FROM custom_questions WHERE id=%s AND user_id=%s", (qid, user_id))
                else:
                    await cur.execute("DELETE FROM custom_questions WHERE id=%s", (qid,))
                return cur.rowcount > 0

    async def list_custom_question_ids(self, ids: list[int]) -> list[dict]:
        """根据 ID 列表批量获取自定义题目（保持传入顺序）"""
        if not ids:
            return []
        if not self.available:
            return await self._list_custom_question_ids_fallback(ids)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(ids))
                await cur.execute(
                    f"SELECT id, question, type, difficulty, topic, expected_points FROM custom_questions WHERE id IN ({placeholders})",
                    ids,
                )
                rows = await cur.fetchall()
                by_id = {}
                for r in rows:
                    by_id[r[0]] = {
                        "id": r[0],
                        "question": r[1],
                        "type": r[2],
                        "difficulty": r[3],
                        "topic": r[4] or "",
                        "expected_points": json.loads(r[5]) if r[5] else [],
                    }
                return [by_id[i] for i in ids if i in by_id]

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

    async def save_search_history(self, position: str, data: dict, user_id: int = None):
        """记录搜索历史"""
        if not self.available:
            return
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO search_history (position, summary, skill_count, topic_count, tech_stack, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    position,
                    data.get("summary", "")[:500],
                    len(data.get("required_skills", [])),
                    len(data.get("common_interview_topics", [])),
                    json.dumps(data.get("tech_stack", []), ensure_ascii=False),
                    user_id,
                ))

    async def get_search_history(self, limit: int = 20, user_id: int = None) -> list[dict]:
        """获取搜索历史（按 user_id 隔离）"""
        if not self.available:
            return []
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute(
                        "SELECT id, position, summary, skill_count, topic_count, created_at "
                        "FROM search_history WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
                        (user_id, limit),
                    )
                else:
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
    _favorites_file = DATA_DIR / "favorites.json"
    _custom_questions_file = DATA_DIR / "custom_questions.json"

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
                report = data.get("report", {})
                sessions.append({
                    "id": fp.stem,
                    "type": data.get("type", "normal"),
                    "position": data.get("position", "未知"),
                    "company": data.get("company", ""),
                    "round": data.get("round", ""),
                    "date": data.get("_updated_at", "")[:19],
                    "total_questions": len(data.get("history", [])) or report.get("total_questions", 0),
                    "overall_score": report.get("overall_score", 0),
                    "score_breakdown": report.get("score_breakdown", {}),
                    "weaknesses": report.get("weaknesses", []),
                    "preparation_advice": report.get("preparation_advice", []),
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

    # ==================== 收藏 JSON 回退 ====================

    async def _save_favorite_fallback(self, data: dict) -> int:
        try:
            items = []
            if self._favorites_file.exists():
                items = json.loads(self._favorites_file.read_text(encoding="utf-8"))
            new_id = max([i.get("id", 0) for i in items], default=0) + 1
            items.append({
                "id": new_id,
                "session_id": data.get("session_id", ""),
                "question": data["question"],
                "type": data.get("type", ""),
                "difficulty": data.get("difficulty", ""),
                "topic": data.get("topic", ""),
                "user_answer": data.get("user_answer", ""),
                "overall_score": data.get("overall_score", 0),
                "saved_at": datetime.now().isoformat(),
            })
            self._favorites_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            return new_id
        except Exception as e:
            logger.warning(f"收藏保存失败: {e}")
            return 0

    async def _list_favorites_fallback(self) -> list[dict]:
        try:
            if self._favorites_file.exists():
                items = json.loads(self._favorites_file.read_text(encoding="utf-8"))
                return sorted(items, key=lambda x: x.get("saved_at", ""), reverse=True)
            return []
        except Exception:
            return []

    async def _delete_favorite_fallback(self, fav_id: int) -> bool:
        try:
            if not self._favorites_file.exists():
                return False
            items = json.loads(self._favorites_file.read_text(encoding="utf-8"))
            new_items = [i for i in items if i.get("id") != fav_id]
            if len(new_items) == len(items):
                return False
            self._favorites_file.write_text(json.dumps(new_items, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    # ==================== 自定义题目 JSON 回退 ====================

    async def _create_custom_question_fallback(self, data: dict) -> int:
        try:
            items = []
            if self._custom_questions_file.exists():
                items = json.loads(self._custom_questions_file.read_text(encoding="utf-8"))
            new_id = max([i.get("id", 0) for i in items], default=0) + 1
            now = datetime.now().isoformat()
            items.append({
                "id": new_id,
                "question": data["question"],
                "type": data.get("type", "技术"),
                "difficulty": data.get("difficulty", "medium"),
                "topic": data.get("topic", ""),
                "expected_points": data.get("expected_points", []),
                "tags": data.get("tags", ""),
                "created_at": now,
                "updated_at": now,
            })
            self._custom_questions_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            return new_id
        except Exception as e:
            logger.warning(f"自定义题目创建失败: {e}")
            return 0

    async def _list_custom_questions_fallback(self) -> list[dict]:
        try:
            if self._custom_questions_file.exists():
                items = json.loads(self._custom_questions_file.read_text(encoding="utf-8"))
                return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)
            return []
        except Exception:
            return []

    async def _get_custom_question_fallback(self, qid: int) -> Optional[dict]:
        try:
            if not self._custom_questions_file.exists():
                return None
            items = json.loads(self._custom_questions_file.read_text(encoding="utf-8"))
            for item in items:
                if item.get("id") == qid:
                    return item
            return None
        except Exception:
            return None

    async def _update_custom_question_fallback(self, qid: int, data: dict) -> bool:
        try:
            if not self._custom_questions_file.exists():
                return False
            items = json.loads(self._custom_questions_file.read_text(encoding="utf-8"))
            for item in items:
                if item.get("id") == qid:
                    item.update({
                        "question": data["question"],
                        "type": data.get("type", "技术"),
                        "difficulty": data.get("difficulty", "medium"),
                        "topic": data.get("topic", ""),
                        "expected_points": data.get("expected_points", []),
                        "tags": data.get("tags", ""),
                        "updated_at": datetime.now().isoformat(),
                    })
                    self._custom_questions_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
                    return True
            return False
        except Exception:
            return False

    async def _delete_custom_question_fallback(self, qid: int) -> bool:
        try:
            if not self._custom_questions_file.exists():
                return False
            items = json.loads(self._custom_questions_file.read_text(encoding="utf-8"))
            new_items = [i for i in items if i.get("id") != qid]
            if len(new_items) == len(items):
                return False
            self._custom_questions_file.write_text(json.dumps(new_items, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    async def _list_custom_question_ids_fallback(self, ids: list[int]) -> list[dict]:
        try:
            if not self._custom_questions_file.exists():
                return []
            all_items = json.loads(self._custom_questions_file.read_text(encoding="utf-8"))
            by_id = {i["id"]: i for i in all_items}
            return [by_id[i] for i in ids if i in by_id]
        except Exception:
            return []


# 全局实例
db = Database()
