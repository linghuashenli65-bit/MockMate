"""统一的 AI 客户端接口（异步）

支持 MiMo / DeepSeek / Qwen / Zhipu 四后端，自动路由和 fallback。
多用户模式下，API Key 从请求头获取，通过 with_keys() 创建临时客户端。
"""
import logging
from typing import Optional

from .config import AI_PROVIDER
from .mimoclient import MiMoClient
from .deepseek_client import DeepSeekClient
from .qwen_client import QwenClient
from .zhipu_client import ZhipuClient

logger = logging.getLogger(__name__)

# fallback 优先级（按配置顺序尝试）
_FALLBACK_ORDER = {
    "mimo":     ["deepseek", "qwen", "zhipu"],
    "deepseek": ["mimo", "qwen", "zhipu"],
    "qwen":     ["deepseek", "mimo", "zhipu"],
    "zhipu":    ["deepseek", "qwen", "mimo"],
}


class AIClient:
    """统一 AI 客户端，屏蔽 MiMo/DeepSeek/Qwen/Zhipu 差异"""

    def __init__(self):
        self.mimo = MiMoClient()
        self.deepseek = DeepSeekClient()
        self.qwen = QwenClient()
        self.zhipu = ZhipuClient()
        self._provider = AI_PROVIDER  # "mimo" | "deepseek" | "qwen" | "zhipu"
        self._last_used_client = self._primary()
        self._auto_switch_provider()

    @property
    def provider(self) -> str:
        return self._provider

    @provider.setter
    def provider(self, value: str):
        if value in ("mimo", "deepseek", "qwen", "zhipu"):
            self._provider = value
            logger.info(f"AI 提供商切换为: {value}")

    @property
    def ready(self) -> bool:
        """任意一个提供商就绪就算就绪"""
        return self.mimo.ready or self.deepseek.ready or self.qwen.ready or self.zhipu.ready

    def _primary(self):
        return {
            "mimo": self.mimo,
            "deepseek": self.deepseek,
            "qwen": self.qwen,
            "zhipu": self.zhipu,
        }.get(self._provider, self.mimo)

    def _get_fallback(self):
        """返回当前提供商的首个可用 fallback"""
        for name in _FALLBACK_ORDER.get(self._provider, []):
            client = getattr(self, name)
            if client.ready:
                return client
        return None

    def _auto_switch_provider(self):
        """如果当前提供商未配置但另一个已配置，自动切换"""
        primary = self._primary()
        if not primary.ready:
            for name, client in [("mimo", self.mimo), ("deepseek", self.deepseek), ("qwen", self.qwen), ("zhipu", self.zhipu)]:
                if client.ready:
                    self._provider = name
                    logger.info(f"自动切换到 {name}")
                    break

    @property
    def last_latency_ms(self) -> float:
        """最近一次实际调用的请求耗时（ms）"""
        return self._last_used_client.last_latency_ms

    @property
    def last_usage(self) -> dict:
        """最近一次实际调用的 token 用量"""
        return self._last_used_client.last_usage

    def with_keys(self, mimo_key: Optional[str] = None, deepseek_key: Optional[str] = None,
                  qwen_key: Optional[str] = None,
                  qwen_reasoner_model: Optional[str] = None,
                  qwen_chat_model: Optional[str] = None,
                  qwen_written_eval_model: Optional[str] = None,
                  qwen_tts_model: Optional[str] = None,
                  zhipu_key: Optional[str] = None,
                  zhipu_reasoner_model: Optional[str] = None,
                  zhipu_chat_model: Optional[str] = None,
                  zhipu_written_eval_model: Optional[str] = None,
                  zhipu_tts_model: Optional[str] = None,
                  provider: Optional[str] = None) -> 'AIClient':
        """创建使用指定 API Key 的临时客户端（共享 HTTP 连接池，无需关闭）"""
        client = AIClient.__new__(AIClient)
        client.mimo = self.mimo.with_key(mimo_key) if mimo_key else self.mimo
        client.deepseek = self.deepseek.with_key(deepseek_key) if deepseek_key else self.deepseek
        client.qwen = self.qwen.with_key(qwen_key,
                                          reasoner_model=qwen_reasoner_model,
                                          chat_model=qwen_chat_model,
                                          written_eval_model=qwen_written_eval_model,
                                          tts_model=qwen_tts_model)
        client.zhipu = self.zhipu.with_key(zhipu_key,
                                            reasoner_model=zhipu_reasoner_model,
                                            chat_model=zhipu_chat_model,
                                            written_eval_model=zhipu_written_eval_model,
                                            tts_model=zhipu_tts_model)
        client._provider = provider if provider in ("mimo", "deepseek", "qwen", "zhipu") else self._provider
        client._last_used_client = client._primary()
        return client

    async def _call_with_fallback(self, method: str, messages: list, **kwargs) -> Optional[str]:
        """通用调用模式：先主提供商，失败后 fallback"""
        client = self._primary()
        result = await getattr(client, method)(messages, **kwargs)
        if result is None:
            fb = self._get_fallback()
            if fb:
                logger.warning(f"{self._provider} 调用失败，fallback 到另一个提供商")
                result = await getattr(fb, method)(messages, **kwargs)
                self._last_used_client = fb
                return result
            return result
        self._last_used_client = client
        return result

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """推理/对话 - 首选当前提供商，失败时自动 fallback"""
        return await self._call_with_fallback("reason", messages, **kwargs)

    async def chat(self, messages: list, **kwargs) -> Optional[str]:
        """标准对话（非推理） - 首选当前提供商的标准模型，失败时自动 fallback"""
        return await self._call_with_fallback("chat_standard", messages, **kwargs)

    async def written_eval(self, messages: list, **kwargs) -> Optional[str]:
        """笔试判卷 - 使用更快模型，失败时自动 fallback"""
        return await self._call_with_fallback("written_eval", messages, **kwargs)

    async def extract_text_from_image(self, image_bytes: bytes) -> Optional[str]:
        """图片文字提取 - 优选 MiMo，其次 Qwen vl，再 Zhipu vision"""
        result = await self.mimo.extract_text_from_image(image_bytes)
        if result is None and self.qwen.ready:
            result = await self.qwen.extract_text_from_image(image_bytes)
        if result is None and self.zhipu.ready:
            result = await self.zhipu.extract_text_from_image(image_bytes)
        return result

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """语音合成 - 优选 MiMo，其次 Qwen CosyVoice，再 Zhipu GLM-TTS"""
        result = await self.mimo.text_to_speech(text)
        if result is None and self.qwen.ready:
            result = await self.qwen.text_to_speech(text)
        if result is None and self.zhipu.ready:
            result = await self.zhipu.text_to_speech(text)
        return result

    async def close(self):
        await self.mimo.close()
        await self.deepseek.close()
        await self.qwen.close()
        await self.zhipu.close()
