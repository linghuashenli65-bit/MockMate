"""通义千问 (Qwen) API 客户端（异步）

OpenAI 兼容接口，支持推理/对话/判卷/图片识别/语音合成。
"""
import logging
import time
from typing import Optional

import httpx

from .config import QWEN_API_BASE, QWEN_API_KEY, QWEN_MODEL, QWEN_MODEL_REASONER, QWEN_MODEL_CHAT, QWEN_MODEL_WRITTEN_EVAL, QWEN_MODEL_TTS

logger = logging.getLogger(__name__)


class QwenClient:
    def __init__(self, api_key: Optional[str] = None,
                 reasoner_model: Optional[str] = None,
                 chat_model: Optional[str] = None,
                 written_eval_model: Optional[str] = None,
                 tts_model: Optional[str] = None):
        self.api_key = api_key or QWEN_API_KEY
        self.base_url = QWEN_API_BASE
        self._client = httpx.AsyncClient(
            timeout=120.0,
            base_url=self.base_url,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._owns_client = True
        self._last_latency_ms: float = 0
        self._last_usage: dict = {}
        self.reasoner_model = reasoner_model or QWEN_MODEL_REASONER
        self.chat_model = chat_model or QWEN_MODEL_CHAT
        self.written_eval_model = written_eval_model or QWEN_MODEL_WRITTEN_EVAL
        self.tts_model = tts_model or QWEN_MODEL_TTS

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    @property
    def last_usage(self) -> dict:
        return self._last_usage

    def with_key(self, api_key: Optional[str] = None,
                 reasoner_model: Optional[str] = None,
                 chat_model: Optional[str] = None,
                 written_eval_model: Optional[str] = None,
                 tts_model: Optional[str] = None) -> 'QwenClient':
        """返回使用不同 API Key / 模型的实例（共享 HTTP 连接池）"""
        client = QwenClient.__new__(QwenClient)
        client.api_key = api_key if api_key is not None else self.api_key
        client.base_url = self.base_url
        client._client = self._client
        client._owns_client = False
        client.reasoner_model = reasoner_model if reasoner_model is not None else self.reasoner_model
        client.chat_model = chat_model if chat_model is not None else self.chat_model
        client.written_eval_model = written_eval_model if written_eval_model is not None else self.written_eval_model
        client.tts_model = tts_model if tts_model is not None else self.tts_model
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
                logger.warning(f"Qwen {model} 返回空内容")
            return content
        except Exception as e:
            logger.error(f"Qwen chat error ({model}): {e}")
            return None

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """调用推理模型，如果返回空则降级到标准模型"""
        result = await self.chat(self.reasoner_model, messages, **kwargs)
        if result is None and self.ready:
            logger.warning("reasoner 返回空，降级到 chat 模型")
            result = await self.chat(self.chat_model, messages, **kwargs)
        return result

    async def chat_standard(self, messages: list, **kwargs) -> Optional[str]:
        """调用标准 chat 模型"""
        return await self.chat(self.chat_model, messages, **kwargs)

    async def written_eval(self, messages: list, **kwargs) -> Optional[str]:
        """调用笔试判卷专用模型（更快）"""
        return await self.chat(self.written_eval_model, messages, **kwargs)

    async def extract_text_from_image(self, image_bytes: bytes) -> Optional[str]:
        """Qwen 支持多模态图片识别（vl 模型）"""
        if not self.ready:
            return None
        import base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请提取这张图片中的文字内容"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        ]
        try:
            resp = await self._client.post(
                "/chat/completions",
                headers=self._headers(),
                json={"model": "qwen-vl-plus", "messages": messages, "max_tokens": 2048},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Qwen 图片识别失败: {e}")
            return None

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """调用语音合成（使用 self.tts_model，可通过请求头覆盖）"""
        if not self.ready:
            return None
        try:
            resp = await self._client.post(
                "/v1/audio/speech",
                headers=self._headers(),
                json={
                    "model": self.tts_model,
                    "input": text,
                    "voice": "longxiaochun",
                    "response_format": "wav",
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error(f"Qwen TTS 失败 (model={self.tts_model}): {e}")
            return None

    async def close(self):
        if self._owns_client:
            await self._client.aclose()
