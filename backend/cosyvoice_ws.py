"""DashScope CosyVoice TTS — 基于官方 SDK

提供两种模式：
1. CosyVoiceStreamClient.synthesize() — 一次性文本，流式返回音频（单次 streaming_call）
2. TTSStreamSession — 双向流式：逐 chunk 发送文本，流式返回音频（适用于 LLM 流式输出场景）
"""
import asyncio
import json
import logging
import queue as _queue
import threading
from pathlib import Path
from typing import AsyncGenerator, Optional

import requests as _requests
import dashscope as _dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback, AudioFormat

from .config import QWEN_MODEL_TTS, DATA_DIR

logger = logging.getLogger(__name__)

# v3.5-flash 无系统音色，需要先创建声音设计（Voice Design）
# _VOICE_CACHE 按 preset 名称缓存 voice_id，首次使用时创建
# 缓存持久化到磁盘，避免每次重启都重新创建（声音设计一旦创建永久有效）
_VOICE_CACHE: dict[str, str] = {}
_VOICE_LOCK = threading.Lock()
_VOICE_CACHE_PATH = DATA_DIR / "voice_cache.json"

_VOICE_PRESETS = {
    "稳重男声": "沉稳的中年男性，45岁左右，语速缓慢沉稳，音色低沉有磁性。参考标准播音风格：吐字清晰精准，字正腔圆，气息沉稳有力，适合朗读新闻或纪录片解说",
    "阳光男声": "温和自信的年轻男性，30岁左右，语调自然上扬，声音明亮清晰。参考标准播音风格：吐字清晰精准，字正腔圆，充满朝气和亲和力",
    "深沉男声": "沉稳厚重的中年男性，40岁左右，语速偏慢，音色低沉有磁性。参考标准播音风格：吐字清晰精准，字正腔圆，逻辑感强，每个字都经过斟酌",
    "干练男声": "干练果断的年轻男性，35岁左右，语速中等偏快，语调有力干脆，专业自信。参考标准播音风格：吐字清晰精准，字正腔圆，简洁有力不拖泥带水",
    "温柔女声": "温柔知性的女性，30岁左右，语调平和舒缓，音色温暖亲切，适合有声书朗读和情感交流",
    "知性女声": "知性冷静的女性，35岁左右，语调平稳清晰，语速中等，逻辑感强，适合技术讲解和专业讨论",
    "活泼女声": "年轻活泼的女性声音，20多岁，语速较快，带有明显的上扬语调，充满朝气和活力，适合介绍时尚产品和轻松话题",
    "默认":     "温和清晰的成年声音，语速中等，发音标准，沉稳专业。参考标准播音风格：吐字清晰精准，字正腔圆",
}


def _load_cache():
    """从磁盘加载 voice_id 缓存"""
    try:
        if _VOICE_CACHE_PATH.exists():
            data = json.loads(_VOICE_CACHE_PATH.read_text(encoding="utf-8"))
            _VOICE_CACHE.update(data)
            logger.info(f"已加载 {len(data)} 个音色缓存")
    except Exception as e:
        logger.warning(f"音色缓存加载失败: {e}")


