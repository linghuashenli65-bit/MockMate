"""ASR 热词管理 — 提升中英文技术术语识别准确率。

使用 DashScope AsrPhraseManager 创建/管理技术面试场景热词短语，
生成的 phrase_id 传递给 Recognition.start(phrase_id=...) 以提升识别率。
"""
import logging
import time
from typing import Dict, Optional

import dashscope
from dashscope.audio.asr.asr_phrase_manager import AsrPhraseManager

from .config import QWEN_API_KEY

logger = logging.getLogger(__name__)

# 技术面试常见中英文术语（权重 1-100，越高越优先匹配）
# AsrPhraseManager 使用 1-100 的权重范围
TECH_PHRASES: Dict[str, int] = {
    # 后端 / 架构
    "Redis": 80,
    "MySQL": 80,
    "PostgreSQL": 80,
    "MongoDB": 80,
    "Elasticsearch": 80,
    "Kubernetes": 90,
    "Docker": 80,
    "Nginx": 70,
    "Kafka": 80,
    "RabbitMQ": 80,
    "GraphQL": 70,
    "REST": 60,
    "API": 60,
    "HTTP": 50,
    "TCP": 50,
    "WebSocket": 70,
    "JSON": 40,
    "SQL": 50,
    "NoSQL": 60,
    "gRPC": 70,
    # 编程语言 / 框架
    "Java": 60,
    "Python": 60,
    "Golang": 70,
    "JavaScript": 50,
    "TypeScript": 60,
    "React": 70,
    "Vue": 70,
    "Node.js": 70,
    "Spring": 70,
    "Spring Boot": 80,
    "MyBatis": 80,
    "Hibernate": 70,
    "Django": 70,
    "FastAPI": 70,
    # 云原生 / DevOps
    "CI/CD": 70,
    "DevOps": 70,
    "AWS": 60,
    "Linux": 50,
    "Git": 50,
    "Jenkins": 60,
    "Terraform": 70,
    # 数据结构 / 算法
    "HashMap": 70,
    "B+Tree": 80,
    "LRU": 70,
    "CAP": 70,
    "Raft": 70,
    "Paxos": 70,
    # 通用技术
    "微服务": 60,
    "高并发": 60,
    "分布式": 60,
    "容器化": 60,
    "负载均衡": 60,
    "读写分离": 60,
    "分库分表": 60,
    "缓存穿透": 70,
    "缓存雪崩": 70,
    "死锁": 60,
    "幂等": 60,
    "降级": 50,
    "熔断": 60,
    "限流": 60,
    "主从复制": 60,
    "哨兵模式": 70,
    "集群": 50,
}

# 缓存：避免每次连接都查 API
_cached_phrase_id: Optional[str] = None

# 短语编译最大等待时间（秒）
_MAX_COMPILE_WAIT_SECONDS = 60
# 轮询间隔（秒）
_POLL_INTERVAL_SECONDS = 3


def get_or_create_vocabulary_id(target_model: str = "fun-asr-realtime") -> Optional[str]:
    """获取或创建 MockMate 技术面试热词短语，返回 phrase_id。

    首次调用会创建热词短语并等待编译完成（最多 60 秒），后续使用缓存。
    如果 API Key 未配置则跳过。
    """
    global _cached_phrase_id
    if _cached_phrase_id:
        return _cached_phrase_id

    if not QWEN_API_KEY or QWEN_API_KEY == "your-api-key-here":
        logger.warning("ASR 热词: QWEN_API_KEY 未配置，跳过短语创建")
        return None

    try:
        dashscope.api_key = QWEN_API_KEY

        # 先查找已有短语（复用已编译成功的）
        page = 1
        while True:
            result = AsrPhraseManager.list_phrases(page=page, page_size=10)
            if result.status_code != 200:
                logger.warning("ASR 热词: 列举短语失败: %s", result.message)
                break
            items = result.output.get("phrase_list") or []
            if not items:
                break
            for item in items:
                pid = item.get("phrase_id", "")
                status = item.get("status", "")
                phrase_model = item.get("model", "")
                if phrase_model == target_model and status == "SUCCEEDED":
                    logger.info("ASR 热词: 复用已有短语 phrase_id=%s", pid)
                    _cached_phrase_id = pid
                    return pid
            page += 1

        # 不存在，创建新短语
        logger.info("ASR 热词: 未找到已有短语，创建新的 (共 %d 个术语)", len(TECH_PHRASES))
        response = AsrPhraseManager.create_phrases(
            model=target_model,
            phrases=TECH_PHRASES,
        )
        if response.status_code != 200:
            logger.error("ASR 热词: 创建短语失败: %s", response.message)
            return None

        phrase_id = response.output.get("job_id", "")
        if not phrase_id:
            logger.error("ASR 热词: 创建短语未返回 job_id")
            return None

        logger.info("ASR 热词: 短语编译任务已提交 phrase_id=%s，等待编译...", phrase_id)

        # 等待编译完成
        elapsed = 0
        while elapsed < _MAX_COMPILE_WAIT_SECONDS:
            time.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            status_resp = AsrPhraseManager.query_phrases(phrase_id)
            if status_resp.status_code != 200:
                logger.warning("ASR 热词: 查询短语状态失败: %s", status_resp.message)
                continue

            status = status_resp.output.get("status", "")
            if status == "SUCCEEDED":
                logger.info("ASR 热词: 短语编译成功 phrase_id=%s", phrase_id)
                _cached_phrase_id = phrase_id
                return phrase_id
            elif status in ("FAILED", "ERROR"):
                logger.error("ASR 热词: 短语编译失败 phrase_id=%s status=%s", phrase_id, status)
                return None

            logger.info("ASR 热词: 编译中 phrase_id=%s status=%s (已等待 %ds)",
                        phrase_id, status, elapsed)

        logger.warning("ASR 热词: 短语编译超时 (%ds)，跳过本次热词", _MAX_COMPILE_WAIT_SECONDS)
        return None

    except Exception as e:
        logger.error("ASR 热词: 创建/获取短语失败: %s", e)
        return None


def get_cached_vocabulary_id() -> Optional[str]:
    """返回缓存的短语 ID（需先调用 get_or_create_vocabulary_id）。"""
    return _cached_phrase_id
