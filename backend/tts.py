"""语音合成模块（异步）"""
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from .config import DATA_DIR
from .ai_client import AIClient

logger = logging.getLogger(__name__)


class TTSStreamSessionWrapper:
    """TTSEngine 内部使用的双向流式 TTS 会话包装

    封装 TTSStreamSession（cosyvoice_ws），添加：
    - 文件保存逻辑（收集 chunks → 写文件 → 生成 URL）
    - 统一的 (stage, data) 产出协议（与 synthesize_stream 兼容）
    """

    def __init__(self, session_id: str, index: int, cosy_session, audio_dir: Path):
        self.session_id = session_id
        self.index = index
        self.cosy_session = cosy_session
        self.audio_dir = audio_dir
        self.chunks: list[bytes] = []
        self.audio_url: Optional[str] = None

    def send_text(self, text: str):
        """发送文本 chunk 到 TTS 会话"""
        self.cosy_session.send_text(text)

    def complete(self):
        """通知 TTS 会话所有文本已发送完毕"""
        self.cosy_session.complete()

    async def audio_chunks(self):
        """async 生成器，从 TTS 会话产出音频 chunks 并保存

        Yields:
            ("chunk", bytes) — 音频二进制数据
            ("done", str | None) — 完成，附带音频 URL，失败为 None
        """
        try:
            async for data in self.cosy_session.audio_chunks():
                self.chunks.append(data)
                yield ("chunk", data)
        except Exception as e:
            logger.error(f"双向流式 TTS 音频流错误: {e}")
            yield ("done", None)
            return

        # 保存完整音频文件
        if self.chunks:
            filename = f"{self.session_id}_q{self.index:03d}.wav"
            filepath = self.audio_dir / filename
            full_audio = b''.join(self.chunks)
            filepath.write_bytes(full_audio)
            self.audio_url = f"/api/audio/{filename}"
            logger.info(f"双向流式语音已保存: {filename} ({len(full_audio)} bytes)")
            yield ("done", self.audio_url)
        else:
            logger.warning("双向流式 TTS 未产出任何音频数据")
            yield ("done", None)


class TTSEngine:
    """语音合成引擎，将文字转为语音"""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client
        self._audio_dir = DATA_DIR / "audios"
        self._audio_dir.mkdir(exist_ok=True)

    async def synthesize(self, text: str, session_id: str, index: int, voice: Optional[str] = None) -> Optional[str]:
        """将文字合成语音并保存到文件，返回音频文件路径
        voice: 音色名称，传入面试官的 voice_style
        """
        audio_data = await self.ai.text_to_speech(text, voice=voice)
        if audio_data is None:
            logger.warning("语音合成失败（API 未配置或不可用）")
            return None

        filename = f"{session_id}_q{index:03d}.wav"
        filepath = self._audio_dir / filename
        filepath.write_bytes(audio_data)
        logger.info(f"语音已生成: {filename}")
        return str(filepath)

    async def synthesize_stream(self, text: str, session_id: str, index: int, voice: Optional[str] = None, rate: float = 1.1):
        """流式语音合成，逐 chunk 产出，完成后保存完整文件

        Args:
            text: 要合成的文本
            session_id: 会话 ID
            index: 问题序号
            voice: 音色名称
            rate: 语速倍率，0.5~2.0，默认 1.1

        Yields:
            ("chunk", bytes) — 音频二进制数据
            ("done", str | None) — 完成，附带音频 URL，失败为 None
        """
        chunks = []
        try:
            async for audio_chunk in self.ai.text_to_speech_stream(text, voice=voice, rate=rate):
                chunks.append(audio_chunk)
                yield ("chunk", audio_chunk)
        except Exception as e:
            logger.error(f"流式语音合成失败: {e}")

        if chunks:
            filename = f"{session_id}_q{index:03d}.wav"
            filepath = self._audio_dir / filename
            full_audio = b''.join(chunks)
            filepath.write_bytes(full_audio)
            url = f"/api/audio/{filename}"
            logger.info(f"流式语音已保存: {filename} ({len(full_audio)} bytes)")
            yield ("done", url)
        else:
            logger.warning("流式语音合成未产出任何音频数据")
            yield ("done", None)

    async def create_stream_session(
        self,
        session_id: str,
        index: int,
        voice: Optional[str] = None,
        rate: float = 1.1,
    ) -> Optional[TTSStreamSessionWrapper]:
        """创建双向流式 TTS 会话

        适用于 LLM 流式输出场景：逐 chunk 发送文本到 TTS，音频 chunks 实时返回。
        如果 TTS 不可用，返回 None（调用方降级为仅文本输出）。

        Args:
            session_id: 会话 ID
            index: 问题序号
            voice: 音色名称或自定义指令描述
            rate: 语速倍率，0.5~2.0

        Returns:
            TTSStreamSessionWrapper 或 None
        """
        # 解析 voice → instruction 和 voice_preset
        from .cosyvoice_ws import _VOICE_PRESETS
        if voice and voice in _VOICE_PRESETS:
            instr = _VOICE_PRESETS[voice]
            voice_preset = voice
        else:
            instr = voice or _VOICE_PRESETS["默认"]
            voice_preset = "默认"

        cosy_session = await self.ai.create_tts_stream_session(
            instr, rate, voice_preset=voice_preset,
        )
        if not cosy_session:
            return None
        return TTSStreamSessionWrapper(session_id, index, cosy_session, self._audio_dir)

    def get_audio_url(self, session_id: str, index: int) -> Optional[str]:
        filename = f"{session_id}_q{index:03d}.wav"
        filepath = self._audio_dir / filename
        if filepath.exists():
            return f"/api/audio/{filename}"
        return None
