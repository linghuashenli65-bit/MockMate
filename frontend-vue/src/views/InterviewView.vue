<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePrepStore, ROUND_TOTALS } from '../stores/prep'
import { useSettingsStore } from '../stores/settings'
import { api } from '../services/api'
import { diffLabel, downloadText, esc, ls, md, ROUND_NAMES, scoreColor, toast } from '../utils/helpers'
import FeedbackButtons from '../components/FeedbackButtons.vue'
import HistoryView from './HistoryView.vue'

const router = useRouter()
const prep = usePrepStore()
const settings = useSettingsStore()

const ROUND_TIMES = { written: 90, tech_1: 300, tech_2: 300, comprehensive: 300 }
const INTERVIEW_TIME = 180
const WRITTEN_TIME = 90

/* ---------- 视图状态 ---------- */
const phase = ref('idle') // idle | loading | question | evaluation | report
const subView = ref('start') // start | history
const question = ref(null)
const questionIndex = ref(0)
const answerText = ref('')
const selectedOption = ref('')
const evaluation = ref(null)
const reportResult = ref(null)
const nextQuestion = ref(null)
const nextIndex = ref(0)
const nextAudio = ref(null)
const hintUsed = ref(false)
const hintText = ref('')
const suspended = ref([])
const submitting = ref(false)

/* ---------- 计时 ---------- */
const timerText = ref('00:00')
const countdownText = ref('00:00')
const countdownPaused = ref(false)
let timerInterval = null
let countdownInterval = null

/* ---------- TTS ---------- */
const ttsEnabled = ref(true)

const isWritten = computed(() => prep.isWrittenRound)
const totalQuestions = computed(() => prep.totalQuestions)
const roundLabel = computed(() => ROUND_NAMES[prep.currentRound] || prep.currentRound || '')
const canStart = computed(() => prep.resume.trim() && prep.profile && prep.resumeScore && prep.resumeScore.score >= 70)

function fmt(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, '0')
  const s = String(sec % 60).padStart(2, '0')
  return m + ':' + s
}

function startTimer() {
  const start = Date.now()
  clearInterval(timerInterval)
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - start) / 1000)
    timerText.value = fmt(elapsed)
  }, 1000)
}

function stopTimer() {
  clearInterval(timerInterval)
  timerInterval = null
  timerText.value = '00:00'
}

function startCountdown(seconds) {
  let remaining = seconds
  countdownPaused.value = false
  countdownText.value = fmt(remaining)
  clearInterval(countdownInterval)
  countdownInterval = setInterval(() => {
    if (countdownPaused.value) return
    remaining--
    countdownText.value = fmt(Math.max(0, remaining))
    if (remaining <= 0) {
      clearInterval(countdownInterval)
      countdownInterval = null
      submitAnswer()
    }
  }, 1000)
}

function stopCountdown() {
  clearInterval(countdownInterval)
  countdownInterval = null
}

function togglePause() {
  countdownPaused.value = !countdownPaused.value
}

/* ---------- 草稿 ---------- */
function draftKey() {
  return 'draft_' + prep.currentSessionId + '_' + questionIndex.value
}
function saveDraft() {
  if (answerText.value.trim()) ls.set(draftKey(), answerText.value)
}
function loadDraft() {
  return ls.get(draftKey(), '')
}
function clearDraft() {
  ls.remove(draftKey())
}
function clearAllDrafts(sessionId) {
  Object.keys(localStorage).forEach((k) => {
    if (k.startsWith('mockmate_draft_' + sessionId)) localStorage.removeItem(k)
  })
}

/* ---------- 题目展示 ---------- */
function showQuestion(q, index, audioUrl) {
  question.value = q
  questionIndex.value = index
  evaluation.value = null
  hintText.value = ''
  hintUsed.value = false
  selectedOption.value = ''
  answerText.value = q.options ? '' : loadDraft()
  phase.value = 'question'

  const timeLimit = ROUND_TIMES[prep.currentRound] || (isWritten.value ? WRITTEN_TIME : INTERVIEW_TIME)
  startCountdown(timeLimit)
}

