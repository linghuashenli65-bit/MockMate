<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePrepStore } from '../stores/prep'
import { api } from '../services/api'
import { startStream, stopIfRunning } from '../services/asr'
import { esc, scoreColor, toast } from '../utils/helpers'
import MockHistoryView from './MockHistoryView.vue'

const router = useRouter()
const prep = usePrepStore()

/* ==================== 面试官管理 ==================== */
const interviewerList = ref([])
const editingId = ref(null)
const dialogOpen = ref(false)
const ivForm = ref({ name: '', role: '', style: '', focus_area: '', voice_style: '', prompt_template: '' })

const PRESET_INTERVIEWERS = [
  { name: '张工', role: '资深工程师', style: '严谨深入', focus_area: ['编码能力', '项目深挖', '技术原理'], voice_style: '稳重男声', aggressiveness: 0.5, follow_up_depth: 0.8, interruption_rate: 0.15, preferred_stages: ['intro', 'resume', 'general_tech'], prompt_template: '你是一位资深工程师，面试风格严谨深入。你善于从一个技术点层层深入，考察候选人对技术原理的掌握程度。\n\n你的核心考察方向是：编码能力、项目深挖、技术原理。\n\n注意事项：\n- 保持严谨深入的风格\n- 聚焦考察编码能力、项目深挖、技术原理\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容' },
  { name: '李总', role: '技术总监', style: '宏观开放', focus_area: ['架构设计', '系统设计', '技术决策'], voice_style: '阳光男声', aggressiveness: 0.4, follow_up_depth: 0.6, interruption_rate: 0.1, preferred_stages: ['general_tech', 'deep_dive', 'project'], prompt_template: '你是一位技术总监，面试风格宏观开放。你关注候选人的技术视野和架构能力，喜欢讨论系统设计的权衡取舍。\n\n你的核心考察方向是：架构设计、系统设计、技术决策。\n\n注意事项：\n- 保持宏观开放的风格\n- 聚焦考察架构设计、系统设计、技术决策\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容' },
  { name: '王老师', role: 'HR 负责人', style: '温和引导', focus_area: ['软技能', '文化匹配', '职业规划'], voice_style: '温柔女声', aggressiveness: 0.1, follow_up_depth: 0.2, interruption_rate: 0.0, preferred_stages: ['intro', 'hr', 'qna', 'end'], prompt_template: '你是一位 HR 负责人，面试风格温和引导。你关注候选人的职业规划、团队协作能力和文化契合度。\n\n你的核心考察方向是：软技能、文化匹配、职业规划。\n\n注意事项：\n- 保持温和引导的风格\n- 聚焦考察软技能、文化匹配、职业规划\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容' },
  { name: '刘博', role: '算法专家', style: '尖锐深入', focus_area: ['算法与数据结构', '代码优化', '数学基础'], voice_style: '深沉男声', aggressiveness: 0.8, follow_up_depth: 0.9, interruption_rate: 0.3, preferred_stages: ['deep_dive', 'pressure'], prompt_template: '你是一位算法专家，面试风格尖锐深入。你擅长考察算法思维和代码优化能力，喜欢挑战候选人的逻辑极限。\n\n你的核心考察方向是：算法与数据结构、代码优化、数学基础。\n\n注意事项：\n- 保持尖锐深入的风格\n- 聚焦考察算法与数据结构、代码优化、数学基础\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容' },
  { name: '陈总', role: '业务负责人', style: '实战导向', focus_area: ['业务理解', '项目落地', '沟通协作'], voice_style: '干练男声', aggressiveness: 0.6, follow_up_depth: 0.5, interruption_rate: 0.2, preferred_stages: ['project', 'pressure'], prompt_template: '你是一位业务负责人，面试风格实战导向。你关注候选人将技术转化为业务价值的能力，以及跨团队协作的实战经验。\n\n你的核心考察方向是：业务理解、项目落地、沟通协作。\n\n注意事项：\n- 保持实战导向的风格\n- 聚焦考察业务理解、项目落地、沟通协作\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容' },
]

function parseFocusArea(v) {
  return String(v || '').split(/[,，、]/).map((s) => s.trim()).filter(Boolean)
}

async function loadInterviewers() {
  try {
    const res = await api.mockListInterviewers()
    interviewerList.value = res.interviewers || []
  } catch (e) {
    toast('加载面试官失败: ' + e.message)
  }
}

async function addPresets() {
  if (!confirm('将一键添加 5 种预设面试官角色（资深工程师、技术总监、HR、算法专家、业务负责人），是否继续？')) return
  try {
    let count = 0
    for (const p of PRESET_INTERVIEWERS) {
      const existing = await api.mockListInterviewers()
      const hasName = (existing.interviewers || []).some((iv) => iv.name === p.name)
      if (hasName) continue
      await api.mockCreateInterviewer(p)
      count++
    }
    toast('成功添加 ' + count + ' 位预设面试官')
    await loadInterviewers()
  } catch (e) {
    toast('添加预设失败: ' + e.message)
  }
}

