# 双向流式 TTS 改造计划

## 目标

将当前问答生成流程从「LLM 出完完整文本 → TTS 开始合成」改为「LLM 每出一个 token 立即送入 TTS，音频 chunks 和文本 tokens 并行到达前端」，降低首音延迟。

## 当前流程（改造前）

```
LLM stream_reason → 收集完整文本 → TTS streaming_call(完整文本) → audio chunks
```

## 目标流程（改造后）

```
LLM stream_reason → token1 → TTS.streaming_call(token1) → audio chunk → 前端
                 → token2 → TTS.streaming_call(token2) → audio chunk → 前端
                 → ...  → TTS.streaming_complete()
```

## 改动文件及内容

### 文件1: `backend/cosyvoice_ws.py` — 新增 TTSStreamSession 类

**新增类 `_BidirectionalCallback(ResultCallback)`**：
- 与 `_StreamCallback` 类似，但接收外部传入的 `loop` 和 `audio_queue`（不自己创建）

**新增类 `TTSStreamSession`**：
- 属性：api_key, model, instruction, rate, audio_format
- 通信通道：
  - `_text_queue: queue.Queue` — 线程安全队列，async 侧 → SDK 线程
  - `_audio_queue: asyncio.Queue` — async 侧 ← SDK 线程
- 方法：
  - `send_text(text: str)` — async 侧调用，将文本 chunk 放入 `_text_queue`
  - `complete()` — async 侧调用，放入 None 哨兵
  - `audio_chunks()` — async generator，启动后台线程，从 `_audio_queue` 产出音频 chunks
  - `_run()` — 在后台线程中运行的同步方法：
    1. 保存/恢复 `_dashscope.api_key`
    2. 创建 `SpeechSynthesizer`（传入 instruction, rate, format, callback）
    3. 循环：`_text_queue.get()` 阻塞等待文本 chunks
    4. 每收到一个 chunk 调用 `synthesizer.streaming_call(chunk)`
    5. 收到 None 后 break，调用 `synthesizer.streaming_complete()`

**改动范围**：仅新增，不修改现有 `CosyVoiceStreamClient` 类（向后兼容）

### 文件2: `backend/ai_client.py` — 新增 create_tts_stream_session 方法

在 `AIClient` 类中新增：
```python
async def create_tts_stream_session(self, instruction: str, rate: float = 1.1):
    """创建双向流式 TTS 会话（返回 TTSStreamSession 或 None）"""
    if self.qwen.ready:
        from .cosyvoice_ws import TTSStreamSession
        return TTSStreamSession(
            api_key=self.qwen.api_key,
            model=QWEN_MODEL_TTS,
            instruction=instruction,
            rate=rate,
            audio_format=AudioFormat.MP3_48000Hz_Mono_256kb,
        )
    return None  # 不支持双向流式时返回 None，调用方降级
```

注意：需要在文件头部增加 `from .config import QWEN_MODEL_TTS` 和 `from dashscope.audio.tts_v2 import AudioFormat` 的导入。

**原因**：`create_tts_stream_session` 需要知道 TTS 模型和格式配置，这些在 config 和 dashscope SDK 中。

### 文件3: `backend/tts.py` — 新增 create_stream_session 方法和 TTSStreamSessionWrapper 类

**新增类 `TTSStreamSessionWrapper`**（TTSEngine 内部使用）：
- 属性：session_id, index, cosy_session（真正的 TTSStreamSession）, audio_dir, chunks[], audio_url
- 方法：
  - `send_text(text: str)` — 委托给 cosy_session.send_text
  - `complete()` — 委托给 cosy_session.complete
  - `audio_chunks()` — async generator：
    1. 遍历 `cosy_session.audio_chunks()`
    2. 收集 chunks 到 self.chunks
    3. yield ("chunk", data)
    4. 完成后保存文件，yield ("done", url)

**在 `TTSEngine` 中新增**：
```python
async def create_stream_session(self, session_id: str, index: int,
                                 voice: Optional[str] = None,
                                 rate: float = 1.1) -> Optional[TTSStreamSessionWrapper]:
    """创建双向流式 TTS 会话"""
    # 解析 voice → instruction
    from .cosyvoice_ws import _VOICE_PRESETS
    if voice and voice in _VOICE_PRESETS:
        instr = _VOICE_PRESETS[voice]
    else:
        instr = voice or _VOICE_PRESETS["默认"]

    cosy_session = await self.ai.create_tts_stream_session(instr, rate)
    if not cosy_session:
        return None
    return TTSStreamSessionWrapper(session_id, index, cosy_session, self._audio_dir)
```

### 文件4: `backend/mock_interview/mock_engine.py` — 改造 `_generate_question_stream`

**改动方法 `_generate_question_stream`**：

当前：
1. 收集 LLM tokens → yield ("token", token)
2. 完整文本生成后 → TTS synthesizer_stream(完整文本) → yield ("audio_chunk", data)
3. yield ("done", result)

改为：
1. 创建 TTS session（通过 `self.tts.create_stream_session(...)`）
2. 同时启动两个 async task（通过 asyncio.create_task）：
   - `pump_text`: 遍历 LLM stream_reason，每收到 token:
     - yield ("token", token)  
     - 如果有 TTS session，调用 `tts_session.send_text(token)`
     - 完成后调用 `tts_session.complete()`，`queue.put(("text_done", collected))`
   - `pump_audio`: 遍历 `tts_session.audio_chunks()`:
     - yield ("chunk", data) → `queue.put(("audio_chunk", data))`
     - yield ("done", url) → `queue.put(("audio_done", url))`
3. 主循环：从 queue 中读取事件并 yield
4. 等到 text_done 和 audio_done 都收到后，yield ("done", result)

**并发控制**：使用 `asyncio.Queue` 做事件多路复用

**错误处理**：
- LLM 流式失败时的 fallback 逻辑保留
- TTS session 创建失败时（返回 None），降级为仅输出文本 tokens，无音频（不阻塞主流程）
- 如果 TTS 中途失败，pump_audio 会收到 Exception（通过 call_soon_threadsafe 投递），需要在主循环中处理

## 不变的文件

- `backend/mock_interview/api_router.py` — `handle_answer_stream` 无需变化，它使用 `_generate_question_stream` 返回的同一套 stage 协议
- `backend/main.py` — WebSocket 事件分派无需变化
- `frontend/js/mock_interview.js` — 前端已处理 `question_token` + `audio_chunk` + `audio_done` 事件序列

## 协议一致

改造后 `_generate_question_stream` 产出的 stage 顺序从：
```
token → token → ... → audio_chunk → audio_chunk → ... → audio_done → done
```
变为：
```
token → audio_chunk → token → audio_chunk → ... → audio_done → done
```
即 tokens 和 audio_chunks 交织到达，前端已经能正确处理这种交织（`handleWsMessage` 中 `question_token` 和 `audio_chunk` 是独立 case）。唯一注意：前端 `_streamingText` 是累积拼接的，交织的 audio_chunk 不会影响它。

## 降级路径

如果用户没有配置 Qwen API Key（`self.qwen.ready == False`），`create_tts_stream_session` 返回 None，`_generate_question_stream` 降级为仅输出文本 tokens 无音频——前端仍能正常显示问题文本。
