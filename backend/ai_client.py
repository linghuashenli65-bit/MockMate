"""统一的 AI 客户端接口（异步）

支持 MiMo 和 DeepSeek 双后端，自动路由和 fallback。
多用户模式下，API Key 从请求头获取，通过 with_keys() 创建临时客户端。
"""
import logging
from typing import Optional

from .config import AI_PROVIDER
from .mimoclient import MiMoClient
from .deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)


class AIClient:
    """统一 AI 客户端，屏蔽 MiMo/DeepSeek 差异"""

    def __init__(self):
        self.mimo = MiMoClient()
        self.deepseek = DeepSeekClient()
        self._provider = AI_PROVIDER  # "mimo" or "deepseek"
        self._last_used_client = self._primary()  # 最近实际调用的客户端
        self._auto_switch_provider()

    @property
    def provider(self) -> str:
        return self._provider

    @provider.setter
    def provider(self, value: str):
        if value in ("mimo", "deepseek"):
            self._provider = value
            logger.info(f"AI 提供商切换为: {value}")

    @property
    def ready(self) -> bool:
        """任意一个提供商就绪就算就绪"""
        return self.mimo.ready or self.deepseek.ready

    def _primary(self):
        return self.mimo if self._provider == "mimo" else self.deepseek

    def _auto_switch_provider(self):
        """如果当前提供商未配置但另一个已配置，自动切换"""
        primary = self._primary()
        if not primary.ready:
            if self._provider == "mimo" and self.deepseek.ready:
                self._provider = "deepseek"
                logger.info("自动切换到 DeepSeek（MiMo 未配置）")
            elif self._provider == "deepseek" and self.mimo.ready:
                self._provider = "mimo"
                logger.info("自动切换到 MiMo（DeepSeek 未配置）")

    @property
    def last_latency_ms(self) -> float:
        """最近一次实际调用的请求耗时（ms）"""
        return self._last_used_client.last_latency_ms

    @property
    def last_usage(self) -> dict:
        """最近一次实际调用的 token 用量"""
        return self._last_used_client.last_usage

    def with_keys(self, mimo_key: Optional[str] = None, deepseek_key: Optional[str] = None,
                  provider: Optional[str] = None) -> 'AIClient':
        """创建使用指定 API Key 的临时客户端（共享 HTTP 连接池，无需关闭）"""
        client = AIClient.__new__(AIClient)
        client.mimo = self.mimo.with_key(mimo_key) if mimo_key else self.mimo
        client.deepseek = self.deepseek.with_key(deepseek_key) if deepseek_key else self.deepseek
        client._provider = provider if provider in ("mimo", "deepseek") else self._provider
        client._last_used_client = client._primary()
        return client

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """推理/对话 - 首选当前提供商，失败时自动 fallback"""
        client = self._primary()
        result = await client.reason(messages, **kwargs)
        if result is None:
            fallback = self.deepseek if self._provider == "mimo" else self.mimo
            if fallback.ready:
                logger.warning(f"{self._provider} 调用失败，fallback 到另一个提供商")
                result = await fallback.reason(messages, **kwargs)
                self._last_used_client = fallback
            return result
        self._last_used_client = client
        return result

    async def chat(self, messages: list, **kwargs) -> Optional[str]:
        """标准对话（非推理） - 首选当前提供商的标准模型，失败时自动 fallback"""
        client = self._primary()
        result = await client.chat_standard(messages, **kwargs)
        if result is None:
            fallback = self.deepseek if self._provider == "mimo" else self.mimo
            if fallback.ready:
                logger.warning(f"{self._provider} 标准模型调用失败，fallback 到另一个提供商")
                result = await fallback.chat_standard(messages, **kwargs)
                self._last_used_client = fallback
            return result
        self._last_used_client = client
        return result

    async def written_eval(self, messages: list, **kwargs) -> Optional[str]:
        """笔试判卷 - 使用更快模型，失败时自动 fallback"""
        client = self._primary()
        result = await client.written_eval(messages, **kwargs)
        if result is None:
            fallback = self.deepseek if self._provider == "mimo" else self.mimo
            if fallback.ready:
                logger.warning(f"{self._provider} 笔试判卷调用失败，fallback 到另一个提供商")
                result = await fallback.written_eval(messages, **kwargs)
                self._last_used_client = fallback
            return result
        self._last_used_client = client
        return result

    async def extract_text_from_image(self, image_bytes: bytes) -> Optional[str]:
        """图片文字提取 - 仅 MiMo 支持"""
        result = await self.mimo.extract_text_from_image(image_bytes)
        if result is None and self.deepseek.ready:
            result = await self.deepseek.chat_standard([
                {"role": "user", "content": "这是一张简历图片（已编码），请输出一个占位文本说明。"}
            ])
        return result

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """语音合成 - 仅 MiMo 支持"""
        return await self.mimo.text_to_speech(text)

    async def close(self):
        await self.mimo.close()
        await self.deepseek.close()