function openDialog(id) {
  editingId.value = id || null
  dialogOpen.value = true
  ivForm.value = { name: '', role: '', style: '', focus_area: '', voice_style: '', prompt_template: '' }
  if (id) {
    api.mockGetInterviewer(id).then((res) => {
      const iv = res.interviewer || {}
      ivForm.value = {
        name: iv.name || '',
        role: iv.role || '',
        style: iv.style || '',
        focus_area: Array.isArray(iv.focus_area) ? iv.focus_area.join(', ') : (iv.focus_area || ''),
        voice_style: iv.voice_style || '',
        prompt_template: iv.prompt_template || '',
      }
    }).catch(() => toast('获取面试官信息失败'))
  }
}

async function saveInterviewer() {
  const data = {
    name: ivForm.value.name.trim(),
    role: ivForm.value.role.trim(),
    style: ivForm.value.style.trim(),
    focus_area: parseFocusArea(ivForm.value.focus_area) || [ivForm.value.role.trim()],
  }
  if (ivForm.value.voice_style.trim()) data.voice_style = ivForm.value.voice_style.trim()
  if (ivForm.value.prompt_template.trim()) data.prompt_template = ivForm.value.prompt_template.trim()
  if (!data.name) { toast('请填写面试官姓名'); return }
  if (!data.role) { toast('请填写面试官角色'); return }
  if (!data.style) { toast('请填写面试风格'); return }
  try {
    if (editingId.value) {
      await api.mockUpdateInterviewer(editingId.value, data)
      toast('面试官已更新')
    } else {
      await api.mockCreateInterviewer(data)
      toast('面试官已添加')
    }
    dialogOpen.value = false
    await loadInterviewers()
  } catch (e) {
    toast('保存失败: ' + e.message)
  }
}

async function deleteInterviewer(id) {
  if (!confirm('确定要删除这个面试官吗？')) return
  try {
    await api.mockDeleteInterviewer(id)
    toast('面试官已删除')
    await loadInterviewers()
  } catch (e) {
    toast('删除失败: ' + e.message)
  }
}

/* ==================== 选择面试官 ==================== */
const selectedIds = ref([])
const duration = ref(40)

function toggleSelect(id) {
  const i = selectedIds.value.indexOf(id)
  if (i >= 0) selectedIds.value.splice(i, 1)
  else selectedIds.value.push(id)
}

const selectedInfos = computed(() => {
  return selectedIds.value.map((id) => {
    const iv = interviewerList.value.find((x) => String(x.id) === String(id))
    return iv ? { id: iv.id, name: iv.name, role: iv.role, voice_style: iv.voice_style || '' } : null
  }).filter(Boolean)
})

/* ==================== 会话状态 ==================== */
const sessionPhase = ref('config') // config | active | report
const subView = ref('start')       // start | history
const sessionId = ref(null)
const panelCards = ref([])
const questionText = ref('')
const questionVisible = ref(false)
const answerInput = ref('')
const submitHint = ref('')
const antiChat = ref(false)
const recording = ref(false)
const recordingStatus = ref('')
const timerText = ref('00:00:00')
const timerWarning = ref(false)
const reportData = ref(null)

let ws = null
let timerInterval = null
let elapsedSeconds = 0
let maxDuration = 0
let submitTime = 0
let pendingSubmit = false
let thinkingTimeout = null
let thinkingDotTimer = null
let realtimeStream = null
let switchInProgress = false
let streamingText = ''
let questionCounter = 0

/* 流式音频 */
let streamingAudioActive = false
let audioMediaSource = null
let audioSourceBuffer = null
let audioChunkQueue = []
let streamingAudioEl = null

/* ==================== 开始面试 ==================== */
function startInterview() {
  if (!prep.resumeScore || prep.resumeScore.score < 70) {
    toast('请先在「准备面试」标签页完成简历评分（需 ≥70 分）')
    router.push('/')
    return
  }
  if (!selectedIds.value.length) {
    toast('请至少选择一位面试官')
    return
  }
  startAsync()
}

async function startAsync() {
  maxDuration = duration.value * 60
  elapsedSeconds = 0
  try {
    const res = await api.mockStartInterview({
      interviewer_ids: selectedIds.value,
      max_duration: duration.value,
      resume: prep.resume.trim() || undefined,
      profile: { position: prep.position.trim(), ...(prep.company.trim() ? { company: prep.company.trim() } : {}) },
    })
    sessionId.value = res.session_id
    sessionPhase.value = 'active'
    panelCards.value = selectedInfos.value.map((iv, idx) => ({ ...iv, current: idx === 0, status: idx === 0 ? '正在发问' : '待发言' }))
    questionCounter = 0
    streamingText = ''
    questionText.value = ''
    questionVisible.value = false
    answerInput.value = ''
    submitHint.value = ''
    antiChat.value = false
    displayQuestion(res)
    startTimer()
    connectWebSocket()
    toast('拟真面试已开始')
  } catch (e) {
    toast('启动失败: ' + e.message)
  }
}

/* ==================== 计时 ==================== */
function startTimer() {
  clearInterval(timerInterval)
  timerInterval = setInterval(() => {
    elapsedSeconds++
    const remaining = Math.max(0, maxDuration - elapsedSeconds)
    const h = String(Math.floor(remaining / 3600)).padStart(2, '0')
    const m = String(Math.floor((remaining % 3600) / 60)).padStart(2, '0')
    const s = String(remaining % 60).padStart(2, '0')
    timerText.value = h + ':' + m + ':' + s
    timerWarning.value = remaining <= 300
  }, 1000)
}

