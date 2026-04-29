"""MiMo API 客户端（异步）"""
import logging
import base64
import io
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
        try:
            resp = await self._client.post(
                "/chat/completions",
                headers=self._headers(),
                json={"model": model, "messages": messages, **kwargs},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"MiMo chat error: {e}")
            return None

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """调用推理模型"""
        return await self.chat(MIMO_MODEL_REASONING, messages, **kwargs)

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
        """语音合成：文字转语音"""
        if not self.ready:
            return None
        try:
            resp = await self._client.post(
                "/audio/speech",
                headers=self._headers(),
                json={
                    "model": MIMO_MODEL_TTS,
                    "input": text,
                    "response_format": "mp3",
                    "speed": 1.0,
                },
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error(f"MiMo TTS error: {e}")
            return None

    async def close(self):
        await self._client.aclose()
