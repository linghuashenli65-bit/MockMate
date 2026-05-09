"""MiMo API 客户端（异步）"""
import logging
import base64
import io
import time
from typing import Optional

import httpx
from PIL import Image

from .config import MIMO_API_BASE, MIMO_API_KEY, MIMO_MODEL_REASONING, MIMO_MODEL_MULTIMODAL, MIMO_MODEL_TTS

logger = logging.getLogger(__name__)


class MiMoClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or MIMO_API_KEY
        self.base_url = MIMO_API_BASE
        self._client = httpx.AsyncClient(
            timeout=120.0,
            base_url=self.base_url,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._owns_client = True
        # 最后一次 API 调用的耗时（ms）和 token 用量
        self._last_latency_ms: float = 0
        self._last_usage: dict = {}

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    @property
    def last_usage(self) -> dict:
        return self._last_usage

    def with_key(self, api_key: str) -> 'MiMoClient':
        """返回使用不同 API Key 的实例（共享 HTTP 连接池）"""
        client = MiMoClient.__new__(MiMoClient)
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
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"MiMo chat error: {e}")
            return None

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """调用推理模型"""
        return await self.chat(MIMO_MODEL_REASONING, messages, **kwargs)

    async def chat_standard(self, messages: list, **kwargs) -> Optional[str]:
        """标准对话（非推理），复用推理模型"""
        return await self.reason(messages, **kwargs)

    async def written_eval(self, messages: list, **kwargs) -> Optional[str]:
        """笔试判卷（MiMo 没有专用模型，复用推理模型作为 fallback）"""
        return await self.reason(messages, **kwargs)

    async def extract_text_from_image(self, image_bytes: bytes) -> Optional[str]:
        """多模态：从图片提取文字"""
        if not self.ready:
            return None
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                w, h = img.size
                if w > 2048 or h > 2048:
                    ratio = min(2048 / w, 2048 / h)
                    img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode()

            resp = await self._client.post(
                "/chat/completions",
                headers=self._headers(),
                json={
                    "model": MIMO_MODEL_MULTIMODAL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请完整提取这张图片中的所有文字内容，包括标题、正文、列表。保持原文格式。"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }],
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"MiMo image extraction error: {e}")
            return None

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """语音合成：文字转语音（MiMo TTS 使用 chat completions 接口）"""
        if not self.ready:
            return None
        try:
            resp = await self._client.post(
                "/chat/completions",
                headers=self._headers(),
                json={
                    "model": MIMO_MODEL_TTS,
                    "messages": [
                        {"role": "user", "content": "请用中文朗读以下内容"},
                        {"role": "assistant", "content": f"<style>自然</style>{text}"},
                    ],
                    "audio": {
                        "format": "wav",
                        "voice": "mimo_default",
                    },
                },
            )
            if resp.status_code == 404:
                logger.info("MiMo TTS 端点不可用（404），语音功能已降级")
                return None
            resp.raise_for_status()
            data = resp.json()
            audio_b64 = data.get("choices", [{}])[0].get("message", {}).get("audio", {}).get("data", "")
            if not audio_b64:
                logger.warning("MiMo TTS 响应中没有 audio.data 字段")
                return None
            return base64.b64decode(audio_b64)
        except httpx.HTTPStatusError as e:
            logger.warning(f"MiMo TTS 返回 HTTP {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"MiMo TTS 调用失败: {e}")
            return None

    async def close(self):
        if self._owns_client:
            await self._client.aclose()
