<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'
import { esc, formatDateTime, toast } from '../utils/helpers'

const sessions = ref([])
const view = ref('list')
const detail = ref(null)
const loading = ref(false)

const PAGE_SIZE = 10
const page = ref(1)

/* ---------- 列表统计 ---------- */
const statTotal = computed(() => sessions.value.length)
const statAvgScore = computed(() => {
  const scores = sessions.value.map((s) => s.overall_score).filter((v) => v != null && v !== 0)
  return scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null
})
const statAvgQuestions = computed(() => {
  return sessions.value.length
    ? Math.round(sessions.value.reduce((a, s) => a + (s.total_questions || 0), 0) / sessions.value.length)
    : 0
})
const statAvgCoverage = computed(() => {
  const covs = sessions.value.map((s) => {
    const c = s.coverage || {}
    return c.total ? c.covered / c.total : null
  }).filter((v) => v != null)
  return covs.length ? Math.round(covs.reduce((a, b) => a + b, 0) / covs.length * 100) : null
})

const totalPages = computed(() => Math.max(1, Math.ceil(sessions.value.length / PAGE_SIZE)))
const pageItems = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return sessions.value.slice(start, start + PAGE_SIZE)
})
function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
}
function pageList() {
  const total = totalPages.value
  const cur = page.value
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = [1]
  if (cur > 4) pages.push('...')
  for (let i = Math.max(2, cur - 2); i <= Math.min(total - 1, cur + 2); i++) pages.push(i)
  if (cur < total - 3) pages.push('...')
  pages.push(total)
  return pages
}

async function loadHistory() {
  loading.value = true
  view.value = 'list'
  page.value = 1
  try {
    const result = await api.mockGetHistory()
    sessions.value = result.sessions || []
  } catch (e) {
    toast('加载拟真面试历史失败: ' + e.message)
  }
  loading.value = false
}

async function openDetail(sessionId) {
  loading.value = true
  try {
    const s = await api.get('/api/interview/session/' + sessionId)
    detail.value = s
    view.value = 'detail'
  } catch (e) {
    toast('加载详情失败: ' + e.message)
  }
  loading.value = false
}

async function removeSession(sessionId) {
  if (!confirm('确定删除这条拟真面试记录？此操作不可恢复。')) return
  try {
    await api.delete('/api/history/' + sessionId)
    toast('已删除')
    await loadHistory()
  } catch (e) {
    toast('删除失败: ' + e.message)
  }
}

/* ---------- 详情计算 ---------- */
const detailReport = computed(() => detail.value?.report || {})
const detailHistory = computed(() => (detail.value?.history || []).filter((h) => h && (h.type === 'question' || h.type === 'answer')))
const qaPairs = computed(() => {
  const pairs = []
  let cur = null
  detailHistory.value.forEach((entry) => {
    if (entry.type === 'question') {
      if (cur) pairs.push(cur)
      cur = { question: entry, answer: null }
    } else if (entry.type === 'answer' && cur) {
      cur.answer = entry
      pairs.push(cur)
      cur = null
    }
  })
  if (cur) pairs.push(cur)
  return pairs
})
const detailScore = computed(() => {
  if (detailReport.value.overall_score != null) return detailReport.value.overall_score
  const scores = qaPairs.value.filter((p) => p.answer && p.answer.score != null).map((p) => p.answer.score)
  return scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null
})
const byInterviewer = computed(() => {
  const map = {}
  qaPairs.value.forEach((p) => {
    const name = p.question.interviewer_name || '未知面试官'
    if (!map[name]) map[name] = { questions: [], scores: [] }
    map[name].questions.push(p)
    if (p.answer && p.answer.score != null) map[name].scores.push(p.answer.score)
  })
  return Object.entries(map).map(([name, data]) => ({
    name,
    count: data.questions.length,
    avg: data.scores.length ? Math.round(data.scores.reduce((a, b) => a + b, 0) / data.scores.length) : null,
  }))
})
const coverage = computed(() => detailReport.value.coverage || {})

function mockScoreColor(score) {
  if (score == null) return 'var(--text2)'
  if (score >= 85) return 'var(--green)'
  if (score >= 60) return 'var(--yellow)'
  return 'var(--red)'
}

onMounted(loadHistory)
</script>

