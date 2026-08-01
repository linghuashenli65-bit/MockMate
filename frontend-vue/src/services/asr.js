/* ========================================
   MockMate ASR — 实时语音识别（边说边出字）

   VoiceState FSM + ASR Reducer，无状态竞争、无旧 session 污染。
   ======================================== */

export const VoiceState = {
  IDLE: 'IDLE',
  REQUESTING_PERMISSION: 'REQUESTING_PERMISSION',
  CONNECTING: 'CONNECTING',
  RECORDING: 'RECORDING',
  STOPPING: 'STOPPING',
  ERROR: 'ERROR',
}

export function voiceStateTransition(currentState, event) {
  const transitions = {}
  transitions[VoiceState.IDLE] = { press_t: VoiceState.REQUESTING_PERMISSION }
  transitions[VoiceState.REQUESTING_PERMISSION] = {
    permission_granted: VoiceState.CONNECTING,
    permission_denied: VoiceState.ERROR,
    cancel: VoiceState.IDLE,
  }
  transitions[VoiceState.CONNECTING] = {
    ws_open: VoiceState.RECORDING,
    ws_error: VoiceState.ERROR,
    cancel: VoiceState.STOPPING,
  }
  transitions[VoiceState.RECORDING] = {
    press_t: VoiceState.STOPPING,
    ws_error: VoiceState.ERROR,
    tab_hidden: VoiceState.STOPPING,
  }
  transitions[VoiceState.STOPPING] = { cleanup_done: VoiceState.IDLE }
  transitions[VoiceState.ERROR] = { reset: VoiceState.IDLE }
  const t = transitions[currentState]
  return t ? (t[event] || null) : null
}

export function asrReducer(state, action) {
  switch (action.type) {
    case 'partial':
      return { finalText: state.finalText, partialText: action.text, awaitingFinal: false }
    case 'speech_end':
      return { finalText: state.finalText, partialText: state.partialText, awaitingFinal: true }
    case 'final':
      return { finalText: state.finalText + action.text + ' ', partialText: '', awaitingFinal: false }
    case 'reset':
      return { finalText: '', partialText: '', awaitingFinal: false }
    default:
      return state
  }
}

export function getDisplayText(state) {
  return state.finalText + state.partialText
}

export function generateSessionId() {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let id = 'asr-'
  for (let i = 0; i < 16; i++) id += chars.charAt(Math.floor(Math.random() * chars.length))
  id += '-' + Date.now().toString(36)
  return id
}

export function shouldProcessMessage(msg, currentSessionId, voiceState) {
  if (msg.sessionId && msg.sessionId !== currentSessionId) return false
  if (voiceState === VoiceState.IDLE && msg.type !== 'error') return false
  return true
}

export function shouldHandleTKey(event, activeTab, interviewStarted, voiceState) {
  if (event.ctrlKey || event.metaKey || event.altKey) return false
  if (event.repeat) return false
  if (event.isComposing) return false
  if (activeTab !== 'mock') return false
  if (!interviewStarted) return false
  const tag = (event.target && event.target.tagName) || ''
  if (tag === 'INPUT' || tag === 'TEXTAREA') return false
  if (event.target && event.target.isContentEditable) return false
  if (voiceState !== VoiceState.IDLE && voiceState !== VoiceState.RECORDING) return false
  return true
}

function resample(audioData, fromRate, toRate) {
  if (fromRate === toRate) return audioData
  const ratio = fromRate / toRate
  const newLength = Math.round(audioData.length / ratio)
  const result = new Float32Array(newLength)
  for (let i = 0; i < newLength; i++) {
    const pos = i * ratio
    const idx = Math.floor(pos)
    const frac = pos - idx
    const next = Math.min(idx + 1, audioData.length - 1)
    result[i] = audioData[idx] * (1 - frac) + audioData[next] * frac
  }
  return result
}

let _activeStream = null

