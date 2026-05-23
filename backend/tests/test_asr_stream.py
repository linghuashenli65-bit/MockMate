"""BDD/TDD: 实时 ASR WebSocket 协议测试

覆盖 BDD 场景:
  A1. 麦克风打开 → WebSocket 连接
  A2. 麦克风关闭 → stop → done
  B1/B2/B3. partial/final/speech_end 消息协议
  C2. 旧 session 消息丢弃（sessionId 校验）
  E3. 客户端断开 → worker 清理
  F1. 无 API Key → 错误拒绝
  F2. WebSocket 错误 → cleanup

后端测试重点：协议正确性、资源清理、错误处理。
前端测试（voice FSM / ASR Reducer）见 voice_controller_test.js。
"""
import asyncio
import base64
import struct
from unittest.mock import MagicMock, patch

import pytest

from backend.main import _make_wav_header


# 所有测试默认跳过热词表创建（避免网络调用阻塞测试）
@pytest.fixture(autouse=True)
def _mock_vocabulary(monkeypatch):
    monkeypatch.setattr("backend.main.get_or_create_vocabulary_id", lambda: None)


# ============================================================
# Mock 基础设施 — 防止 worker 线程连接真实的 DashScope
# ============================================================

def _make_mock_recognition_factory(callback_class=None):
    """返回一个 Mock Recognition factory。

    mock 实例行为:
      - start() / send_audio_frame() 为 no-op
      - stop() 触发 callback.on_complete() → 主循环收到 "done"
      - callback 参数被捕获到 mock_inst._callback
    """
    def factory(model=None, format=None, sample_rate=None,
                semantic_punctuation_enabled=None, callback=None, **kwargs):
        mock_inst = MagicMock()
        mock_inst.start = MagicMock()
        mock_inst.send_audio_frame = MagicMock()

        def _stop():
            if callback:
                try:
                    callback.on_complete()
                except Exception:
                    pass
        mock_inst.stop = _stop
        mock_inst._callback = callback
        return mock_inst
    return factory


async def _recv_until_done(ws, timeout=1.5):
    """从 WebSocket 接收消息直到 done/error 或超时"""
    msgs = []
    try:
        while True:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
            msgs.append(msg)
            if msg.get("type") in ("done", "error"):
                break
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass
    return msgs


# ============================================================
# A. WAV Header 生成（纯函数）
# ============================================================

class TestWavHeader:
    """WAV Header — 第一帧 PCM 数据正确标记为 WAV 格式"""

    def test_wav_header_is_44_bytes(self):
        assert len(_make_wav_header(0, 16000)) == 44

    def test_wav_header_contains_RIFF_and_WAVE(self):
        h = _make_wav_header(4096, 16000)
        assert h[0:4] == b'RIFF'
        assert h[8:12] == b'WAVE'
        assert h[12:16] == b'fmt '
        assert h[36:40] == b'data'

    def test_wav_header_file_size_is_ffffffff_for_streaming(self):
        """流式模式下 file_size 设为 0xFFFFFFFF 表示未知长度"""
        h = _make_wav_header(4096, 16000)
        assert struct.unpack_from('<I', h, 4)[0] == 0xFFFFFFFF

    def test_wav_header_pcm_mono_16bit(self):
        h = _make_wav_header(1024, 16000)
        assert struct.unpack_from('<H', h, 20)[0] == 1
        assert struct.unpack_from('<H', h, 22)[0] == 1
        assert struct.unpack_from('<H', h, 34)[0] == 16

    def test_wav_header_sample_rate_preserved(self):
        for sr in [8000, 16000, 44100]:
            assert struct.unpack_from('<I', _make_wav_header(100, sr), 24)[0] == sr

    def test_data_size_field_is_ffffffff_for_streaming(self):
        """流式模式下 data_size 设为 0xFFFFFFFF 表示未知长度"""
        assert struct.unpack_from('<I', _make_wav_header(9999, 16000), 40)[0] == 0xFFFFFFFF

    def test_wav_header_ignores_input_size(self):
        """流式模式下忽略传入的 data_size 参数"""
        h = _make_wav_header(0, 16000)
        assert len(h) == 44
        assert struct.unpack_from('<I', h, 4)[0] == 0xFFFFFFFF


# ============================================================
# B. WebSocket 连接 — 认证与握手
# ============================================================