function stopTimer() {
  clearInterval(timerInterval)
  timerInterval = null
}

/* ==================== 题目显示 ==================== */
function displayQuestion(data) {
  const qText = data.question_text || data.next_question_text || ''
  questionCounter++
  streamingText = qText
  questionText.value = qText
  questionVisible.value = true
  streamingAudioActive = false
  if (data.audio_url) {
    setTimeout(() => playAudio(data.audio_url), 300)
  }
  answerInput.value = ''
  submitHint.value = ''
  pendingSubmit = false
}

function showThinking() {
  questionVisible.value = false
  const base = '面试官正在思考'
  let dots = 0
  clearInterval(thinkingDotTimer)
  thinkingDotTimer = setInterval(() => {
    dots = (dots + 1) % 4
    questionText.value = base + '.'.repeat(dots)
  }, 400)
}

function showSwitchTransition(fromName, toName) {
  streamingAudioActive = false
  questionVisible.value = false
  questionText.value = fromName + ' 的问题问完了。接下来由 ' + toName + ' 继续。'
  panelCards.value = panelCards.value.map((c) => {
    if (c.name === fromName) return { ...c, current: false, exiting: true }
    if (c.name === toName) return { ...c, current: true, speaking: true }
    return c
  })
  setTimeout(() => {
    panelCards.value = panelCards.value.map((c) => ({ ...c, exiting: false }))
  }, 500)
}

function scheduleNextQuestion(data) {
  clearTimeout(thinkingTimeout)
  const elapsed = Date.now() - submitTime
  const delay = Math.max(0, 2500 - elapsed)
  clearPendingSubmit()
  thinkingTimeout = setTimeout(() => {
    thinkingTimeout = null
    displayQuestion(data)
  }, delay)
}

function finalizeQuestion(data) {
  clearPendingSubmit()
  const finalText = data.next_question_text || data.question_text || ''
  if (finalText) {
    streamingText = finalText
    questionText.value = finalText
    questionVisible.value = true
  }
  streamingText = ''
  if (data.audio_url && !streamingAudioActive) {
    setTimeout(() => playAudio(data.audio_url), 300)
  }
  streamingAudioActive = false
}

/* ==================== 提交回答 ==================== */
function submitAnswer() {
  if (pendingSubmit) return
  const text = answerInput.value.trim()
  if (!text) { toast('请先输入回答'); return }
  if (/^(你好|您好|哈哈|呵呵|嗯|哦|不知道|不会|谢谢|hi|hello|test|测试|\.\.\.|你猜|你说)$/i.test(text)) {
    answerInput.value = ''
    showAntiChat()
    return
  }
  pendingSubmit = true
  submitTime = Date.now()
  answerInput.value = ''
  submitHint.value = '已提交当前回答'
  showThinking()
  const payload = { type: 'answer', text, elapsed_minutes: Math.floor(elapsedSeconds / 60) }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload))
    // 60s 降级 REST
    setTimeout(async () => {
      if (!pendingSubmit) return
      pendingSubmit = false
      try {
        const res = await api.mockSubmitAnswer({ session_id: sessionId.value, answer: text, elapsed_minutes: Math.floor(elapsedSeconds / 60) })
        if (res.completed) handleInterviewEnd(res)
        else if (res.next_question_text) displayQuestion(res)
      } catch (e) { toast('提交失败: ' + e.message) }
      clearPendingSubmit()
    }, 60000)
  } else {
    api.mockSubmitAnswer({ session_id: sessionId.value, answer: text, elapsed_minutes: Math.floor(elapsedSeconds / 60) })
      .then((res) => {
        if (res.completed) handleInterviewEnd(res)
        else if (res.next_question_text) displayQuestion(res)
        clearPendingSubmit()
      })
      .catch((e) => { toast('提交失败: ' + e.message); clearPendingSubmit() })
  }
}

function clearPendingSubmit() {
  pendingSubmit = false
  clearTimeout(thinkingTimeout)
  thinkingTimeout = null
  clearInterval(thinkingDotTimer)
  thinkingDotTimer = null
  submitHint.value = ''
}

function showAntiChat() {
  antiChat.value = true
  setTimeout(() => { antiChat.value = false }, 3000)
}

/* ==================== WebSocket ==================== */
function connectWebSocket() {
  if (!sessionId.value) return
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = proto + '//' + window.location.host + '/api/mock/interview/ws/' + sessionId.value
  try {
    ws = new WebSocket(url)
    ws.onmessage = (event) => {
      try { handleWsMessage(JSON.parse(event.data)) } catch (e) { console.error('WS 消息解析失败:', e) }
    }
    ws.onclose = () => { ws = null }
    ws.onerror = (err) => console.error('WS 错误:', err)
  } catch (e) {
    console.warn('WebSocket 连接失败，将使用 REST API:', e)
    ws = null
  }
}