<template>
  <div>
    <!-- ============ 列表 ============ -->
    <template v-if="view === 'list'">
      <div v-if="loading" class="loading"><div class="spinner"></div><div style="margin-top: 8px">加载拟真面试历史...</div></div>
      <div v-else-if="!sessions.length" class="empty-state">
        暂无拟真面试记录<br><span style="font-size: 13px">完成一次拟真面试后，报告（含逐题评分）会保存在这里</span>
      </div>

      <template v-else>
        <div class="stats-grid">
          <div class="stat-card"><div class="stat-value">{{ statTotal }}</div><div class="stat-label">总场次</div></div>
          <div class="stat-card"><div class="stat-value" :style="{ color: mockScoreColor(statAvgScore) }">{{ statAvgScore ?? '—' }}</div><div class="stat-label">平均分</div></div>
          <div class="stat-card"><div class="stat-value">{{ statAvgQuestions }}</div><div class="stat-label">平均题数</div></div>
          <div class="stat-card"><div class="stat-value" :style="{ color: statAvgCoverage != null && statAvgCoverage >= 60 ? 'var(--green)' : 'var(--yellow)' }">{{ statAvgCoverage != null ? statAvgCoverage + '%' : '—' }}</div><div class="stat-label">平均覆盖度</div></div>
        </div>

        <div v-for="s in pageItems" :key="s.id" class="history-item is-mock" style="cursor: pointer" @click="openDetail(s.id)">
          <div class="hi-main">
            <div class="hi-info">
              <div class="hi-position"><span class="mock-badge">拟真</span> {{ s.position || '未知岗位' }}</div>
              <div class="hi-meta">
                {{ formatDateTime(s.date) }} · {{ s.total_questions || 0 }} 题
                <template v-if="s.overall_score != null && s.overall_score !== 0"> · 得分 <strong :style="{ color: mockScoreColor(s.overall_score) }">{{ s.overall_score }}</strong></template>
                <template v-if="s.coverage && s.coverage.total"> · 覆盖 {{ s.coverage.covered }}/{{ s.coverage.total }}</template>
              </div>
            </div>
            <button class="btn btn-danger btn-sm" style="flex-shrink: 0" @click.stop="removeSession(s.id)">删除</button>
          </div>
        </div>

        <div v-if="totalPages > 1" class="fav-pagination" style="margin-top: 12px">
          <button class="page-btn" :disabled="page <= 1" @click="goPage(page - 1)">‹</button>
          <template v-for="(p, i) in pageList()" :key="i">
            <span v-if="p === '...'" class="page-dots">…</span>
            <button v-else class="page-btn" :class="{ active: p === page }" @click="goPage(p)">{{ p }}</button>
          </template>
          <button class="page-btn" :disabled="page >= totalPages" @click="goPage(page + 1)">›</button>
        </div>
      </template>
    </template>

    <!-- ============ 详情 ============ -->
    <template v-else-if="view === 'detail' && detail">
      <div style="margin-bottom: 8px">
        <button class="btn btn-secondary btn-sm" @click="loadHistory">← 返回列表</button>
      </div>

      <!-- 顶部摘要 -->
      <div class="card" style="border-left: 3px solid var(--accent)">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px">
          <div>
            <h2 style="font-size: 18px; text-transform: none; color: var(--text); margin: 0">{{ detail.position || '拟真面试' }}</h2>
            <div style="font-size: 13px; color: var(--text2); margin-top: 6px">
              <template v-if="detail.company">{{ detail.company }} · </template>
              {{ formatDateTime(detail.date) }} · <span style="color: var(--accent2)">拟真面试</span>
              · 共 {{ qaPairs.length }} 题
            </div>
          </div>
          <div v-if="detailScore != null" style="text-align: right">
            <div style="font-size: 11px; color: var(--text2)">综合评分</div>
            <div style="font-size: 40px; font-weight: 700; line-height: 1.1" :style="{ color: mockScoreColor(detailScore) }">{{ detailScore }}</div>
          </div>
        </div>
        <div v-if="coverage.total" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center">
          <span class="score-tag">考察覆盖 <strong>{{ coverage.covered }}/{{ coverage.total }}</strong></span>
          <template v-if="coverage.remaining && coverage.remaining.length">
            <span style="font-size: 12px; color: var(--text2)">未覆盖：{{ coverage.remaining.join('、') }}</span>
          </template>
        </div>
      </div>

      <!-- 面试官维度 -->
      <div v-if="byInterviewer.length" class="card">
        <h2 style="font-size: 16px; text-transform: none; color: var(--text)">面试官维度</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-top: 10px">
          <div v-for="iv in byInterviewer" :key="iv.name" class="mock-iv-card" style="margin: 0">
            <div class="mock-iv-avatar">{{ (iv.name || '?').charAt(0) }}</div>
            <div class="mock-iv-info">
              <div class="mock-iv-name">{{ iv.name }}</div>
              <div class="mock-iv-role">提问 {{ iv.count }} 题
                <span v-if="iv.avg != null" :style="{ color: mockScoreColor(iv.avg), fontWeight: 600 }"> · 均分 {{ iv.avg }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 问答回顾 -->
      <template v-if="qaPairs.length">
        <h2 style="font-size: 16px; text-transform: none; color: var(--text); margin-top: 20px">问答回顾</h2>
        <div v-for="(p, idx) in qaPairs" :key="idx" class="card" style="margin-top: 10px; padding: 14px">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px">
            <span style="font-size: 12px; color: var(--accent2)">第 {{ idx + 1 }} 题 · {{ p.question.interviewer_name || '' }}</span>
            <span class="score-tag">
              得分 <strong :style="{ color: mockScoreColor(p.answer && p.answer.score) }">{{ p.answer && p.answer.score != null ? p.answer.score : '未评分' }}</strong>
            </span>
          </div>
          <div style="font-size: 14px; margin-bottom: 8px; padding: 8px 10px; background: var(--surface); border-radius: 6px"><strong>问：</strong>{{ esc(p.question.question || '') }}</div>
          <div v-if="p.answer && p.answer.answer" style="font-size: 13px; color: var(--text2); margin-bottom: 6px; padding: 8px 10px; background: var(--surface2); border-radius: 6px"><strong>答：</strong>{{ esc(p.answer.answer) }}</div>
          <div v-else style="font-size: 13px; color: var(--text2); margin-bottom: 6px; font-style: italic">（未回答）</div>
          <div v-if="p.answer && p.answer.evaluation" style="font-size: 12px; color: var(--text2); padding: 8px 10px; background: var(--surface); border-radius: 6px; border-left: 2px solid var(--accent2)"><strong>评语：</strong>{{ esc(p.answer.evaluation) }}</div>
        </div>
      </template>
    </template>
  </div>
</template>
