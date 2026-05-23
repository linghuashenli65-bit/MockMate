/* ========================================
   MockMate.ASR — 实时语音识别（边说边出字）

   内部使用 VoiceState FSM + ASR Reducer 模式，
   确保无状态竞争、无旧 session 污染、无资源泄漏。

   公开 API:
     ASR.startStream(options) → { stop, isActive, getSessionId }
     ASR.toggleMic()          — ASR Tab 独立模式（按钮触发）
     ASR.start() / ASR.stop() — ASR Tab 独立模式
     ASR.stopIfRunning()      — 安全停止（供外部调用）
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  var ASR = {};

  // ============================================================
  // VoiceState FSM
  // ============================================================

  var VoiceState = {
    IDLE: 'IDLE',
    REQUESTING_PERMISSION: 'REQUESTING_PERMISSION',
    CONNECTING: 'CONNECTING',
    RECORDING: 'RECORDING',
    STOPPING: 'STOPPING',
    ERROR: 'ERROR'
  };

  function voiceStateTransition(currentState, event) {
    var transitions = {};
    transitions[VoiceState.IDLE] = {
      press_t: VoiceState.REQUESTING_PERMISSION,
    };
    transitions[VoiceState.REQUESTING_PERMISSION] = {
      permission_granted: VoiceState.CONNECTING,
      permission_denied: VoiceState.ERROR,
      cancel: VoiceState.IDLE,
    };
    transitions[VoiceState.CONNECTING] = {
      ws_open: VoiceState.RECORDING,
      ws_error: VoiceState.ERROR,
      cancel: VoiceState.STOPPING,
    };
    transitions[VoiceState.RECORDING] = {
      press_t: VoiceState.STOPPING,
      ws_error: VoiceState.ERROR,
      tab_hidden: VoiceState.STOPPING,
    };
    transitions[VoiceState.STOPPING] = {
      cleanup_done: VoiceState.IDLE,
    };
    transitions[VoiceState.ERROR] = {
      reset: VoiceState.IDLE,
    };
    var t = transitions[currentState];
    if (!t) return null;
    return t[event] || null;
  }

  // ============================================================
  // ASR Reducer — partial/final 文本累积（纯函数）
  // ============================================================

  function asrReducer(state, action) {
    switch (action.type) {
      case 'partial':
        return {
          finalText: state.finalText,
          partialText: action.text,
          awaitingFinal: false,
        };
      case 'speech_end':
        return {
          finalText: state.finalText,
          partialText: state.partialText,
          awaitingFinal: true,
        };
      case 'final':
        return {
          finalText: state.finalText + action.text + ' ',
          partialText: '',
          awaitingFinal: false,
        };
      case 'reset':
        return {
          finalText: '',
          partialText: '',
          awaitingFinal: false,
        };
      default:
        return state;
    }
  }

  function getDisplayText(state) {
    return state.finalText + state.partialText;
  }

  // ============================================================
  // Session ID 生成（UUID 模式，防止旧 session 污染）
  // ============================================================

  function generateSessionId() {
    var chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    var id = 'asr-';
    for (var i = 0; i < 16; i++) {
      id += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    id += '-' + Date.now().toString(36);
    return id;
  }

  function shouldProcessMessage(msg, currentSessionId, voiceState) {
    if (msg.sessionId && msg.sessionId !== currentSessionId) {
      return false;
    }
    if (voiceState === VoiceState.IDLE && msg.type !== 'error') {
      return false;
    }
    return true;
  }

  // ============================================================
  // Keyboard Guard（共享工具函数）
  // ============================================================

  function shouldHandleTKey(event, activeTab, interviewStarted, voiceState) {
    if (event.ctrlKey || event.metaKey || event.altKey) return false;
    if (event.repeat) return false;
    if (event.isComposing) return false;
    if (activeTab !== 'mock') return false;
    if (!interviewStarted) return false;
    var tag = (event.target && event.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return false;
    if (event.target && event.target.isContentEditable) return false;
    if (voiceState !== VoiceState.IDLE && voiceState !== VoiceState.RECORDING) return false;
    return true;
  }

  // ============================================================
  // 流式引擎实例变量（单例，同一时间只允许一个流）
  // ============================================================

  var _activeStream = null; // 当前活跃的流对象

  // ASR Tab 独立模式的 DOM 引用
  var _btn, _status, _vadInd, _resultEl, _historyEl;
  var _micOn = false;       // ASR Tab 的麦克风状态
  var _sentenceCount = 0;

  // ============================================================
  // 公开 API：startStream(options)
  //
  // options:
  //   onPartial(text)        — 实时 partial 结果
  //   onFinal(text)          — 句子结束（累积后的完整文本）
  //   onSpeechStart()        — VAD 检测到语音
  //   onSpeechEnd()          — VAD 检测到静音
  //   onStatus(text, color)  — 状态消息
  //   onError(message)       — 错误
  //   onDone()               — 识别完成
  //   onStateChange(newState)— 状态变更通知
  //   apiKey                 — 可选 API Key
  //
  // 返回: { stop, isActive, getSessionId, getState }
  // ============================================================

  ASR.startStream = function (options) {
    var opts = options || {};

    // 防双连接
    if (_activeStream) {
      if (opts.onError) opts.onError('已有活跃的语音识别会话');
      return null;
    }

    var voiceState = VoiceState.IDLE;
    var ws = null;
    var audioCtx = null;
    var source = null;
    var processor = null;
    var stream = null;
    var micActive = false;
    var sessionId = generateSessionId();
    var asrState = { finalText: '', partialText: '', awaitingFinal: false };

    // 自适应噪声门：动态跟踪环境噪声底噪，过滤背景人声
    var noiseFloorEstimate = 0.001; // 噪声底噪估计（初始值 ≈ -60dBFS）
    var NOISE_FLOOR_FAST_COEF = 0.05;  // 底噪快速追踪（信号接近底噪时）
    var NOISE_FLOOR_SLOW_COEF = 0.001; // 底噪慢速追踪（有语音时，避免语音抬高底噪）
    var MIN_GATE = 0.002;    // 绝对最小门限 ≈ -54dBFS
    var GATE_RATIO = 2.5;    // 信号需高于底噪 2.5 倍（≈8dB SNR）才放行

    function setState(newState) {
      voiceState = newState;
      if (opts.onStateChange) opts.onStateChange(newState);
    }

    function setStatus(text, color) {
      if (opts.onStatus) opts.onStatus(text, color);
    }

    // ---- 音频处理 ----

    function startAudioProcessing() {
      if (!audioCtx) {
        try {
          audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        } catch (err) {
          setStatus('音频上下文创建失败: ' + err.message, '#ef4444');
          cleanup();
          return;
        }
      }

      if (audioCtx.state === 'suspended') {
        audioCtx.resume().catch(function () {});
      }

      try {
        source = audioCtx.createMediaStreamSource(stream);
        processor = audioCtx.createScriptProcessor(4096, 1, 1);

        processor.onaudioprocess = function (e) {
          if (!micActive || !ws || ws.readyState !== WebSocket.OPEN) return;

          var input = e.inputBuffer.getChannelData(0);
          var data = input;
          if (audioCtx.sampleRate !== 16000) {
            data = resample(input, audioCtx.sampleRate, 16000);
          }

          // 自适应噪声门：动态跟踪环境底噪，过滤背景人声和环境噪音
          // 近场语音 SNR 通常 >12dB，远场背景人声 SNR 通常 <6dB
          var sumSq = 0;
          for (var i = 0; i < data.length; i++) {
            sumSq += data[i] * data[i];
          }
          var rms = Math.sqrt(sumSq / data.length);

          // 更新的噪声底噪估计（不对称追踪）
          if (rms <= noiseFloorEstimate * 1.8) {
            // 当前帧接近底噪 → 快速更新以捕获环境变化（如有人开始在远处说话）
            noiseFloorEstimate = (1 - NOISE_FLOOR_FAST_COEF) * noiseFloorEstimate
                                 + NOISE_FLOOR_FAST_COEF * rms;
          } else {
            // 当前帧有语音 → 极慢更新（避免近场语音抬高底噪估计）
            noiseFloorEstimate = (1 - NOISE_FLOOR_SLOW_COEF) * noiseFloorEstimate
                                 + NOISE_FLOOR_SLOW_COEF * rms;
          }

          // 自适应门限：至少 MIN_GATE，或底噪的 GATE_RATIO 倍
          var gateThreshold = Math.max(MIN_GATE, noiseFloorEstimate * GATE_RATIO);
          if (rms < gateThreshold) {
            for (var k = 0; k < data.length; k++) {
              data[k] = 0;
            }
          }

          var pcm16 = new Int16Array(data.length);
          for (var i = 0; i < data.length; i++) {
            var s = Math.max(-1, Math.min(1, data[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }

          var bytes = new Uint8Array(pcm16.buffer);
          var binary = '';
          for (var j = 0; j < bytes.length; j++) {
            binary += String.fromCharCode(bytes[j]);
          }
          var b64 = btoa(binary);

          ws.send(JSON.stringify({ type: 'audio', data: b64, sessionId: sessionId }));
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);
      } catch (err) {
        setStatus('音频处理初始化失败: ' + err.message, '#ef4444');
        cleanup();
      }
    }

    function stopAudioProcessing() {
      if (processor) {
        processor.disconnect();
        processor = null;
      }
      if (source) {
        source.disconnect();
        source = null;
      }
      if (audioCtx) {
        audioCtx.close().catch(function () {});
        audioCtx = null;
      }
    }

    // ---- 资源清理（顺序：①ws.send(stop) → ②stop tracks → ③disconnect → ④ws.close → ⑤AudioCtx.close → ⑥state→IDLE） ----

    function cleanup() {
      stopAudioProcessing();
      if (stream) {
        stream.getTracks().forEach(function (t) { t.stop(); });
        stream = null;
      }
      micActive = false;
    }

    // ---- WebSocket 消息处理 ----

    function handleMessage(msg) {
      if (!shouldProcessMessage(msg, sessionId, voiceState)) return;

      switch (msg.type) {
        case 'partial':
          asrState = asrReducer(asrState, { type: 'partial', text: msg.text });
          if (opts.onPartial) opts.onPartial(asrState.partialText, getDisplayText(asrState));
          break;
        case 'final':
          asrState = asrReducer(asrState, { type: 'final', text: msg.text });
          if (opts.onFinal) opts.onFinal(asrState.finalText);
          break;
        case 'speech_start':
          if (opts.onSpeechStart) opts.onSpeechStart();
          break;
        case 'speech_end':
          asrState = asrReducer(asrState, { type: 'speech_end' });
          if (opts.onSpeechEnd) opts.onSpeechEnd();
          break;
        case 'done':
          if (opts.onDone) opts.onDone();
          break;
        case 'error':
          if (opts.onError) opts.onError(msg.message);
          break;
      }
    }

    // ---- 启动流程 ----

    function doStart() {
      // 获取 API Key
      var apiKey = opts.apiKey || (M.state && M.state._apiKeys && M.state._apiKeys.qwen_api_key) || '';

      // 连接 WebSocket
      var wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:')
        + '//' + location.host + '/api/asr/stream'
        + '?api_key=' + encodeURIComponent(apiKey)
        + '&vad=true'
        + '&fmt=pcm';

      try {
        ws = new WebSocket(wsUrl);
      } catch (err) {
        setState(VoiceState.ERROR);
        if (opts.onError) opts.onError('WebSocket 连接失败: ' + err.message);
        cleanup();
        return;
      }

      ws.onopen = function () {
        var newState = voiceStateTransition(voiceState, 'ws_open');
        if (newState) setState(newState);
        micActive = true;
        asrState = asrReducer(asrState, { type: 'reset' });
        startAudioProcessing();
        setStatus('● 麦克风已打开', '#22c55e');
      };

      ws.onmessage = function (event) {
        try {
          var msg = JSON.parse(event.data);
          console.log('[ASR] ←', msg.type, msg.type === 'partial' || msg.type === 'final' ? '"' + (msg.text || '').slice(0, 40) + '"' : '');
          handleMessage(msg);
        } catch (e) {
          console.error('[ASR] handleMessage 异常:', e);
        }
      };

      ws.onerror = function () {
        var newState = voiceStateTransition(voiceState, 'ws_error');
        if (newState) setState(newState);
        setStatus('WebSocket 连接异常', '#ef4444');
        cleanup();
        // 异常断开必须清除活跃流，防止死锁
        _activeStream = null;
      };

      ws.onclose = function () {
        if (voiceState !== VoiceState.IDLE && voiceState !== VoiceState.STOPPING) {
          setStatus('连接已断开', '#ef4444');
        }
        cleanup();
        // 如果不是正常 stop() 调用（stop() 已置 null），直接切到 IDLE
        if (voiceState !== VoiceState.IDLE) {
          setState(VoiceState.IDLE);
        }
        _activeStream = null;
      };
    }

    // ---- 实际启动（异步获取麦克风权限） ----

    var apiKey = opts.apiKey || (M.state && M.state._apiKeys && M.state._apiKeys.qwen_api_key) || '';

    // 提前创建 AudioContext（利用用户手势）
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    } catch (err) {
      // 延迟创建
    }

    // 获取麦克风
    var startPromise = navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
      }
    }).then(function (mediaStream) {
      stream = mediaStream;
      var newState = voiceStateTransition(VoiceState.REQUESTING_PERMISSION, 'permission_granted');
      if (newState) setState(newState);
      doStart();
      return streamObj;
    }).catch(function (err) {
      var newState = voiceStateTransition(VoiceState.REQUESTING_PERMISSION, 'permission_denied');
      if (newState) setState(newState);
      if (opts.onError) opts.onError('麦克风访问被拒绝: ' + err.message);
      if (audioCtx) { audioCtx.close(); audioCtx = null; }
      return null;
    });

    // 设置初始状态
    var newState = voiceStateTransition(VoiceState.IDLE, 'press_t');
    if (newState) setState(newState);

    // ---- 流对象 ----

    var streamObj = {
      _startPromise: startPromise,

      stop: function () {
        micActive = false;
        var newState = voiceStateTransition(voiceState, 'press_t');
        if (newState) setState(newState);

        // ① 通知服务器停止
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'stop', sessionId: sessionId }));
        }

        // ② 停止麦克风轨道
        if (stream) {
          stream.getTracks().forEach(function (t) { t.stop(); });
          stream = null;
        }

        // ③ 断开音频节点 + ⑤ 关闭 AudioContext
        stopAudioProcessing();

        // ④ 关闭 WebSocket（onclose 已置 null 避免二次 cleanup）
        if (ws) {
          ws.onclose = null;
          ws.close();
          ws = null;
        }

        // ⑥ 状态 → IDLE，清除活跃流
        var doneState = voiceStateTransition(voiceState, 'cleanup_done');
        if (doneState) setState(doneState);

        _activeStream = null;
        setStatus('麦克风已关闭', 'var(--text2)');
      },

      isActive: function () {
        return voiceState === VoiceState.RECORDING || voiceState === VoiceState.CONNECTING;
      },

      getSessionId: function () {
        return sessionId;
      },

      getState: function () {
        return voiceState;
      }
    };

    _activeStream = streamObj;
    return streamObj;
  };

  // ============================================================
  // ASR Tab 独立模式（兼容原有 API）
  // ============================================================

  ASR.init = function () {
    _btn = document.getElementById('asrMicBtn');
    _status = document.getElementById('asrStatus');
    _vadInd = document.getElementById('asrVadIndicator');
    _resultEl = document.getElementById('asrResult');
    _historyEl = document.getElementById('asrHistory');

    console.log('MockMate: ASR init OK');

    // 切换 Tab 时自动关闭麦克风
    var origSwitch = M.switchTab;
    M.switchTab = function (name) {
      if (name !== 'asr') ASR.stopIfRunning();
      origSwitch.call(M, name);
    };
  };

  ASR.toggleMic = function () {
    if (_micOn) {
      ASR.stop();
    } else {
      ASR.start();
    }
  };

  ASR.stopIfRunning = function () {
    if (_micOn) ASR.stop();
  };

  ASR.start = function () {
    if (_micOn) return;

    var streamObj = ASR.startStream({
      onPartial: function (text) {
        handlePartial(text);
      },
      onFinal: function (text) {
        handleFinal(text);
      },
      onSpeechStart: function () {
        if (_vadInd) _vadInd.style.display = 'inline';
      },
      onSpeechEnd: function () {
        if (_vadInd) _vadInd.style.display = 'none';
      },
      onStatus: function (text, color) {
        if (_status) {
          _status.textContent = text;
          _status.style.color = color || 'var(--text2)';
        }
      },
      onError: function (msg) {
        setStatus('错误: ' + msg, '#ef4444');
      },
      onDone: function () {
        setStatus('识别完成', 'var(--text2)');
      }
    });

    if (!streamObj) return;

    _micOn = true;
    _partialText = '';
    _sentenceCount = 0;
    updateBtn();
    if (_resultEl) _resultEl.innerHTML = '';

    // 将 streamObj 存下来供 stop 使用
    ASR._currentStream = streamObj;
  };

  ASR.stop = function () {
    if (!_micOn) return;

    var streamObj = ASR._currentStream;
    if (streamObj) {
      streamObj.stop();
      ASR._currentStream = null;
    }

    if (_vadInd) _vadInd.style.display = 'none';
    _micOn = false;
    updateBtn();
    setStatus('麦克风已关闭', 'var(--text2)');
  };

  // ---- 结果处理（ASR Tab UI） ----

  var _partialText = '';

  function handlePartial(text) {
    if (!_resultEl) return;
    var html = _resultEl.innerHTML;
    var lines = html.split('\n').filter(function (l, i) {
      return i > 0 || l !== '';
    });
    if (lines.length > 0 && lines[lines.length - 1].indexOf('\u25B6') === 0) {
      lines[lines.length - 1] = '\u25B6 ' + escapeHtml(text);
    } else {
      lines.push('\u25B6 ' + escapeHtml(text));
    }
    _resultEl.innerHTML = lines.join('\n');
    _resultEl.scrollTop = _resultEl.scrollHeight;
  }

  function handleFinal(text) {
    _sentenceCount++;
    if (_resultEl) {
      var lines = _resultEl.innerHTML.split('\n');
      if (lines.length > 0 && lines[lines.length - 1].indexOf('\u25B6') === 0) {
        lines[lines.length - 1] = '  ' + escapeHtml(text);
      } else {
        lines.push('  ' + escapeHtml(text));
      }
      _resultEl.innerHTML = lines.join('\n');
      _resultEl.scrollTop = _resultEl.scrollHeight;
    }
    addHistory(text);
  }

  function addHistory(text) {
    if (!_historyEl) return;
    var firstChild = _historyEl.firstChild;
    if (firstChild && firstChild.tagName === 'SPAN') {
      _historyEl.innerHTML = '';
    }
    var div = document.createElement('div');
    div.style.cssText = 'padding:6px 0;border-bottom:1px solid var(--border, #eee)';
    var num = document.createElement('span');
    num.style.cssText = 'color:var(--text2);margin-right:8px;font-size:12px';
    num.textContent = '#' + _sentenceCount;
    div.appendChild(num);
    div.appendChild(document.createTextNode(text));
    _historyEl.insertBefore(div, _historyEl.firstChild);
  }

  // ---- 辅助 ----

  function updateBtn() {
    if (!_btn) return;
    _btn.textContent = _micOn ? '\u23F9 关闭麦克风' : '\uD83C\uDFA4 打开麦克风';
    _btn.className = _micOn ? 'btn btn-danger' : 'btn btn-primary';
  }

  function setStatus(text, color) {
    if (_status) {
      _status.textContent = text;
      _status.style.color = color || 'var(--text2)';
    }
  }

  function resample(audioData, fromRate, toRate) {
    if (fromRate === toRate) return audioData;
    var ratio = fromRate / toRate;
    var newLength = Math.round(audioData.length / ratio);
    var result = new Float32Array(newLength);
    for (var i = 0; i < newLength; i++) {
      var pos = i * ratio;
      var idx = Math.floor(pos);
      var frac = pos - idx;
      var next = Math.min(idx + 1, audioData.length - 1);
      result[i] = audioData[idx] * (1 - frac) + audioData[next] * frac;
    }
    return result;
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ============================================================
  // 导出
  // ============================================================

  M.ASR = ASR;
  M.VoiceState = VoiceState;
  M.voiceStateTransition = voiceStateTransition;
  M.asrReducer = asrReducer;
  M.getDisplayText = getDisplayText;
  M.generateSessionId = generateSessionId;
  M.shouldProcessMessage = shouldProcessMessage;
  M.shouldHandleTKey = shouldHandleTKey;

  // 页面加载后自动初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ASR.init);
  } else {
    ASR.init();
  }

})(window.MockMate);