function handleWsMessage(msg) {
  switch (msg.type) {
    case 'switch_interviewer':
      switchInProgress = true
      showSwitchTransition(msg.from, msg.to)
      streamingText = ''
      break
    case 'question':
      if (msg.switch_from && msg.switch_to) {
        if (switchInProgress) {
          switchInProgress = false
          scheduleNextQuestion(msg)
        } else {
          showSwitchTransition(msg.switch_from, msg.switch_to)
          setTimeout(() => scheduleNextQuestion(msg), 2000)
        }
      } else if (msg.streamed) {
        finalizeQuestion(msg)
      } else {
        scheduleNextQuestion(msg)
      }
      break
    case 'question_token':
      if (typeof msg.token === 'string') {
        if (!questionVisible.value) {
          clearInterval(thinkingDotTimer)
          questionVisible.value = true
          questionText.value = ''
        }
        streamingText += msg.token
        questionText.value = streamingText
      }
      break
    case 'audio_chunk':
      if (!streamingAudioActive) {
        if (!initAudioStream()) break
        streamingAudioActive = true
        const card = panelCards.value.find((c) => c.current)
        if (card) card.speaking = true
      }
      if (msg.data) feedAudioChunk(msg.data)
      break
    case 'audio_done':
      finalizeAudioStream(msg.audio_url)
      break
    case 'clear_audio':
      stopAudioStream()
      streamingText = ''
      break
    case 'eval_token':
      break
    case 'evaluation':
      break
    case 'end':
      clearPendingSubmit()
      handleInterviewEnd(msg)
      break
    case 'error':
      pendingSubmit = false
      toast('错误: ' + (msg.message || '未知错误'))
      break
    case 'pong':
      break
  }
}

/* ==================== 音频播放 ==================== */
function playAudio(url) {
  if (!url) return
  const card = panelCards.value.find((c) => c.current)
  if (card) card.speaking = true
  const audio = new Audio(url)
  audio.onended = () => { if (card) card.speaking = false }
  audio.onerror = () => { if (card) card.speaking = false }
  audio.play().catch(() => {
    if (card) card.speaking = false
  })
}

function initAudioStream() {
  audioChunkQueue = []
  streamingAudioEl = document.getElementById('mockStreamAudio')
  if (!streamingAudioEl) {
    streamingAudioEl = document.createElement('audio')
    streamingAudioEl.id = 'mockStreamAudio'
    streamingAudioEl.style.display = 'none'
    document.body.appendChild(streamingAudioEl)
  }
  streamingAudioEl.onended = () => {
    const card = panelCards.value.find((c) => c.current)
    if (card) card.speaking = false
  }
  streamingAudioEl.onerror = () => {
    const card = panelCards.value.find((c) => c.current)
    if (card) card.speaking = false
  }
  try {
    if (!window.MediaSource) return false
    audioMediaSource = new MediaSource()
    audioMediaSource.addEventListener('sourceopen', () => {
      try {
        audioSourceBuffer = audioMediaSource.addSourceBuffer('audio/mpeg')
        audioSourceBuffer.addEventListener('updateend', () => {
          if (audioChunkQueue.length > 0 && !audioSourceBuffer.updating) {
            const next = audioChunkQueue.shift()
            try { audioSourceBuffer.appendBuffer(next) } catch (e) { console.warn('追加音频 chunk 失败:', e) }
          }
        })
        while (audioChunkQueue.length > 0 && audioSourceBuffer && !audioSourceBuffer.updating) {
          audioSourceBuffer.appendBuffer(audioChunkQueue.shift())
        }
      } catch (e) {
        console.warn('SourceBuffer 创建失败:', e)
        audioSourceBuffer = null
      }
    })
    streamingAudioEl.src = URL.createObjectURL(audioMediaSource)
    streamingAudioEl.play().catch((e) => console.warn('流式音频启动（可忽略）:', e.message))
    return true
  } catch (e) {
    console.warn('MediaSource 初始化失败:', e)
    audioMediaSource = null
    return false
  }
}

function feedAudioChunk(base64Data) {
  try {
    const binary = atob(base64Data)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    const buffer = bytes.buffer
    if (audioSourceBuffer && !audioSourceBuffer.updating) audioSourceBuffer.appendBuffer(buffer)
    else audioChunkQueue.push(buffer)
  } catch (e) {
    console.warn('音频 chunk 解码失败:', e)
  }
}

function finalizeAudioStream(fallbackUrl) {
  if (audioMediaSource && audioMediaSource.readyState === 'open') {
    try { audioMediaSource.endOfStream() } catch (e) { console.warn('endOfStream 失败:', e) }
  }
  if (fallbackUrl) {
    const hasBuffered = audioSourceBuffer && audioSourceBuffer.buffered && audioSourceBuffer.buffered.length > 0
    if (!hasBuffered) setTimeout(() => playAudio(fallbackUrl), 300)
  }
  streamingAudioActive = false
}

function stopAudioStream() {
  if (audioMediaSource) {
    try {
      if (audioMediaSource.readyState === 'open') audioMediaSource.endOfStream()
    } catch (e) { /* ignore */ }
    audioMediaSource = null
  }
  audioSourceBuffer = null
  audioChunkQueue = []
  if (streamingAudioEl) {
    streamingAudioEl.pause()
    streamingAudioEl.removeAttribute('src')
    streamingAudioEl.load()
  }
  panelCards.value.forEach((c) => { c.speaking = false })
  streamingAudioActive = false
}

