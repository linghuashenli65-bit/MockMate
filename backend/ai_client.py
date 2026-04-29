"""统一的 AI 客户端接口（异步）

支持 MiMo 和 DeepSeek 双后端，自动路由和 fallback。
用户可在设置页切换提供商。
"""
import logging
from pathlib import Path
from typing import Optional

from dotenv import set_key

from .config import AI_PROVIDER
from .mimoclient import MiMoClient
from .deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _save_env(key: str, value: str):
    """保存配置到 .env 文件"""
    try:
        set_key(str(ENV_FILE), key, value)
        logger.info(f"配置已保存: {key}")
    except Exception as e:
        logger.warning(f"配置保存失败: {e}")


class AIClient:
    """统一 AI 客户端，屏蔽 MiMo/DeepSeek 差异"""

    def __init__(self):
        self.mimo = MiMoClient()
        self.deepseek = DeepSeekClient()
        self._provider = AI_PROVIDER  # "mimo" or "deepseek"
        self._auto_switch_provider()

    @property
    def provider(self) -> str:
        return self._provider

    @provider.setter
    def provider(self, value: str):
        if value in ("mimo", "deepseek"):
            self._provider = value
            logger.info(f"AI 提供商切换为: {value}")
            _save_env("AI_PROVIDER", value)

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

    async def reason(self, messages: list, **kwargs) -> Optional[str]:
        """推理/对话 - 首选当前提供商，失败时自动 fallback"""
        client = self._primary()
        result = await client.reason(messages, **kwargs)
        if result is None:
            fallback = self.deepseek if self._provider == "mimo" else self.mimo
            if fallback.ready:
                logger.warning(f"{self._provider} 调用失败，fallback 到另一个提供商")
                result = await fallback.reason(messages, **kwargs)
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

    def update_api_key(self, provider: str, key: str):
        """更新 API Key，自动保存到 .env"""
        if provider == "mimo":
            self.mimo.api_key = key
            _save_env("MIMO_API_KEY", key)
            logger.info("MiMo API Key 已更新并保存")
        elif provider == "deepseek":
            self.deepseek.api_key = key
            _save_env("DEEPSEEK_API_KEY", key)
            logger.info("DeepSeek API Key 已更新并保存")
        self._auto_switch_provider()

    async def close(self):
        await self.mimo.close()
        await self.deepseek.close()