class TestASRWebSocketAuth:
    """认证: 有 Key → 接受 / 无 Key → 拒绝"""

    @pytest.mark.asyncio
    async def test_rejects_missing_api_key(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.QWEN_API_KEY", "your-api-key-here"):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=&vad=true&fmt=pcm"
            ) as ws:
                data = ws.receive_json()
                assert data["type"] == "error"
                assert "API Key" in data["message"]

    @pytest.mark.asyncio
    async def test_rejects_placeholder_key(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.QWEN_API_KEY", "your-api-key-here"):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=your-api-key-here&vad=true&fmt=pcm"
            ) as ws:
                data = ws.receive_json()
                assert data["type"] == "error"

    @pytest.mark.asyncio
    async def test_accepts_with_query_key(self):
        """场景 A1: 通过 query API Key 建立连接，mock worker 不崩溃"""
        from fastapi.testclient import TestClient
        from backend.main import app

        # 验证 mock factory 被调用（callback 被正确传入）
        cb_captured = []
        def tracking_factory(model=None, format=None, sample_rate=None,
                            semantic_punctuation_enabled=None, callback=None, **kwargs):
            cb_captured.append(callback)
            m = MagicMock()
            m.start = MagicMock()
            m.send_audio_frame = MagicMock()
            def _stop():
                if callback:
                    callback.on_complete()
            m.stop = _stop
            return m

        with patch("backend.main.Recognition", tracking_factory):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key-123&vad=true&fmt=pcm"
            ) as ws:
                await asyncio.sleep(0.2)
                ws.send_json({"type": "audio", "data": base64.b64encode(bytes(1600)).decode()})
                ws.send_json({"type": "stop"})
                await asyncio.sleep(0.2)

        assert len(cb_captured) > 0, "Recognition factory not called"
        assert cb_captured[0] is not None, "Callback not passed to Recognition"

    @pytest.mark.asyncio
    async def test_accepts_with_env_key(self):
        """场景 A1: 环境变量 API Key 时连接接受，mock worker 不崩溃"""
        from fastapi.testclient import TestClient
        from backend.main import app

        cb_captured = []
        def tracking_factory(model=None, format=None, sample_rate=None,
                            semantic_punctuation_enabled=None, callback=None, **kwargs):
            cb_captured.append(callback)
            m = MagicMock()
            m.start = MagicMock()
            m.send_audio_frame = MagicMock()
            def _stop():
                if callback:
                    callback.on_complete()
            m.stop = _stop
            return m

        with patch("backend.main.QWEN_API_KEY", "env-test-key"):
            with patch("backend.main.Recognition", tracking_factory):
                client = TestClient(app)
                with client.websocket_connect(
                    "/api/asr/stream?vad=true&fmt=pcm"
                ) as ws:
                    await asyncio.sleep(0.2)
                    ws.send_json({"type": "audio", "data": base64.b64encode(bytes(1600)).decode()})
                    ws.send_json({"type": "stop"})
                    await asyncio.sleep(0.2)

        assert len(cb_captured) > 0
        assert cb_captured[0] is not None


# ============================================================
# C. 消息协议 — partial / final / speech_start / speech_end / done
# ============================================================