/* ==================== 结束面试 ==================== */
function endInterview() {
  if (!confirm('确定要结束当前面试吗？')) return
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'end_request', reason: 'user_request' }))
  } else {
    doEndInterview()
  }
}

async function doEndInterview() {
  try {
    const res = await api.mockEndInterview(sessionId.value)
    handleInterviewEnd(res)
  } catch (e) {
    toast('结束面试失败: ' + e.message)
  }
}

function handleInterviewEnd(data) {
  stopTimer()
  pendingSubmit = false
  clearTimeout(thinkingTimeout)
  clearInterval(thinkingDotTimer)
  if (ws) { try { ws.close() } catch (e) { /* ignore */ } ws = null }
  if (realtimeStream) { realtimeStream.stop(); realtimeStream = null }
  stopAudioStream()
  stopIfRunning()
  recording.value = false

  const sid = data.session_id || sessionId.value
  sessionPhase.value = 'report'
  questionText.value = '面试结束'
  questionVisible.value = false
  if (sid) {
    api.mockGetReport(sid).then((res) => {
      reportData.value = res
      toast('面试已结束，报告已生成')
    }).catch(() => toast('面试已结束'))
  } else {
    toast('面试已结束')
  }
}

function backToConfig() {
  sessionPhase.value = 'config'
  reportData.value = null
  sessionId.value = null
  panelCards.value = []
}

const reportSummary = computed(() => {
  const data = reportData.value
  if (!data) return null
  const history = data.history || []
  const qaPairs = []
  let currentQ = null
  for (const entry of history) {
    if (entry.type === 'question') {
      if (currentQ) qaPairs.push(currentQ)
      currentQ = { question: entry, answer: null }
    } else if (entry.type === 'answer' && currentQ) {
      currentQ.answer = entry
      qaPairs.push(currentQ)
      currentQ = null
    }
  }
  if (currentQ) qaPairs.push(currentQ)
  const scores = qaPairs.filter((p) => p.answer && p.answer.score != null).map((p) => p.answer.score)
  const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null
  const byInterviewer = {}
  qaPairs.forEach((p) => {
    const name = p.question.interviewer_name || '未知'
    if (!byInterviewer[name]) byInterviewer[name] = { questions: [], scores: [] }
    byInterviewer[name].questions.push(p)
    if (p.answer && p.answer.score != null) byInterviewer[name].scores.push(p.answer.score)
  })
  return {
    totalQ: data.total_questions || qaPairs.length,
    coverage: data.coverage || {},
    avgScore,
    byInterviewer,
    qaPairs,
  }
})

function copyReport() {
  const text = document.getElementById('mockReportContent')?.innerText || ''
  navigator.clipboard.writeText(text).then(() => toast('报告已复制到剪贴板')).catch(() => toast('复制失败'))
}

/* ==================== 语音录制 ==================== */
function toggleRecording() {
  if (realtimeStream && realtimeStream.isActive()) {
    realtimeStream.stop()
    realtimeStream = null
    recording.value = false
    recordingStatus.value = ''
    return
  }
  recording.value = true
  recordingStatus.value = '● 录音中...'
  realtimeStream = startStream({
    onPartial: (partial, full) => {
      answerInput.value = full
      recordingStatus.value = '● 录音中... ' + full.slice(0, 24)
    },
    onFinal: (finalText) => {
      answerInput.value = finalText
    },
    onSpeechStart: () => { recordingStatus.value = '● 语音中...' },
    onSpeechEnd: () => { recordingStatus.value = '● 等待说话...' },
    onError: (msg) => {
      toast('语音识别错误: ' + msg)
      realtimeStream = null
      recording.value = false
      recordingStatus.value = ''
    },
    onDone: () => {
      recordingStatus.value = '✓ 识别完成'
      setTimeout(() => { if (recordingStatus.value === '✓ 识别完成') recordingStatus.value = '' }, 2000)
    },
  })
  if (!realtimeStream) {
    recording.value = false
    recordingStatus.value = '🚫 无法启动'
  }
}

function checkMediaDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    let hint = ''
    if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      hint = '麦克风需要 localhost 或 HTTPS 访问。'
    } else {
      hint = '当前浏览器不支持麦克风 API，请更换最新版 Chrome/Edge。'
    }
    toast('麦克风不可用: ' + hint)
    return false
  }
  return true
}

/* 语音测试（点击 TTS / 长按 ASR） */
const vtfTesting = ref(false)
const vtfFeedback = ref('')
function vtFeedback(text, type) {
  vtfFeedback.value = text
  vtfType.value = type || 'info'
  setTimeout(() => { vtfFeedback.value = '' }, 4000)
}
const vtfType = ref('info')
let vtPressTimer = null
let vtLongPress = false
let vtRecorder = null
let vtStream = null
let vtChunks = []

