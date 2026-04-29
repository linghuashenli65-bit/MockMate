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

# 服务器
HOST = "127.0.0.1"
PORT = 18633

# MiMo API
MIMO_API_BASE = "https://api.mimo.xiaomi.com/v1"
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_MODEL_REASONING = "MiMo-v2.5-reasoning"
MIMO_MODEL_MULTIMODAL = "MiMo-v2.5-vision"
MIMO_MODEL_TTS = "MiMo-v2.5-tts"

# DeepSeek API
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_MODEL_REASONER = "deepseek-v4-flash"

# 默认 AI 提供商: "mimo" 或 "deepseek"
AI_PROVIDER = os.environ.get("AI_PROVIDER", "mimo")

# MySQL 数据库（可选）
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mockmate")