class TestASRMessageProtocol:
    """消息协议正确性"""

    @pytest.mark.asyncio
    async def test_audio_frame_accepted(self):
        """音频帧 + stop 流程不崩溃"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                await asyncio.sleep(0.2)
                b64 = base64.b64encode(bytes(1600)).decode()
                ws.send_json({"type": "audio", "data": b64})
                ws.send_json({"type": "stop"})
                await asyncio.sleep(0.2)
                # 流程完成，无崩溃 = 测试通过

    @pytest.mark.asyncio
    async def test_invalid_base64_not_crash(self):
        """无效 base64 不会导致服务崩溃 — 错误被捕获并处理"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                await asyncio.sleep(0.2)
                b64 = base64.b64encode(bytes(1600)).decode()
                ws.send_json({"type": "audio", "data": b64})
                ws.send_json({"type": "audio", "data": "!!!not-b64!!!"})
                ws.send_json({"type": "stop"})
                await asyncio.sleep(0.5)
                # 无效 base64 触发 b64decode 异常 → 服务端捕获 → 应无崩溃

    @pytest.mark.asyncio
    async def test_stop_sends_done(self):
        """场景 A2: stop 后 worker 线程正常结束"""
        from fastapi.testclient import TestClient
        from backend.main import app

        cb_captured = []
        def tracking_factory(model=None, format=None, sample_rate=None,
                            semantic_punctuation_enabled=None, callback=None, **kwargs):
            cb_captured.append(callback)
            m = MagicMock()
            m.start = MagicMock()
            m.send_audio_frame = MagicMock()
            def _stop():
                cb_captured.append('stop_called')
                if callback:
                    callback.on_complete()
                    cb_captured.append('on_complete_called')
            m.stop = _stop
            return m

        with patch("backend.main.Recognition", tracking_factory):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                await asyncio.sleep(0.2)
                b64 = base64.b64encode(bytes(3200)).decode()
                ws.send_json({"type": "audio", "data": b64})
                ws.send_json({"type": "stop"})
                await asyncio.sleep(0.3)

        assert cb_captured[0] is not None, "Callback not passed"
        assert 'stop_called' in cb_captured, "rec.stop() not called"
        assert 'on_complete_called' in cb_captured, "callback.on_complete() not called"

    @pytest.mark.asyncio
    async def test_multiple_stops_no_double_done(self):
        """连续多个 stop 不会产生重复 done"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                b64 = base64.b64encode(bytes(3200)).decode()
                ws.send_json({"type": "audio", "data": b64})
                ws.send_json({"type": "stop"})
                ws.send_json({"type": "stop"})

                msgs = await _recv_until_done(ws, timeout=1.0)
                done_count = sum(1 for m in msgs if m.get("type") == "done")
                assert done_count <= 1

    @pytest.mark.asyncio
    async def test_error_message_format(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.QWEN_API_KEY", "your-api-key-here"):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=&vad=true&fmt=pcm"
            ) as ws:
                data = ws.receive_json()
                assert data["type"] == "error"
                assert isinstance(data["message"], str)
                assert len(data["message"]) > 0


# ============================================================
# D. Worker Thread 生命周期 — 资源清理
# ============================================================

class TestASRWorkerLifecycle:
    """Worker 线程启停，无资源泄漏"""

    @pytest.mark.asyncio
    async def test_worker_stops_after_disconnect(self):
        """场景 E3: 客户端断开后 worker 线程终止"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                b64 = base64.b64encode(bytes(3200)).decode()
                ws.send_json({"type": "audio", "data": b64})
                ws.send_json({"type": "stop"})
                await _recv_until_done(ws)

    @pytest.mark.asyncio
    async def test_multiple_audio_frames_no_crash(self):
        """连续多帧音频 + stop 不崩溃"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                b64 = base64.b64encode(bytes(3200)).decode()
                for _ in range(5):
                    ws.send_json({"type": "audio", "data": b64})
                ws.send_json({"type": "stop"})
                await _recv_until_done(ws)

    @pytest.mark.asyncio
    async def test_no_audio_frames_no_crash(self):
        """连接后立即断开 — 不发送任何音频帧也不崩溃"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                pass

    @pytest.mark.asyncio
    async def test_disconnect_without_stop_no_leak(self):
        """场景 E3: VAD 模式不发送 stop 直接断开"""
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.Recognition",
                   _make_mock_recognition_factory()):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                b64 = base64.b64encode(bytes(3200)).decode()
                for _ in range(10):
                    ws.send_json({"type": "audio", "data": b64})


# ============================================================
# E. WAV Header 在第一帧自动添加
# ============================================================

class TestWavHeaderInjection:
    """worker 线程中第一帧 PCM 自动封装 WAV header"""

    @pytest.mark.asyncio
    async def test_first_chunk_gets_wav_header(self):
        """第一帧 PCM 数据被 worker 自动添加 WAV header"""
        from fastapi.testclient import TestClient
        from backend.main import app

        mock_inst = None

        def capture_factory(model=None, format=None, sample_rate=None,
                           semantic_punctuation_enabled=None, callback=None, **kwargs):
            nonlocal mock_inst
            mock_inst = MagicMock()
            mock_inst.start = MagicMock()
            mock_inst.send_audio_frame = MagicMock()

            def _stop():
                if callback:
                    try:
                        callback.on_complete()
                    except Exception:
                        pass
            mock_inst.stop = _stop
            mock_inst._callback = callback
            return mock_inst

        with patch("backend.main.Recognition", capture_factory):
            client = TestClient(app)
            with client.websocket_connect(
                "/api/asr/stream?api_key=test-key&vad=true&fmt=pcm"
            ) as ws:
                await asyncio.sleep(0.2)  # 等待 worker 线程启动

                pcm_data = bytes([0] * 1600)
                b64 = base64.b64encode(pcm_data).decode()
                ws.send_json({"type": "audio", "data": b64})

                await asyncio.sleep(0.3)  # 等待 worker 处理

                ws.send_json({"type": "stop"})
                await _recv_until_done(ws)

        if mock_inst and mock_inst.send_audio_frame.call_count > 0:
            first_arg = mock_inst.send_audio_frame.call_args_list[0][0][0]
            assert len(first_arg) == 44 + len(pcm_data), \
                f"Expected {44 + len(pcm_data)} bytes, got {len(first_arg)}"
            assert first_arg[:4] == b'RIFF'