function vtTestTts() {
  if (vtfTesting.value) return
  vtfTesting.value = true
  vtFeedback('正在测试语音合成...', 'info')
  fetch('/api/mock/voice/tts').then((r) => r.json()).then((data) => {
    if (data.audio_url) {
      const audio = new Audio(data.audio_url)
      audio.onended = () => { vtfTesting.value = false; vtFeedback('语音合成正常 ✓', 'success') }
      audio.onerror = () => { vtfTesting.value = false; vtFeedback('语音播放失败', 'error') }
      audio.play().catch(() => { vtfTesting.value = false; vtFeedback('语音播放失败', 'error') })
    } else {
      vtfTesting.value = false
      vtFeedback('语音合成服务不可用', 'error')
    }
  }).catch(() => { vtfTesting.value = false; vtFeedback('语音测试请求失败', 'error') })
}

function vtStartAsr() {
  if (!checkMediaDevices()) return
  vtFeedback('录音中...松开结束', 'info')
  navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
    vtStream = stream
    vtChunks = []
    vtRecorder = new MediaRecorder(stream)
    vtRecorder.ondataavailable = (e) => { if (e.data.size > 0) vtChunks.push(e.data) }
    vtRecorder.onstop = () => {
      vtFeedback('识别中...', 'info')
      const blob = new Blob(vtChunks, { type: 'audio/webm' })
      const formData = new FormData()
      formData.append('file', blob, 'test_audio.webm')
      fetch('/api/mock/voice/asr', { method: 'POST', body: formData })
        .then((r) => r.json())
        .then((data) => {
          if (data.transcription) vtFeedback('识别结果: "' + data.transcription + '"', 'success')
          else vtFeedback('识别无结果', 'error')
        })
        .catch(() => vtFeedback('识别请求失败', 'error'))
        .finally(() => { if (vtStream) { vtStream.getTracks().forEach((t) => t.stop()); vtStream = null } })
    }
    vtRecorder.start()
  }).catch((err) => vtFeedback('麦克风访问失败: ' + err.message, 'error'))
}

function vtStopAsr() {
  if (vtRecorder && vtRecorder.state !== 'inactive') vtRecorder.stop()
  vtRecorder = null
}

function vtDown() {
  vtLongPress = false
  vtPressTimer = setTimeout(() => { vtLongPress = true; vtStartAsr() }, 400)
}
function vtUp() {
  clearTimeout(vtPressTimer)
  if (vtLongPress) vtStopAsr()
  else vtTestTts()
}

/* ==================== T 键 ==================== */
function onKeydown(e) {
  if (e.key !== 't' && e.key !== 'T') return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (e.repeat || e.isComposing) return
  const tag = (e.target && e.target.tagName) || ''
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (e.target && e.target.isContentEditable) return
  if (sessionPhase.value === 'active') {
    e.preventDefault()
    toggleRecording()
  }
}

onMounted(() => {
  loadInterviewers()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  stopTimer()
  if (ws) { try { ws.close() } catch (e) { /* ignore */ } ws = null }
  if (realtimeStream) { realtimeStream.stop(); realtimeStream = null }
  stopIfRunning()
  stopAudioStream()
  if (vtRecorder && vtRecorder.state !== 'inactive') { try { vtRecorder.stop() } catch (e) { /* ignore */ } }
})
</script>