def _save_cache():
    """将 voice_id 缓存持久化到磁盘"""
    try:
        _VOICE_CACHE_PATH.write_text(
            json.dumps(_VOICE_CACHE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"音色缓存保存失败: {e}")


# 模块加载时从磁盘恢复音色缓存
_load_cache()


def _create_voice(voice_prompt: str, prefix: str = "mockmate", api_key: Optional[str] = None) -> Optional[str]:
    """调用阿里云声音设计 API 创建一个音色，返回 voice_id"""
    try:
        api_key = api_key or _dashscope.api_key or getattr(_dashscope, '_api_key', None)
        if not api_key:
            logger.warning("CosyVoice 声音设计：无 API Key")
            return None

        payload = {
            "model": "voice-enrollment",
            "input": {
                "action": "create_voice",
                "target_model": QWEN_MODEL_TTS,
                "voice_prompt": voice_prompt,
                "preview_text": "你好，欢迎参加模拟面试，请准备好回答面试官的问题。",
                "prefix": prefix,
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = _requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
            headers=headers,
            json=payload,
            timeout=30,
        )
        data = resp.json()
        voice_id = data.get("output", {}).get("voice_id")
        if voice_id:
            logger.info(f"声音设计创建成功: {voice_id} ({prefix})")
            return voice_id
        else:
            logger.error(f"声音设计失败 [{prefix}]: {data.get('message', resp.text)}")
            return None
    except Exception as e:
        logger.error(f"声音设计异常 [{prefix}]: {e}")
        return None


def _ensure_voice(preset: str = "默认", api_key: Optional[str] = None) -> str:
    """获取指定预设音色的 voice_id，首次调用时自动创建

    创建失败的不会缓存，下次调用会重试。
    """
    # 已缓存的直接返回
    cached = _VOICE_CACHE.get(preset)
    if cached is not None:
        logger.debug(f"音色命中缓存: {preset}")
        return cached

    with _VOICE_LOCK:
        # double-check
        cached = _VOICE_CACHE.get(preset)
        if cached is not None:
            return cached

        prompt = _VOICE_PRESETS.get(preset, _VOICE_PRESETS["默认"])
        # prefix 只允许英文字母和数字且不超过 10 字符
        _PREFIX_MAP = {
            "稳重男声": "mmwz", "阳光男声": "mmyg",
            "深沉男声": "mmsc", "干练男声": "mmgl",
            "温柔女声": "mmwr", "知性女声": "mmzx",
            "活泼女声": "mmhp", "默认": "mmdef",
        }
        eng_prefix = _PREFIX_MAP.get(preset, "mm-voice")
        logger.info(f"音色未命中缓存，正在创建: {preset} ({eng_prefix})")
        voice_id = _create_voice(prompt, eng_prefix, api_key=api_key)
        if voice_id:
            _VOICE_CACHE[preset] = voice_id
            _save_cache()  # 持久化，避免重启后重复创建
            return voice_id
        return ""


def warmup_all_voices(api_key: str) -> dict[str, str]:
    """同步预热所有预设音色，返回 {preset: voice_id} 映射

    阻塞直到全部创建完成，用于服务启动时确保所有音色就绪。
    已缓存的音色直接返回，只创建尚未缓存的。
    """
    before = len(_VOICE_CACHE)
    for preset in _VOICE_PRESETS:
        _ensure_voice(preset, api_key=api_key)
    after = len(_VOICE_CACHE)
    new_created = after - before
    logger.info(
        f"音色预热完成: 缓存 {after}/{len(_VOICE_PRESETS)} 个预设"
        + (f"，新创建 {new_created} 个" if new_created else "")
    )
    return dict(_VOICE_CACHE)


class _StreamCallback(ResultCallback):
    """桥接 SDK 同步回调到 async generator

    SDK 的 streaming_call 在后台线程运行，on_data 在该线程中被调用。
    通过 call_soon_threadsafe 将数据投递到事件循环的队列中。
    """

    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.queue = asyncio.Queue()

    def on_data(self, data: bytes):
        """收到音频二进制 chunk（在 SDK 工作线程中调用）"""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, data)

    def on_complete(self):
        """合成完成，所有音频数据已接收"""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, None)

    def on_error(self, message: str):
        """发生错误"""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, Exception(message))

    def on_close(self):
        """连接关闭（仅日志，不触发队列信号以避免和 on_complete/on_error 竞争）"""
        pass