function progressPct() {
  const total = totalQuestions.value
  return total > 0 ? Math.round((questionIndex.value / total) * 100) : 0
}

/* ---------- 开始面试 ---------- */
async function startInterview() {
  const resume = prep.resume.trim()
  const position = prep.position.trim()
  const company = prep.company.trim()
  if (!resume) { toast('请先填写或上传简历'); return }
  if (!position) { toast('请填写目标岗位'); return }
  if (!prep.resumeScore) { toast('请先对简历进行评分'); router.push('/'); return }
  if (prep.resumeScore.score < 70) { toast('简历评分低于 70 分无法开始面试，请优化简历'); return }

  phase.value = 'loading'
  try {
    const result = await api.post('/api/interview/start', {
      resume, position, company,
      profile: prep.profile || {},
      round: prep.selectedRound,
      custom_question_ids: prep.useCustom ? prep.selectedCustomIds : [],
      enable_tts: settings.ttsEnabled,
    })
    prep.currentSessionId = result.session_id
    prep.currentQuestionIndex = 0
    prep.interviewActive = true
    prep.currentRound = result.round
    prep.isWrittenRound = result.round === 'written'
    prep.totalQuestions = (prep.useCustom ? prep.selectedCustomIds.length : 0) || ROUND_TOTALS[result.round] || 8
    ls.set('active_session', result.session_id)
    startTimer()
    showQuestion(result.question, 0, result.audio_url)
    toast('面试已开始')
  } catch (e) {
    phase.value = 'idle'
    toast('启动面试失败: ' + e.message)
  }
}

/* ---------- 提交回答 ---------- */
async function submitAnswer() {
  if (!prep.interviewActive) return
  if (submitting.value) return
  stopCountdown()

  let answer
  if (question.value && question.value.options) {
    if (!selectedOption.value) { toast('请选择一个答案'); restartCountdown(); return }
    answer = selectedOption.value
  } else {
    answer = answerText.value.trim()
    if (!answer) { toast('请先输入回答'); restartCountdown(); return }
  }

  submitting.value = true
  const qIndex = questionIndex.value
  try {
    const result = await api.post('/api/interview/answer', {
      session_id: prep.currentSessionId,
      question_index: qIndex,
      answer,
      hint_used: hintUsed.value,
      enable_tts: settings.ttsEnabled,
    })
    prep.currentQuestionIndex = result.next_index
    clearDraft()
    evaluation.value = result.evaluation
    prep.lastEvaluation = result.evaluation
    nextQuestion.value = result.next_question || null
    nextIndex.value = result.next_index || 0
    nextAudio.value = result.audio_url || null
    phase.value = 'evaluation'
  } catch (e) {
    toast('评估失败: ' + e.message)
    restartCountdown()
  }
  submitting.value = false
}

function restartCountdown() {
  const timeLimit = ROUND_TIMES[prep.currentRound] || (isWritten.value ? WRITTEN_TIME : INTERVIEW_TIME)
  startCountdown(timeLimit)
}

/* ---------- 跳过 ---------- */
async function skipQuestion() {
  if (!prep.interviewActive) return
  stopCountdown()
  suspended.value.push({ question: question.value, index: questionIndex.value })
  submitting.value = true
  try {
    const result = await api.post('/api/interview/answer', {
      session_id: prep.currentSessionId,
      question_index: questionIndex.value,
      answer: '',
      enable_tts: settings.ttsEnabled,
    })
    prep.currentQuestionIndex = result.next_index
    clearDraft()
    showNextQuestion(result.next_question, result.next_index, result.audio_url)
  } catch (e) {
    toast('跳过失败: ' + e.message)
  }
  submitting.value = false
}

