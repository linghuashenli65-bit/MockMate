"""语音合成模块（异步）"""
import logging
from pathlib import Path
from typing import Optional

from .config import DATA_DIR
from .ai_client import AIClient

logger = logging.getLogger(__name__)


class TTSEngine:
    """语音合成引擎，将文字转为语音"""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client
        self._audio_dir = DATA_DIR / "audios"
        self._audio_dir.mkdir(exist_ok=True)

    async def synthesize(self, text: str, session_id: str, index: int) -> Optional[str]:
        """将文字合成语音并保存到文件，返回音频文件路径"""
        audio_data = await self.ai.text_to_speech(text)
        if audio_data is None:
            logger.warning("语音合成失败（API 未配置或不可用）")
            return None

        filename = f"{session_id}_q{index:03d}.mp3"
        filepath = self._audio_dir / filename
        filepath.write_bytes(audio_data)
        logger.info(f"语音已生成: {filename}")
        return str(filepath)

    def get_audio_url(self, session_id: str, index: int) -> Optional[str]:
        filename = f"{session_id}_q{index:03d}.mp3"
        filepath = self._audio_dir / filename
        if filepath.exists():
            return f"/api/audio/{filename}"
        return None
