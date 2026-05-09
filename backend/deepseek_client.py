"""DeepSeek API 客户端（异步）"""
import logging
import time
from typing import Optional

import httpx

from .config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_MODEL_REASONER, DEEPSEEK_MODEL_CHAT, DEEPSEEK_MODEL_WRITTEN_EVAL

logger = logging.getLogger(__name__)


class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_API_BASE
        self._client = httpx.AsyncClient(
            timeout=120.0,
            base_url=self.base_url,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._owns_client = True
        self._last_latency_ms: float = 0
        self._last_usage: dict = {}

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    @property
    def last_usage(self) -> dict:
        return self._last_usage

    def with_key(self, api_key: str) -> 'DeepSeekClient':
        """返回使用不同 API Key 的实例（共享 HTTP 连接池）"""
        client = DeepSeekClient.__new__(DeepSeekClient)
        client.api_key = api_key
        client.base_url = self.base_url
        client._client = self._client
        client._owns_client = False
        return client

    @property
    def ready(self) -> bool:
        return bool(self.api_key) and self.api_key != "your-api-key-here"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(self, model: str, messages: list, **kwargs) -> Optional[str]:
        if not self.ready:
            return None
        self._last_latency_ms = 0
        self._last_usage = {}
        try:
            t0 = time.monotonic()
            resp = await self._client.post(
                "/chat/completions",
                headers=self._headers(),
                json={"model": model, "messages": messages, **kwargs},
            )
            self._last_latency_ms = round((time.monotonic() - t0) * 1000, 1)
            resp.raise_for_status()
            data = resp.json()
            self._last_usage = data.get("usage", {})
            content = data["choices"][0]["message"]["content"]
            if content is None:
                logger.warning(f"DeepSeek {model} 返回空内容")
            return content
        except Exception as e:
            logger.error(f"DeepSeek chat error ({model}): {e}")
            return None

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """调用推理模型，如果返回空则降级到标准模型"""
        result = await self.chat(DEEPSEEK_MODEL_REASONER, messages, **kwargs)
        if result is None and self.ready:
            logger.warning("reasoner 返回空，降级到 chat 模型")
            result = await self.chat(DEEPSEEK_MODEL, messages, **kwargs)
        return result

    async def chat_standard(self, messages: list, **kwargs) -> Optional[str]:
        """调用标准 chat 模型"""
        return await self.chat(DEEPSEEK_MODEL_CHAT, messages, **kwargs)

    async def written_eval(self, messages: list, **kwargs) -> Optional[str]:
        """调用笔试判卷专用模型（更快）"""
        return await self.chat(DEEPSEEK_MODEL_WRITTEN_EVAL, messages, **kwargs)

    async def extract_text_from_image(self, image_bytes: bytes) -> Optional[str]:
        """DeepSeek 不支持多模态"""
        logger.warning("DeepSeek 不支持图片识别，请使用 MiMo API")
        return None

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """DeepSeek 不支持 TTS"""
        logger.warning("DeepSeek 不支持语音合成，请使用 MiMo API")
        return None

    async def close(self):
        if self._owns_client:
            await self._client.aclose()