/* ---------- 提示 ---------- */
async function getHint() {
  if (hintUsed.value) return
  try {
    const result = await api.post('/api/interview/hint', {
      session_id: prep.currentSessionId,
      question_index: questionIndex.value,
    })
    hintText.value = result.hint
    hintUsed.value = true
  } catch (e) {
    toast('获取提示失败: ' + e.message)
  }
}

/* ---------- 收藏题目 ---------- */
async function saveFavorite() {
  try {
    await api.post('/api/favorites', {
      session_id: prep.currentSessionId || '',
      question: question.value.question || '',
      type: question.value.type || '',
      difficulty: question.value.difficulty || '',
      topic: question.value.topic || '',
      user_answer: answerText.value.trim() || '',
      overall_score: (evaluation.value && evaluation.value.overall_score) || 0,
      reference_answer: (evaluation.value && evaluation.value.reference_answer) || '',
    })
    toast('已收藏题目')
  } catch (e) {
    toast('收藏失败: ' + e.message)
  }
}

function printPage() {
  window.print()
}

/* ---------- 下一题 ---------- */
function showNextQuestion(nextQuestion, nextIndex, audioUrl) {
  if (nextQuestion && nextIndex < totalQuestions.value) {
    showQuestion(nextQuestion, nextIndex, audioUrl)
    return
  }
  if (suspended.value.length > 0) {
    const s = suspended.value.shift()
    prep.totalQuestions += 1
    prep.currentQuestionIndex = s.index
    showQuestion(s.question, s.index, null)
    toast('这是你之前跳过的第 ' + (s.index + 1) + ' 题')
    return
  }
  phase.value = 'finished'
}

/* ---------- 结束面试 ---------- */
async function endInterview() {
  if (!prep.currentSessionId) return
  if (!confirm('确定结束面试并生成报告吗？')) return
  stopCountdown()
  phase.value = 'loading'
  try {
    const result = await api.post('/api/interview/end', { session_id: prep.currentSessionId })
    reportResult.value = result
    phase.value = 'report'
    toast('面试已结束，报告已生成')
  } catch (e) {
    toast('结束面试失败: ' + e.message)
    phase.value = 'question'
  }
}

function cleanup() {
  stopTimer()
  stopCountdown()
  if (prep.currentSessionId) clearAllDrafts(prep.currentSessionId)
  prep.interviewActive = false
  prep.currentSessionId = null
  prep.currentQuestionIndex = 0
  prep.currentRound = null
  prep.isWrittenRound = false
  prep.totalQuestions = 0
  suspended.value = []
  ls.remove('active_session')
  phase.value = 'idle'
}

function finishAndHome() {
  cleanup()
  router.push('/')
}

/* ---------- 报告 ---------- */
function copyReport() {
  const text = document.getElementById('reportContent')?.innerText || ''
  navigator.clipboard.writeText(text)
    .then(() => toast('报告已复制到剪贴板'))
    .catch(() => toast('复制失败'))
}