class CosyVoiceStreamClient:
    """CosyVoice TTS — 基于 DashScope SDK"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: float = 1.1,
        instruction: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """流式合成语音，逐 chunk 产出 MP3 音频二进制数据

        Args:
            text: 要合成的文本
            voice: 预设音色名称或自定义指令描述
            rate: 语速倍率，0.5~2.0
            instruction: 音色指令描述，优先级高于 voice

        Yields:
            bytes: MP3 音频二进制 chunk
        """
        # 确定 instruction 和 voice_id
        if instruction:
            instr = instruction
        elif voice and voice in _VOICE_PRESETS:
            instr = _VOICE_PRESETS[voice]
        else:
            instr = voice or _VOICE_PRESETS["默认"]

        # 确定语音 ID：preset 名称 → 对应 voice_id，否则用默认
        voice_preset = voice if (voice and voice in _VOICE_PRESETS) else "默认"
        voice_id = _ensure_voice(voice_preset, api_key=self.api_key)
        if not voice_id:
            raise ConnectionError(f"音色 '{voice_preset}' 创建失败，无法使用 TTS")

        callback = _StreamCallback()

        def run():
            """在后台线程中运行 SDK（同步阻塞）"""
            old_key = _dashscope.api_key
            _dashscope.api_key = self.api_key
            try:
                synthesizer = SpeechSynthesizer(
                    model=QWEN_MODEL_TTS,
                    voice=voice_id,
                    instruction=instr,
                    speech_rate=rate,
                    format=AudioFormat.MP3_48000HZ_MONO_256KBPS,
                    callback=callback,
                )
                synthesizer.streaming_call(text)
                synthesizer.streaming_complete()
            except Exception as e:
                logger.error(f"CosyVoice SDK error: {e}")
                callback.loop.call_soon_threadsafe(
                    callback.queue.put_nowait, Exception(str(e))
                )
            finally:
                _dashscope.api_key = old_key

        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, run)

        while True:
            item = await callback.queue.get()
            if item is None:
                break  # complete 或 close
            if isinstance(item, Exception):
                raise ConnectionError(f"CosyVoice TTS 失败: {item}") from item
            yield item

        # 等待后台线程结束（确保资源释放）
        await task


class _BidirectionalCallback(ResultCallback):
    """桥接 SDK 同步回调到外部 async 队列（用于双向流式 TTS）

    与 _StreamCallback 类似，但接收外部传入的 loop 和 audio_queue，
    由 TTSStreamSession 统一管理。
    """

    def __init__(self, loop, audio_queue):
        self.loop = loop
        self.audio_queue = audio_queue

    def on_data(self, data: bytes):
        """收到音频二进制 chunk（在 SDK 工作线程中调用）"""
        self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, data)

    def on_complete(self):
        """合成完成"""
        self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)

    def on_error(self, message: str):
        """发生错误"""
        self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, Exception(message))

    def on_close(self):
        pass


class TTSStreamSession:
    """双向流式 TTS 会话

    async 侧通过 send_text() 逐 chunk 发送文本，
    后台线程将文本送入 SDK 进行流式合成，
    async 侧通过 audio_chunks() 异步生成器接收音频 chunks。

    典型用法（无需额外 import，通过 AIClient / TTSEngine 创建）：
        session = TTSStreamSession(api_key, model, instruction, ...)
        # 启动音频消费
        async for chunk in session.audio_chunks():
            ...
        # 在另一侧发送文本
        session.send_text("Hello ")
        session.send_text("world")
        session.complete()
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        instruction: str,
        rate: float = 1.1,
        voice_preset: str = "默认",
        audio_format=AudioFormat.MP3_48000HZ_MONO_256KBPS,
    ):
        self.api_key = api_key
        self.model = model
        self.instruction = instruction
        self.rate = rate
        self.voice_preset = voice_preset
        self.voice_id = _ensure_voice(voice_preset, api_key=self.api_key)
        if not self.voice_id:
            raise ValueError(f"音色 '{voice_preset}' 创建失败，TTS 不可用")
        self.audio_format = audio_format

        # 通信通道
        self._text_queue: _queue.Queue = _queue.Queue()  # async → SDK 线程

    def send_text(self, text: str):
        """async 侧调用，将文本 chunk 放入 _text_queue"""
        self._text_queue.put(text)

    def complete(self):
        """async 侧调用，放入 None 哨兵以结束流式合成"""
        self._text_queue.put(None)

    async def audio_chunks(self):
        """async 生成器，启动后台线程，从 _audio_queue 产出音频 bytes

        注意：每个 TTSStreamSession 实例只能调用一次 audio_chunks()。
        """
        audio_queue: asyncio.Queue = asyncio.Queue()
        callback = _BidirectionalCallback(asyncio.get_event_loop(), audio_queue)

        def run():
            """在后台线程中运行 SDK（同步阻塞）"""
            old_key = _dashscope.api_key
            _dashscope.api_key = self.api_key
            try:
                synthesizer = SpeechSynthesizer(
                    model=self.model,
                    voice=self.voice_id,
                    instruction=self.instruction,
                    speech_rate=self.rate,
                    format=self.audio_format,
                    callback=callback,
                )
                while True:
                    chunk = self._text_queue.get()  # 阻塞等待文本 chunk
                    if chunk is None:
                        break
                    synthesizer.streaming_call(chunk)
                synthesizer.streaming_complete()
            except Exception as e:
                logger.error(f"TTSStreamSession SDK error: {e}")
                callback.loop.call_soon_threadsafe(
                    callback.audio_queue.put_nowait, Exception(str(e))
                )
            finally:
                _dashscope.api_key = old_key

        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, run)

        while True:
            item = await audio_queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise ConnectionError(f"双向流式 TTS 失败: {item}") from item
            yield item

        await task