<template>
  <div>
    <!-- 子导航：开始面试 / 历史记录 -->
    <div v-if="sessionPhase !== 'active'" class="mock-subtabs">
      <button class="mock-subtab" :class="{ active: subView === 'start' }" @click="subView = 'start'">开始面试</button>
      <button class="mock-subtab" :class="{ active: subView === 'history' }" @click="subView = 'history'">历史记录</button>
    </div>

    <MockHistoryView v-if="subView === 'history' && sessionPhase !== 'active'" />

    <!-- ============ 配置区 ============ -->
    <template v-if="sessionPhase === 'config' && subView !== 'history'">
      <div class="card" id="mockInterviewerSection">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px">
          <h2 style="margin: 0">面试官角色配置</h2>
          <div style="display: flex; gap: 8px">
            <button class="btn btn-sm btn-secondary" title="一键添加5种典型面试官角色" @click="addPresets">+ 添加预设面试官</button>
            <button class="btn btn-primary btn-sm" @click="openDialog(null)">+ 自定义</button>
          </div>
        </div>
        <div style="margin-top: 12px">
          <div v-if="!interviewerList.length" class="mock-empty-state">
            还没有面试官<br>
            <button class="btn btn-sm btn-primary" @click="addPresets">添加预设角色</button>
          </div>
          <div v-for="iv in interviewerList" :key="iv.id" class="mock-iv-card">
            <div class="mock-iv-avatar">{{ (iv.name || '?').charAt(0) }}</div>
            <div class="mock-iv-info">
              <div class="mock-iv-name">{{ iv.name }}</div>
              <div class="mock-iv-role">{{ iv.role }} · {{ iv.style }}</div>
              <div class="mock-iv-tags">
                <span v-for="f in parseFocusArea(iv.focus_area)" :key="f" class="mock-iv-tag">{{ f }}</span>
              </div>
            </div>
            <div class="mock-iv-actions">
              <button class="btn btn-sm btn-secondary" @click="openDialog(iv.id)">编辑</button>
              <button class="btn btn-sm btn-danger" @click="deleteInterviewer(iv.id)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 面试官编辑弹窗 -->
      <Teleport to="body">
        <div v-if="dialogOpen" class="modal-overlay" style="display: flex" @click.self="dialogOpen = false">
          <div class="modal" style="max-width: 500px">
            <h3>{{ editingId ? '编辑面试官' : '添加面试官' }}</h3>
            <div class="form-group">
              <label>姓名</label>
              <input v-model="ivForm.name" type="text" placeholder="例如：张工">
            </div>
            <div class="form-group">
              <label>角色</label>
              <input v-model="ivForm.role" type="text" placeholder="例如：资深工程师、技术总监、HR负责人">
            </div>
            <div class="form-group">
              <label>面试风格</label>
              <input v-model="ivForm.style" type="text" placeholder="例如：严谨深入、宏观开放、温和引导">
            </div>
            <div class="form-group">
              <label>考察重点（逗号分隔）</label>
              <input v-model="ivForm.focus_area" type="text" placeholder="例如：编码能力, 项目深挖, 系统设计">
            </div>
            <div class="form-group">
              <label>音色（用于语音合成）</label>
              <input v-model="ivForm.voice_style" type="text" placeholder="预设：稳重男声 / 阳光男声 / 温柔女声 / 知性女声 / 活泼女声">
            </div>
            <div class="form-group">
              <label>自定义 Prompt（选填）</label>
              <textarea v-model="ivForm.prompt_template" rows="3" placeholder="留空则自动生成"></textarea>
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end">
              <button class="btn btn-secondary" @click="dialogOpen = false">取消</button>
              <button class="btn btn-primary" @click="saveInterviewer">保存</button>
            </div>
          </div>
        </div>
      </Teleport>

      <div class="card" id="mockStartSection">
        <h2>开始拟真面试</h2>
        <p style="font-size: 13px; color: var(--text2); margin-bottom: 12px">
          选择参与面试的面试官，系统将模拟多位面试官轮流提问的真实场景。
        </p>
        <div style="margin-bottom: 12px">
          <div v-if="!interviewerList.length" class="mock-empty-state">请先在上方添加面试官</div>
          <div
            v-for="iv in interviewerList"
            :key="iv.id"
            class="mock-iv-select-item"
            :class="{ selected: selectedIds.includes(iv.id) }"
            @click="toggleSelect(iv.id)"
          >
            <input type="checkbox" class="mock-iv-checkbox" :value="iv.id" :checked="selectedIds.includes(iv.id)" @click.stop>
            <span class="check-mark">✓</span>
            <div class="mock-iv-avatar" style="margin-right: 4px">{{ (iv.name || '?').charAt(0) }}</div>
            <div style="flex: 1; min-width: 0">
              <strong class="mock-iv-name">{{ iv.name }}</strong>
              <span class="mock-iv-role" style="font-size: 12px; color: var(--text2); margin-left: 8px">{{ iv.role }}</span>
              <div class="mock-iv-tags">
                <span v-for="f in parseFocusArea(iv.focus_area)" :key="f" class="mock-iv-tag">{{ f }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label>时长控制（分钟）</label>
          <div style="display: flex; gap: 8px; align-items: center">
            <input v-model.number="duration" type="range" min="15" max="60" value="40" style="flex: 1">
            <span style="font-size: 14px; font-weight: 600; min-width: 40px">{{ duration }}</span>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="!selectedIds.length" @click="startInterview">开始拟真面试</button>

        <!-- 语音测试 -->
        <div class="mock-vtf" style="position: static; margin-top: 16px; flex-direction: row; gap: 12px">
          <div
            class="mock-vtf-btn"
            style="width: 44px; height: 44px"
            @mousedown="vtDown"
            @mouseup="vtUp"
            @mouseleave="clearTimeout(vtPressTimer)"
            @touchstart.prevent="vtDown"
            @touchend.prevent="vtUp"
          >
            <span class="mock-vtf-icon">🔊</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 2px">
            <div style="font-size: 13px; color: var(--text2)">语音功能测试</div>
            <div style="font-size: 12px; color: var(--text2)">点击播放测试语音 · 长按录音识别</div>
            <div v-if="vtfFeedback" class="mock-vtf-feedback" :class="['show', vtfType]" style="position: static; margin: 0">{{ vtfFeedback }}</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ============ 沉浸面试区 ============ -->
    <div v-if="sessionPhase === 'active'" id="mockSessionSection">
      <div class="mock-topbar">
        <div class="mock-topbar-left">
          <span class="mock-brand">MockMate</span>
          <span class="mock-divider">｜</span>
          <span class="mock-position">{{ prep.position || '技术面试' }}</span>
        </div>
        <div class="mock-topbar-center"></div>
        <div class="mock-topbar-right">
          <span class="mock-countdown" :class="{ warning: timerWarning }">{{ timerText }}</span>
          <button class="mock-end-btn" style="margin-left: 24px" @click="endInterview">结束面试</button>
        </div>
      </div>

      <div class="mock-main">
        <div class="mock-panel">
          <div
            v-for="(card, idx) in panelCards"
            :key="idx"
            class="mock-panel-card"
            :class="{ current: card.current, exiting: card.exiting, speaking: card.speaking }"
          >
            <div class="mock-panel-card-badge">● {{ card.current ? '当前提问' : '待发言' }}</div>
            <div class="mock-iv-card-name">{{ card.name }}</div>
            <div class="mock-iv-card-role">{{ card.role }}</div>
            <div class="mock-iv-card-status">
              {{ card.current ? '正在发问' : '待发言' }}
              <span v-if="card.voice_style" class="mock-iv-voice-badge">{{ card.voice_style }}</span>
            </div>
          </div>
        </div>

        <div class="mock-question-area">
          <div v-if="questionVisible" class="mock-question-text">{{ questionText }}</div>
        </div>

        <div class="mock-input-area">
          <textarea v-model="answerInput" placeholder="沉稳作答..." rows="4"></textarea>
          <div class="mock-input-actions">
            <button class="mock-voice-btn" :class="{ recording }" title="语音输入 (T 键开关)" @click="toggleRecording">{{ recording ? '⏹' : '🎤' }}</button>
            <button class="mock-submit-btn" :class="{ submitted: submitHint }" @click="submitAnswer">提交回答</button>
            <span class="mock-submit-hint">{{ submitHint }}</span>
          </div>
          <div v-if="recordingStatus" class="mock-recording-status active">{{ recordingStatus }}</div>
          <div class="mock-anti-chat" :style="{ opacity: antiChat ? 1 : 0 }">[ 系统提示：当前为面试环境，请针对问题作答 ]</div>
        </div>
      </div>
    </div>

    <!-- ============ 报告 ============ -->
    <div v-if="sessionPhase === 'report' && reportData && subView !== 'history'" id="mockReportContent">
      <div style="margin-bottom: 8px">
        <button class="btn btn-secondary btn-sm" @click="backToConfig">← 返回配置</button>
      </div>
      <div class="card" style="border-left: 3px solid var(--accent)">
        <h2 style="font-size: 18px; text-transform: none; color: var(--text)">拟真面试报告</h2>
        <div class="score-row" style="margin: 12px 0">
          <span v-if="reportSummary.avgScore !== null" class="score-tag">
            综合评分 <span class="val" :style="{ color: scoreColor(reportSummary.avgScore) }">{{ reportSummary.avgScore }}</span>
          </span>
          <span v-for="(ivData, name) in reportSummary.byInterviewer" :key="name" class="score-tag">
            {{ name }} <span v-if="ivData.scores.length" class="val" :style="{ color: scoreColor(Math.round(ivData.scores.reduce((a, b) => a + b, 0) / ivData.scores.length)) }">{{ Math.round(ivData.scores.reduce((a, b) => a + b, 0) / ivData.scores.length) }}</span>
          </span>
        </div>
        <div style="font-size: 13px; color: var(--text2); margin-bottom: 4px">
          共提问 <strong>{{ reportSummary.totalQ }}</strong> 题，考察覆盖 <strong>{{ reportSummary.coverage.covered || 0 }}/{{ reportSummary.coverage.total || 0 }}</strong>
          <template v-if="reportSummary.coverage.remaining && reportSummary.coverage.remaining.length">，未覆盖：{{ reportSummary.coverage.remaining.join('、') }}</template>
        </div>
      </div>

      <template v-if="reportSummary.qaPairs.length">
        <h2 style="font-size: 16px; text-transform: none; color: var(--text); margin-top: 20px">问答回顾</h2>
        <div v-for="(p, idx) in reportSummary.qaPairs" :key="idx" class="card" style="margin-top: 10px; padding: 14px">
          <div style="font-size: 11px; color: var(--accent2); margin-bottom: 6px">
            第 {{ idx + 1 }} 题 · {{ p.question.interviewer_name || '' }}
            · 得分 <strong :style="{ color: scoreColor(p.answer && p.answer.score) }">{{ p.answer && p.answer.score != null ? p.answer.score : '未评分' }}</strong>
          </div>
          <div style="font-size: 14px; margin-bottom: 8px; padding: 8px 10px; background: var(--surface); border-radius: 6px"><strong>问：</strong>{{ p.question.question || '' }}</div>
          <div v-if="p.answer && p.answer.answer" style="font-size: 13px; color: var(--text2); margin-bottom: 6px; padding: 8px 10px; background: var(--surface2); border-radius: 6px"><strong>答：</strong>{{ p.answer.answer }}</div>
          <div v-else style="font-size: 13px; color: var(--text2); margin-bottom: 6px; font-style: italic">（未回答）</div>
          <div v-if="p.answer && p.answer.evaluation" style="font-size: 12px; color: var(--text2); padding: 8px 10px; background: var(--surface); border-radius: 6px; border-left: 2px solid var(--accent2)">{{ p.answer.evaluation }}</div>
        </div>
      </template>

      <div style="margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap">
        <button class="btn btn-primary" style="flex: 1" @click="backToConfig">返回配置</button>
        <button class="btn btn-secondary" @click="copyReport">复制报告</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mock-subtabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  padding: 4px;
  background: var(--surface);
  border-radius: var(--radius);
  width: fit-content;
}
.mock-subtab {
  padding: 8px 18px;
  border: none;
  background: none;
  border-radius: 8px;
  font-size: 14px;
  color: var(--text2);
  cursor: pointer;
  transition: all 0.2s;
}
.mock-subtab.active {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}
.mock-subtab:hover:not(.active) {
  color: var(--text);
}
</style>