function downloadReport() {
  const result = reportResult.value
  const r = result.report || {}
  const lines = []
  lines.push('==========================================')
  lines.push('  MockMate 面试报告')
  lines.push('==========================================')
  lines.push('')
  if (result.round) lines.push('轮次: ' + (ROUND_NAMES[result.round] || result.round))
  lines.push('总题数: ' + (result.history || []).length)
  lines.push('总评分数: ' + (r.overall_score || 0))
  if (r.score_breakdown) {
    const sc = r.score_breakdown
    lines.push('  技术: ' + (sc.technical || 0) + '  逻辑: ' + (sc.logic || 0) + '  深度: ' + (sc.depth || 0) + '  表达: ' + (sc.communication || 0))
  }
  lines.push('')
  if (r.final_verdict) { lines.push('【最终评价】'); lines.push(r.final_verdict); lines.push('') }
  if (r.skill_summary) { lines.push('【技能总结】'); lines.push(r.skill_summary); lines.push('') }
  if (r.strengths && r.strengths.length) { lines.push('【优势】'); r.strengths.forEach((s) => lines.push('  - ' + s)); lines.push('') }
  if (r.weaknesses && r.weaknesses.length) { lines.push('【待提升】'); r.weaknesses.forEach((w) => lines.push('  - ' + w)); lines.push('') }
  if (r.preparation_advice && r.preparation_advice.length) {
    lines.push('【复习建议】')
    r.preparation_advice.forEach((a, i) => lines.push('  ' + (i + 1) + '. ' + a))
    lines.push('')
  }
  lines.push('--- 问答回顾 ---')
  ;(result.history || []).forEach((h, i) => {
    lines.push('')
    lines.push('第' + (i + 1) + '题 (' + (h.type || '') + ') 得分: ' + ((h.score && h.score.overall_score) || 0))
    lines.push('问: ' + (h.q || ''))
    lines.push('答: ' + (h.a || ''))
  })
  const pos = (result.round ? ROUND_NAMES[result.round] : 'report').replace(/\s/g, '')
  const date = new Date().toISOString().slice(0, 10)
  downloadText('MockMate_' + pos + '_' + date + '.txt', lines.join('\n'))
  toast('报告已下载')
}

/* ---------- 语音输入（Web Speech） ---------- */
let recognition = null
let recording = ref(false)
function toggleVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) { toast('浏览器不支持语音输入'); return }
  if (!recognition) {
    recognition = new SR()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.onresult = (event) => {
      let transcript = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) transcript += event.results[i][0].transcript
      }
      if (transcript) {
        answerText.value += transcript
        saveDraft()
      }
    }
    recognition.onend = () => { recording.value = false }
    recognition.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') toast('语音识别错误: ' + e.error)
      recording.value = false
    }
  }
  if (!recording.value) {
    try { recognition.start() } catch { /* already started */ }
    recording.value = true
  } else {
    recognition.stop()
    recording.value = false
  }
}

/* ---------- 断点续面 ---------- */
async function resumeSession() {
  const sessionId = ls.get('active_session', '')
  if (!sessionId) return
  try {
    const session = await api.get('/api/interview/session/' + sessionId)
    if (session.round && session.current_question) {
      prep.currentSessionId = session.id
      prep.currentQuestionIndex = session.current_index
      prep.interviewActive = true
      prep.currentRound = session.round
      prep.isWrittenRound = session.round === 'written'
      prep.totalQuestions = (session.custom_questions || []).length || ROUND_TOTALS[session.round] || 8
      startTimer()
      showQuestion(session.current_question, session.current_index, null)
      toast('面试已恢复，继续作答')
    } else {
      ls.remove('active_session')
    }
  } catch {
    ls.remove('active_session')
  }
}

/* ---------- TTS ---------- */
function toggleTts() {
  ttsEnabled.value = !ttsEnabled.value
  settings.setTtsEnabled(ttsEnabled.value)
  toast('语音播报已' + (ttsEnabled.value ? '开启' : '关闭'))
}

onMounted(async () => {
  ttsEnabled.value = settings.ttsEnabled
  await resumeSession()
})

onBeforeUnmount(() => {
  stopTimer()
  stopCountdown()
  if (recognition) { try { recognition.stop() } catch { /* ignore */ } }
})
</script>