/**
 * 启动实时语音识别流
 * options: { onPartial, onFinal, onSpeechStart, onSpeechEnd, onStatus, onError, onDone, onStateChange, apiKey }
 * 返回 { stop, isActive, getSessionId, getState } 或 null（已有活跃会话）
 */
export function startStream(options) {
  const opts = options || {}
  if (_activeStream) {
    if (opts.onError) opts.onError('已有活跃的语音识别会话')
    return null
  }

  let voiceState = VoiceState.IDLE
  let ws = null
  let audioCtx = null
  let source = null
  let processor = null
  let stream = null
  let micActive = false
  const sessionId = generateSessionId()
  let asrState = { finalText: '', partialText: '', awaitingFinal: false }

  // 自适应噪声门
  let noiseFloorEstimate = 0.001
  const NOISE_FLOOR_FAST_COEF = 0.05
  const NOISE_FLOOR_SLOW_COEF = 0.001
  const MIN_GATE = 0.002
  const GATE_RATIO = 2.5

  function setState(newState) {
    voiceState = newState
    if (opts.onStateChange) opts.onStateChange(newState)
  }

  function setStatus(text, color) {
    if (opts.onStatus) opts.onStatus(text, color)
  }

  function startAudioProcessing() {
    if (!audioCtx) {
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 })
      } catch (err) {
        setStatus('音频上下文创建失败: ' + err.message, '#ef4444')
        cleanup()
        return
      }
    }
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {})

    try {
      source = audioCtx.createMediaStreamSource(stream)
      processor = audioCtx.createScriptProcessor(4096, 1, 1)
      processor.onaudioprocess = (e) => {
        if (!micActive || !ws || ws.readyState !== WebSocket.OPEN) return
        let data = e.inputBuffer.getChannelData(0)
        if (audioCtx.sampleRate !== 16000) data = resample(data, audioCtx.sampleRate, 16000)

        let sumSq = 0
        for (let i = 0; i < data.length; i++) sumSq += data[i] * data[i]
        const rms = Math.sqrt(sumSq / data.length)
        if (rms <= noiseFloorEstimate * 1.8) {
          noiseFloorEstimate = (1 - NOISE_FLOOR_FAST_COEF) * noiseFloorEstimate + NOISE_FLOOR_FAST_COEF * rms
        } else {
          noiseFloorEstimate = (1 - NOISE_FLOOR_SLOW_COEF) * noiseFloorEstimate + NOISE_FLOOR_SLOW_COEF * rms
        }
        const gateThreshold = Math.max(MIN_GATE, noiseFloorEstimate * GATE_RATIO)
        if (rms < gateThreshold) {
          for (let k = 0; k < data.length; k++) data[k] = 0
        }

        const pcm16 = new Int16Array(data.length)
        for (let i = 0; i < data.length; i++) {
          const s = Math.max(-1, Math.min(1, data[i]))
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
        }
        const bytes = new Uint8Array(pcm16.buffer)
        let binary = ''
        for (let j = 0; j < bytes.length; j++) binary += String.fromCharCode(bytes[j])
        ws.send(JSON.stringify({ type: 'audio', data: btoa(binary), sessionId }))
      }
      source.connect(processor)
      processor.connect(audioCtx.destination)
    } catch (err) {
      setStatus('音频处理初始化失败: ' + err.message, '#ef4444')
      cleanup()
    }
  }

  function stopAudioProcessing() {
    if (processor) { processor.disconnect(); processor = null }
    if (source) { source.disconnect(); source = null }
    if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null }
  }

  function cleanup() {
    stopAudioProcessing()
    if (stream) {
      stream.getTracks().forEach((t) => t.stop())
      stream = null
    }
    micActive = false
  }

  function handleMessage(msg) {
    if (!shouldProcessMessage(msg, sessionId, voiceState)) return
    switch (msg.type) {
      case 'partial':
        asrState = asrReducer(asrState, { type: 'partial', text: msg.text })
        if (opts.onPartial) opts.onPartial(asrState.partialText, getDisplayText(asrState))
        break
      case 'final':
        asrState = asrReducer(asrState, { type: 'final', text: msg.text })
        if (opts.onFinal) opts.onFinal(asrState.finalText)
        break
      case 'speech_start':
        if (opts.onSpeechStart) opts.onSpeechStart()
        break
      case 'speech_end':
        asrState = asrReducer(asrState, { type: 'speech_end' })
        if (opts.onSpeechEnd) opts.onSpeechEnd()
        break
      case 'done':
        if (opts.onDone) opts.onDone()
        break
      case 'error':
        if (opts.onError) opts.onError(msg.message)
        break
    }
  }

  function doStart() {
    const wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:')
      + '//' + location.host + '/api/asr/stream?vad=true&fmt=pcm'
    try {
      ws = new WebSocket(wsUrl)
    } catch (err) {
      setState(VoiceState.ERROR)
      if (opts.onError) opts.onError('WebSocket 连接失败: ' + err.message)
      cleanup()
      return
    }

    ws.onopen = () => {
      const ns = voiceStateTransition(voiceState, 'ws_open')
      if (ns) setState(ns)
      micActive = true
      asrState = asrReducer(asrState, { type: 'reset' })
      startAudioProcessing()
      setStatus('● 麦克风已打开', '#22c55e')
    }
    ws.onmessage = (event) => {
      try { handleMessage(JSON.parse(event.data)) } catch (e) { console.error('[ASR] handleMessage 异常:', e) }
    }
    ws.onerror = () => {
      const ns = voiceStateTransition(voiceState, 'ws_error')
      if (ns) setState(ns)
      setStatus('WebSocket 连接异常', '#ef4444')
      cleanup()
      _activeStream = null
    }
    ws.onclose = () => {
      if (voiceState !== VoiceState.IDLE && voiceState !== VoiceState.STOPPING) {
        setStatus('连接已断开', '#ef4444')
      }
      cleanup()
      if (voiceState !== VoiceState.IDLE) setState(VoiceState.IDLE)
      _activeStream = null
    }
  }

  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 })
  } catch { /* 延迟创建 */ }

  const startPromise = navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
  }).then((mediaStream) => {
    stream = mediaStream
    const ns = voiceStateTransition(VoiceState.REQUESTING_PERMISSION, 'permission_granted')
    if (ns) setState(ns)
    doStart()
    return streamObj
  }).catch((err) => {
    const ns = voiceStateTransition(VoiceState.REQUESTING_PERMISSION, 'permission_denied')
    if (ns) setState(ns)
    if (opts.onError) opts.onError('麦克风访问被拒绝: ' + err.message)
    if (audioCtx) { audioCtx.close(); audioCtx = null }
    return null
  })

  const ns0 = voiceStateTransition(VoiceState.IDLE, 'press_t')
  if (ns0) setState(ns0)

  const streamObj = {
    _startPromise: startPromise,
    stop() {
      micActive = false
      const ns = voiceStateTransition(voiceState, 'press_t')
      if (ns) setState(ns)
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop', sessionId }))
      }
      if (stream) {
        stream.getTracks().forEach((t) => t.stop())
        stream = null
      }
      stopAudioProcessing()
      if (ws) {
        ws.onclose = null
        ws.close()
        ws = null
      }
      const done = voiceStateTransition(voiceState, 'cleanup_done')
      if (done) setState(done)
      _activeStream = null
      setStatus('麦克风已关闭', 'var(--text2)')
    },
    isActive() {
      return voiceState === VoiceState.RECORDING || voiceState === VoiceState.CONNECTING
    },
    getSessionId() { return sessionId },
    getState() { return voiceState },
  }

  _activeStream = streamObj
  return streamObj
}

export function stopIfRunning() {
  if (_activeStream) {
    _activeStream.stop()
    _activeStream = null
  }
}

export default { startStream, stopIfRunning, VoiceState }
