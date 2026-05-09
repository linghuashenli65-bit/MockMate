"""用户认证与邮箱验证码模块

基于 JWT 实现用户注册、登录、邮箱验证码。
API Key 由用户在浏览器端加密存储，不保存到数据库。
"""
import logging
import random
import string
import time
import warnings
from datetime import datetime, timedelta
from typing import Optional

import aiomysql
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from .config import SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_HOURS

logger = logging.getLogger(__name__)


# -------- JWT Bearer --------

security = HTTPBearer(auto_error=False)


# -------- 邮箱验证码存储（内存）--------
# 生产环境建议用 Redis，这里用内存简化实现

_code_store: dict[str, tuple[str, float]] = {}  # email -> (code, expire_time)


def generate_code(length: int = 6) -> str:
    """生成数字验证码"""
    return ''.join(random.choices(string.digits, k=length))


def save_code(email: str, code: str, ttl_seconds: int = 300):
    """保存验证码，默认 5 分钟有效"""
    _code_store[email] = (code, time.time() + ttl_seconds)


def verify_code(email: str, code: str) -> bool:
    """校验验证码"""
    entry = _code_store.get(email)
    if not entry:
        return False
    stored_code, expire_time = entry
    if time.time() > expire_time:
        del _code_store[email]
        return False
    if stored_code != code:
        return False
    # 验证成功后删除
    del _code_store[email]
    return True


# -------- JWT 工具 --------

def create_access_token(user_id: int, email: str) -> str:
    """创建 JWT Token"""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# -------- 用户数据库操作 --------

async def init_user_tables(pool: aiomysql.Pool):
    """初始化用户表"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    nickname VARCHAR(100) DEFAULT '',
                    is_verified TINYINT DEFAULT 0,
                    is_active TINYINT DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_email (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表'
            """)
            logger.info("用户表初始化完成")


async def create_user(pool: aiomysql.Pool, email: str, password: str, nickname: str = "") -> Optional[int]:
    """创建用户，返回用户 ID"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash(password)
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO users (email, hashed_password, nickname, is_verified) VALUES (%s, %s, %s, 1)",
                    (email, hashed, nickname or email.split('@')[0]),
                )
                return cur.lastrowid
    except aiomysql.IntegrityError:
        return None  # 邮箱已存在


async def authenticate_user(pool: aiomysql.Pool, email: str, password: str) -> Optional[dict]:
    """验证用户登录，返回用户信息"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, email, hashed_password, nickname, is_active FROM users WHERE email=%s",
                (email,),
            )
            user = await cur.fetchone()
            if not user:
                return None
            if not user['is_active']:
                return None
            if not pwd_context.verify(password, user['hashed_password']):
                return None
            return dict(user)


async def get_user_by_id(pool: aiomysql.Pool, user_id: int) -> Optional[dict]:
    """根据 ID 获取用户"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, email, nickname, is_active FROM users WHERE id=%s",
                (user_id,),
            )
            return await cur.fetchone()


async def email_exists(pool: aiomysql.Pool, email: str) -> bool:
    """检查邮箱是否已注册"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            return await cur.fetchone() is not None


# -------- FastAPI 依赖项 --------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """从 JWT Token 获取当前用户（FastAPI 依赖注入）"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录，请先登录",
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
        )
    user_id = int(payload.get("sub", 0))
    email = payload.get("email", "")
    return {"id": user_id, "email": email}