<template>
  <div>
    <!-- 子导航：开始面试 / 历史记录 -->
    <div v-if="phase === 'idle'" class="mock-subtabs">
      <button class="mock-subtab" :class="{ active: subView === 'start' }" @click="subView = 'start'">开始面试</button>
      <button class="mock-subtab" :class="{ active: subView === 'history' }" @click="subView = 'history'">历史记录</button>
    </div>

    <HistoryView v-if="subView === 'history' && phase === 'idle'" />

    <div v-else class="card">
    <!-- 顶部栏 -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px">
      <span style="font-size: 13px; color: var(--text2)">
        {{
          phase === 'report'
            ? '面试结束 · 共 ' + ((reportResult.history || []).length) + ' 题'
            : phase === 'finished'
              ? '全部完成'
              : prep.interviewActive
                ? '第 ' + (questionIndex + 1) + ' / ' + (totalQuestions || 0) + ' 题'
                : '第 0 题'
        }}
      </span>
      <span style="font-size: 12px; color: var(--accent2); background: var(--surface2); padding: 2px 10px; border-radius: 4px">{{ roundLabel }}</span>
      <span style="font-size: 13px; color: var(--text2)"><span>{{ timerText }}</span></span>
      <span
        style="font-size: 12px; cursor: pointer; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border); user-select: none"
        @click="toggleTts"
      >{{ ttsEnabled ? '🔊 语音开' : '🔇 语音关' }}</span>
      <button class="btn btn-danger btn-sm" :disabled="!prep.interviewActive" @click="endInterview">结束面试</button>
    </div>

    <!-- 轮次选择 -->
    <div v-if="phase === 'idle'" id="preInterviewConfig" style="margin-bottom: 16px">
      <h3 style="margin: 0 0 8px; font-size: 15px">面试轮次</h3>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px">
        <label class="round-option" :class="{ active: prep.selectedRound === 'written' }" @click="prep.selectedRound = 'written'">
          <input type="radio" value="written" :checked="prep.selectedRound === 'written'">
          <div><div class="round-name">笔试</div><div class="round-desc">理论基础 · 知识广度 · 客观题</div></div>
        </label>
        <label class="round-option" :class="{ active: prep.selectedRound === 'tech_1' }" @click="prep.selectedRound = 'tech_1'">
          <input type="radio" value="tech_1" :checked="prep.selectedRound === 'tech_1'">
          <div><div class="round-name">技术一面</div><div class="round-desc">编码实践 · 代码审查 · 工程判断</div></div>
        </label>
        <label class="round-option" :class="{ active: prep.selectedRound === 'tech_2' }" @click="prep.selectedRound = 'tech_2'">
          <input type="radio" value="tech_2" :checked="prep.selectedRound === 'tech_2'">
          <div><div class="round-name">技术二面</div><div class="round-desc">架构设计 · 技术深度 · 权衡分析</div></div>
        </label>
        <label class="round-option" :class="{ active: prep.selectedRound === 'comprehensive' }" @click="prep.selectedRound = 'comprehensive'">
          <input type="radio" value="comprehensive" :checked="prep.selectedRound === 'comprehensive'">
          <div><div class="round-name">综合面</div><div class="round-desc">领导力 · 成长思维 · 跨团队协作</div></div>
        </label>
      </div>
      <button class="btn btn-primary" style="margin-top: 12px; width: 100%" :disabled="!canStart" @click="startInterview">开始面试</button>
    </div>

    <!-- 加载中 -->
    <div v-if="phase === 'loading'" style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 300px">
      <div class="spinner" style="width: 48px; height: 48px; border-width: 5px"></div>
      <div style="margin-top: 20px; font-size: 16px; font-weight: 600; color: var(--text)">正在准备面试...</div>
      <div style="margin-top: 8px; font-size: 13px; color: var(--text2)">AI 正在根据你的简历生成题目</div>
    </div>

    <!-- 空状态 -->
    <div v-if="phase === 'idle'" class="interview-area">
      <div class="empty-state">
        请先完成准备<br>
        <span style="font-size: 13px">在「准备面试」标签页填写信息、生成岗位画像、完成简历评分</span>
      </div>
    </div>

    <!-- 题目视图 -->
    <template v-if="phase === 'question' && question">
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px">
        <div class="progress-wrap" style="margin-bottom: 0; flex: 1">
          <div class="progress-track"><div class="progress-fill" :style="{ width: progressPct() + '%' }"></div></div>
          <span class="progress-text">第 {{ questionIndex + 1 }} / {{ totalQuestions }} 题</span>
        </div>
        <span class="countdown" :class="{ paused: countdownPaused }">{{ countdownText }}</span>
      </div>

      <div class="question-box">
        <div class="q-label">{{ isWritten ? '笔试题目' : '面试官提问' }}</div>
        <div class="q-text markdown-body" v-html="md(question.question)"></div>
        <div v-if="question.difficulty" class="q-meta" style="display: flex; gap: 12px; flex-wrap: wrap">
          <span>{{ question.type || '' }}</span>
          <span>{{ diffLabel(question.difficulty) }}</span>
          <span>{{ question.topic || '' }}</span>
        </div>
      </div>

      <div v-if="!isWritten" style="margin-top: 8px; display: flex; gap: 8px">
        <button class="btn btn-sm btn-secondary" :disabled="hintUsed" @click="getHint">
          {{ hintUsed ? '💡 已查看提示' : '💡 提示' }}
        </button>
      </div>
      <div v-if="hintText" style="margin-top: 8px; padding: 10px; background: var(--surface2); border-radius: 8px; border-left: 3px solid var(--accent); font-size: 13px; line-height: 1.6" v-html="md(hintText)"></div>

      <!-- 选择题 -->
      <div v-if="question.options" class="form-group">
        <label>请选择答案</label>
        <label
          v-for="(val, key) in question.options"
          :key="key"
          class="written-option"
          style="display: flex; align-items: center; gap: 8px; padding: 10px 12px; margin: 4px 0; background: var(--surface2); border-radius: 8px; cursor: pointer; border: 2px solid var(--border)"
          :style="{ borderColor: selectedOption === key ? 'var(--accent)' : 'var(--border)' }"
        >
          <input type="radio" name="writtenAnswer" :value="key" style="width: 16px; height: 16px; accent-color: var(--accent)" v-model="selectedOption">
          <span style="font-size: 14px"><strong>{{ key }}.</strong> {{ val }}</span>
        </label>
      </div>

      <!-- 主观题 -->
      <div v-else class="form-group">
        <label>你的回答</label>
        <div style="display: flex; gap: 8px; align-items: flex-start">
          <textarea v-model="answerText" rows="5" placeholder="输入你的回答...（Ctrl+Enter 快捷提交）" style="flex: 1" @input="saveDraft" @keydown.ctrl.enter="submitAnswer"></textarea>
          <button class="record-btn-sm" :class="{ recording }" title="语音输入" @click="toggleVoice">🎤</button>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text2); margin-top: 4px">
          <span>Ctrl+Enter 提交 · 自动保存草稿</span>
          <span>{{ answerText.length }} 字</span>
        </div>
      </div>

      <div style="display: flex; gap: 10px">
        <button class="btn btn-primary" style="flex: 1" :disabled="submitting" @click="submitAnswer">提交回答</button>
        <button class="btn btn-secondary" style="flex: 0.3" @click="togglePause">{{ countdownPaused ? '继续' : '暂停' }}</button>
        <button class="btn btn-secondary" style="flex: 0.4" :disabled="submitting" @click="skipQuestion">跳过本题</button>
      </div>
    </template>

    <!-- 评估结果 -->
    <template v-if="phase === 'evaluation' && evaluation">
      <div class="feedback-box" :style="isWritten ? { borderLeftColor: evaluation.correct ? 'var(--green)' : 'var(--red)' } : {}">
        <!-- 笔试 -->
        <template v-if="isWritten">
          <div style="font-size: 24px; color: evaluation.correct ? 'var(--green)' : 'var(--red)'; margin-bottom: 8px">
            {{ evaluation.correct ? '✔' : '✘' }} <span style="font-size: 16px; font-weight: 600">{{ evaluation.correct ? '回答正确' : '回答错误' }}</span>
          </div>
          <div style="font-size: 13px; color: var(--text2); margin-bottom: 6px"><strong>正确答案：</strong><span v-html="md(evaluation.correct_answer || '')"></span></div>
          <div style="font-size: 13px; line-height: 1.6; padding: 10px; background: var(--surface); border-radius: 6px" class="markdown-body"><strong>解析：</strong><br><span v-html="md(evaluation.explanation || '')"></span></div>
        </template>
        <!-- 面试 -->
        <template v-else>
          <div style="font-size: 12px; color: var(--accent2); margin-bottom: 8px; font-weight: 600">
            {{ ({ tech_1: '工程能力评估', tech_2: '架构深度评估', comprehensive: '综合素质评估' })[prep.currentRound] || '面试评估' }}
          </div>
          <div class="score-row">
            <span class="score-tag">综合 <span class="val" :style="{ color: scoreColor(evaluation.overall_score) }">{{ evaluation.overall_score || 0 }}</span></span>
            <span class="score-tag">技术 <span class="val" :style="{ color: scoreColor(evaluation.technical_score) }">{{ evaluation.technical_score || 0 }}</span></span>
            <span class="score-tag">逻辑 <span class="val" :style="{ color: scoreColor(evaluation.logic_score) }">{{ evaluation.logic_score || 0 }}</span></span>
            <span class="score-tag">深度 <span class="val" :style="{ color: scoreColor(evaluation.depth_score) }">{{ evaluation.depth_score || 0 }}</span></span>
            <span class="score-tag">表达 <span class="val" :style="{ color: scoreColor(evaluation.communication_score) }">{{ evaluation.communication_score || 0 }}</span></span>
          </div>
          <div style="font-size: 13px; line-height: 1.6" class="markdown-body">
            <span v-html="md(evaluation.summary || '')"></span>
            <div v-if="evaluation.strengths && evaluation.strengths.length" style="margin-top: 8px"><strong>优点：</strong> {{ evaluation.strengths.join('、') }}</div>
            <div v-if="evaluation.improvements && evaluation.improvements.length" style="margin-top: 4px"><strong>改进建议：</strong> {{ evaluation.improvements.join('、') }}</div>
            <div v-if="evaluation.reference_answer" style="margin-top: 8px; padding: 8px; background: var(--surface); border-radius: 6px" class="markdown-body"><strong>参考回答：</strong><br><span v-html="md(evaluation.reference_answer)"></span></div>
          </div>
        </template>

        <FeedbackButtons
          v-if="evaluation._record_id"
          record-type="eval"
          :record-id="evaluation._record_id"
          :data="evaluation"
        />
      </div>

      <div style="margin-top: 12px; display: flex; gap: 10px">
        <button class="btn btn-primary" style="flex: 1" @click="showNextQuestion(nextQuestion, nextIndex, nextAudio)">下一题</button>
        <button v-if="!isWritten" class="btn btn-secondary btn-sm" @click="saveFavorite">收藏此题</button>
        <button class="btn btn-danger btn-sm" @click="endInterview">结束面试</button>
      </div>
    </template>

    <!-- 全部完成 -->
    <div v-if="phase === 'finished'" style="margin-top: 16px; display: flex; gap: 10px">
      <button class="btn btn-primary" style="flex: 1" @click="endInterview">生成报告并结束</button>
    </div>

    <!-- 报告 -->
    <div v-if="phase === 'report' && reportResult" id="reportContent" class="card" style="border-left: 3px solid var(--accent)">
      <h2 style="font-size: 18px; text-transform: none; color: var(--text)">面试报告</h2>
      <div v-if="reportResult.round" style="font-size: 12px; color: var(--accent2); margin-bottom: 8px">轮次：{{ ROUND_NAMES[reportResult.round] || reportResult.round }}</div>
      <div class="score-row" style="margin: 12px 0">
        <span class="score-tag">总评 <span class="val" :style="{ color: scoreColor(reportResult.report.overall_score) }">{{ reportResult.report.overall_score || 0 }}</span></span>
        <span class="score-tag">技术 <span class="val" :style="{ color: scoreColor(reportResult.report.score_breakdown?.technical) }">{{ reportResult.report.score_breakdown?.technical || 0 }}</span></span>
        <span class="score-tag">逻辑 <span class="val" :style="{ color: scoreColor(reportResult.report.score_breakdown?.logic) }">{{ reportResult.report.score_breakdown?.logic || 0 }}</span></span>
        <span class="score-tag">深度 <span class="val" :style="{ color: scoreColor(reportResult.report.score_breakdown?.depth) }">{{ reportResult.report.score_breakdown?.depth || 0 }}</span></span>
        <span class="score-tag">表达 <span class="val" :style="{ color: scoreColor(reportResult.report.score_breakdown?.communication) }">{{ reportResult.report.score_breakdown?.communication || 0 }}</span></span>
      </div>
      <div v-if="reportResult.report.final_verdict" class="markdown-body" style="font-size: 14px; line-height: 1.6; margin-bottom: 12px" v-html="md(reportResult.report.final_verdict)"></div>
      <div v-if="reportResult.report.skill_summary" class="markdown-body" style="font-size: 13px; color: var(--text2); margin-bottom: 12px" v-html="md(reportResult.report.skill_summary)"></div>
      <div v-if="reportResult.report.strengths && reportResult.report.strengths.length" style="margin-bottom: 8px">
        <strong style="color: var(--green)">优势</strong><br>
        <span style="font-size: 13px" class="markdown-body" v-html="reportResult.report.strengths.map((s) => md(s)).join('；')"></span>
      </div>
      <div v-if="reportResult.report.weaknesses && reportResult.report.weaknesses.length" style="margin-bottom: 8px">
        <strong style="color: var(--yellow)">待提升</strong><br>
        <span style="font-size: 13px" class="markdown-body" v-html="reportResult.report.weaknesses.map((w) => md(w)).join('；')"></span>
      </div>
      <div v-if="reportResult.report.preparation_advice && reportResult.report.preparation_advice.length" style="margin-bottom: 12px">
        <strong>复习建议</strong><br>
        <ul style="font-size: 13px; padding-left: 20px; margin-top: 4px">
          <li v-for="(a, i) in reportResult.report.preparation_advice" :key="i" class="markdown-body" v-html="md(a)"></li>
        </ul>
      </div>
      <div v-if="reportResult.report.recommended_positions && reportResult.report.recommended_positions.length" style="font-size: 13px; color: var(--text2)">
        推荐方向：{{ reportResult.report.recommended_positions.join('、') }}
      </div>

      <template v-if="(reportResult.history || []).length">
        <h2 style="font-size: 16px; text-transform: none; color: var(--text); margin-top: 20px">问答回顾</h2>
        <div v-for="(h, i) in reportResult.history" :key="i" style="background: var(--surface2); border-radius: 8px; padding: 12px; margin-top: 8px">
          <div style="font-size: 12px; color: var(--accent2); margin-bottom: 4px">第 {{ i + 1 }} 题 ({{ h.type || '' }})</div>
          <div style="font-size: 13px; margin-bottom: 6px" class="markdown-body"><strong>问：</strong><span v-html="md(h.q)"></span></div>
          <div style="font-size: 13px; color: var(--text2); margin-bottom: 4px" class="markdown-body"><strong>答：</strong><span v-html="md(h.a || '')"></span></div>
          <span class="score-tag" style="display: inline-block">得分 {{ (h.score && h.score.overall_score) || 0 }}</span>
        </div>
      </template>

      <div style="margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap">
        <button class="btn btn-primary" style="flex: 1" @click="finishAndHome">返回首页</button>
        <button class="btn btn-secondary" @click="copyReport">复制报告</button>
        <button class="btn btn-secondary" @click="downloadReport">下载报告</button>
        <button class="btn btn-secondary" @click="printPage">导出 PDF</button>
      </div>
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
