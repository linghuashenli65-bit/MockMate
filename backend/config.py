"""MockMate 配置"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv, set_key

# 加载 .env 文件（如果存在）
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # 从旧的 config.json 迁移数据
    old_config = Path(__file__).parent / "data" / "config.json"
    if old_config.exists():
        try:
            data = json.loads(old_config.read_text(encoding="utf-8"))
            for k, v in data.items():
                env_key = k.upper()  # mimo_api_key → MIMO_API_KEY
                if v:
                    set_key(str(env_path), env_key, v)
            load_dotenv(env_path)
            old_config.unlink()  # 迁移后删除旧文件
            print(f"已从 {old_config.name} 迁移配置到 .env")
        except Exception as e:
            print(f"配置迁移失败: {e}")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "sessions").mkdir(exist_ok=True)
(DATA_DIR / "audios").mkdir(exist_ok=True)

# 服务器（支持通过环境变量覆盖）
HOST = os.environ.get("MOCKMATE_HOST", "0.0.0.0")
PORT = int(os.environ.get("MOCKMATE_PORT", "18633"))

# MiMo API（2025-12 更新：旧端点 api.mimo.xiaomi.com 已停用，模型名也已变更）
MIMO_API_BASE = "https://api.xiaomimimo.com/v1"
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_MODEL_REASONING = "mimo-v2-pro"
MIMO_MODEL_MULTIMODAL = "mimo-v2-omni"
MIMO_MODEL_TTS = "mimo-v2-tts"

# DeepSeek API
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_MODEL_REASONER = "deepseek-v4-flash"
DEEPSEEK_MODEL_CHAT = "deepseek-v4-flash"
DEEPSEEK_MODEL_WRITTEN_EVAL = "deepseek-chat"

# 默认 AI 提供商: "mimo" 或 "deepseek"
AI_PROVIDER = os.environ.get("AI_PROVIDER", "mimo")

# 是否允许未配置 API Key 的用户回退使用全局 Key（.env 中的配置）
# false = 每个用户必须自己提供 API Key，否则返回 401
# true = 兼容旧行为，未配 Key 的用户使用全局 Key（会记录警告日志）
ALLOW_SHARED_API_KEY = os.environ.get("ALLOW_SHARED_API_KEY", "false").lower() == "true"

# MySQL 数据库（可选）
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mockmate")

# JWT 认证
SECRET_KEY = os.environ.get("SECRET_KEY", "mockmate-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "72"))

# 邮箱验证码（SMTP）
# 兼容两种环境变量命名：SMTP_*（标准）或 EMAIL_*（用户习惯）
_email_user = os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER", "")
_email_pass = os.environ.get("SMTP_PASSWORD") or os.environ.get("EMAIL_KEY", "")
SMTP_USER = _email_user
SMTP_PASSWORD = _email_pass
# 自动根据邮箱域名推断 SMTP 服务器
if _email_user and "@qq.com" in _email_user:
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.qq.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
elif _email_user and "@163.com" in _email_user:
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.163.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
elif _email_user and "@gmail.com" in _email_user:
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
else:
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_FROM = os.environ.get("SMTP_FROM") or _email_user
