<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import Chart from 'chart.js/auto'
import { api } from '../services/api'
import { esc, formatDate, formatDateTime, md, ROUND_NAMES, scoreColor, toast } from '../utils/helpers'

const sessions = ref([])
const view = ref('list')
const detail = ref(null)
const loading = ref(false)

const trendBarRef = ref(null)
const trendLineRef = ref(null)
const dimRadarRef = ref(null)
const detailRadarRef = ref(null)

const charts = {}

const normalSessions = computed(() => sessions.value.filter((s) => s.type !== 'mock'))

/* ---------- 底部记录分页（每页 10 条） ---------- */
const HISTORY_PAGE_SIZE = 10
const historyPage = ref(1)
const historyTotalPages = computed(() => Math.max(1, Math.ceil(sessions.value.length / HISTORY_PAGE_SIZE)))
const pageSessions = computed(() => {
  const start = (historyPage.value - 1) * HISTORY_PAGE_SIZE
  return normalSessions.value.slice(start, start + HISTORY_PAGE_SIZE)
})
const pageNormals = computed(() => pageSessions.value.filter((s) => s.type !== 'mock'))

function goHistoryPage(p) {
  if (p < 1 || p > historyTotalPages.value) return
  historyPage.value = p
}

function historyPageList() {
  const total = historyTotalPages.value
  const cur = historyPage.value
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  const pages = [1]
  if (cur > 4) pages.push('...')
  for (let i = Math.max(2, cur - 2); i <= Math.min(total - 1, cur + 2); i++) pages.push(i)
  if (cur < total - 3) pages.push('...')
  pages.push(total)
  return pages
}

/* ---------- 统计 ---------- */
const statTotal = computed(() => normalSessions.value.length)
const statAvg = computed(() => {
  const scores = normalSessions.value.map((s) => s.overall_score || 0).filter((s) => s > 0)
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0
})
const statMax = computed(() => {
  const scores = normalSessions.value.map((s) => s.overall_score || 0).filter((s) => s > 0)
  return scores.length ? Math.max(...scores) : 0
})
const statTrend = computed(() => {
  const recent = sessions.value.slice(0, Math.min(3, sessions.value.length))
  if (recent.length < 2) return { cls: 'flat', text: '—' }
  const diff = (recent[0].overall_score || 0) - (recent[recent.length - 1].overall_score || 0)
  if (diff > 0.3) return { cls: 'up', text: '↑ ' + diff.toFixed(1) }
  if (diff < -0.3) return { cls: 'down', text: '↓ ' + Math.abs(diff).toFixed(1) }
  return { cls: 'flat', text: '→ 持平' }
})

/* ---------- 能力分析 ---------- */
const validSessions = computed(() => sessions.value.filter((s) => s.score_breakdown && Object.keys(s.score_breakdown).length > 0))
const avgDims = computed(() => {
  const keys = ['technical', 'logic', 'depth', 'communication']
  const sums = {}, counts = {}
  keys.forEach((k) => { sums[k] = 0; counts[k] = 0 })
  validSessions.value.forEach((s) => {
    const sb = s.score_breakdown || {}
    keys.forEach((k) => {
      const v = sb[k]
      if (v != null && !isNaN(v)) { sums[k] += v; counts[k]++ }
    })
  })
  const result = {}
  keys.forEach((k) => { result[k] = counts[k] ? +(sums[k] / counts[k]).toFixed(1) : 0 })
  return result
})
const weakList = computed(() => aggregate(sessions.value, 'weaknesses'))
const adviceList = computed(() => aggregate(sessions.value, 'preparation_advice'))

function aggregate(list, field) {
  const freq = {}
  list.forEach((s) => {
    const arr = s[field]
    if (!Array.isArray(arr)) return
    arr.forEach((w) => {
      const key = String(w).trim()
      if (key) freq[key] = (freq[key] || 0) + 1
    })
  })
  return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8)
}

const DIM_LABELS = { technical: '技术', logic: '逻辑', depth: '深度', communication: '表达' }

/* ---------- 图表 ---------- */
function destroyCharts() {
  Object.values(charts).forEach((c) => { try { c.destroy() } catch { /* ignore */ } })
  for (const k in charts) delete charts[k]
}

function renderTrendBar() {
  if (!trendBarRef.value) return
  const data = sessions.value.slice(0, 10).reverse()
  const labels = data.map((s) => formatDate(s.date))
  const scores = data.map((s) => s.overall_score || 0)
  const ids = data.map((s) => s.id)
  const bgColors = scores.map((v) => (v >= 7 ? 'rgba(0,184,148,0.7)' : v >= 4 ? 'rgba(253,203,110,0.7)' : 'rgba(225,112,85,0.7)'))
  charts.trendBar = new Chart(trendBarRef.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '面试评分', data: scores, backgroundColor: bgColors,
        borderColor: bgColors.map((c) => c.replace('0.7', '1')), borderWidth: 1, borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { min: 0, max: 10, ticks: { color: '#8b8fa8', stepSize: 2 } }, x: { ticks: { color: '#8b8fa8' } } },
      plugins: { legend: { display: false } },
      onClick: (e, elements) => {
        if (elements.length > 0 && ids[elements[0].index]) viewSession(ids[elements[0].index])
      },
    },
  })
}

function renderDimTrend() {
  if (!trendLineRef.value) return
  const data = sessions.value.slice(0, 20).reverse()
  const labels = data.map((s) => formatDate(s.date))
  const dims = [
    { key: 'technical', label: '技术', color: '#00b894' },
    { key: 'logic', label: '逻辑', color: '#6c5ce7' },
    { key: 'depth', label: '深度', color: '#fdcb6e' },
    { key: 'communication', label: '表达', color: '#e17055' },
  ]
  const datasets = dims.map((d) => ({
    label: d.label,
    data: data.map((s) => (s.score_breakdown || {})[d.key] ?? null),
    borderColor: d.color, backgroundColor: d.color + '22', fill: false,
    tension: 0.3, pointRadius: 3, pointHoverRadius: 5, spanGaps: false,
  }))
  datasets.push({
    label: '综合', data: data.map((s) => s.overall_score ?? null),
    borderColor: '#a29bfe', backgroundColor: '#a29bfe22', borderDash: [5, 3], borderWidth: 2,
    fill: false, tension: 0.3, pointRadius: 2, pointHoverRadius: 4, spanGaps: false,
  })
  charts.trendLine = new Chart(trendLineRef.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { min: 0, max: 10, ticks: { color: '#8b8fa8', stepSize: 2 } }, x: { ticks: { color: '#8b8fa8', maxTicksLimit: 10 } } },
      plugins: { legend: { position: 'bottom', labels: { color: '#8b8fa8', boxWidth: 12, padding: 12, font: { size: 11 } } } },
    },
  })
}

function renderDimRadar() {
  if (!dimRadarRef.value) return
  charts.dimRadar = new Chart(dimRadarRef.value, {
    type: 'radar',
    data: {
      labels: ['技术', '逻辑', '深度', '表达'],
      datasets: [{
        label: '平均分',
        data: [avgDims.value.technical, avgDims.value.logic, avgDims.value.depth, avgDims.value.communication],
        backgroundColor: 'rgba(108,92,231,0.2)', borderColor: '#6c5ce7', borderWidth: 2,
        pointBackgroundColor: ['#00b894', '#6c5ce7', '#fdcb6e', '#e17055'], pointRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      scales: { r: { min: 0, max: 10, ticks: { stepSize: 2, display: false }, grid: { color: '#2e3348' }, angleLines: { color: '#2e3348' }, pointLabels: { color: '#8b8fa8', font: { size: 12 } } } },
      plugins: { legend: { display: false } },
    },
  })
}

function renderDetailRadar() {
  if (!detailRadarRef.value || !detail.value || !detail.value.report) return
  const sc = detail.value.report.score_breakdown || {}
  charts.detailRadar = new Chart(detailRadarRef.value, {
    type: 'radar',
    data: {
      labels: ['技术', '逻辑', '深度', '表达', '综合'],
      datasets: [{
        label: '能力评估',
        data: [sc.technical || 0, sc.logic || 0, sc.depth || 0, sc.communication || 0, detail.value.report.overall_score || 0],
        backgroundColor: 'rgba(108,92,231,0.2)', borderColor: '#6c5ce7', borderWidth: 2,
        pointBackgroundColor: '#6c5ce7', pointRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      scales: { r: { min: 0, max: 10, ticks: { stepSize: 2, display: false }, grid: { color: '#2e3348' }, angleLines: { color: '#2e3348' }, pointLabels: { color: '#8b8fa8', font: { size: 12 } } } },
      plugins: { legend: { display: false } },
    },
  })
}

/* ---------- 数据加载 ---------- */
async function loadHistory() {
  loading.value = true
  view.value = 'list'
  historyPage.value = 1
  destroyCharts()
  try {
    const result = await api.get('/api/history')
    sessions.value = result.sessions || []
    loading.value = false
    if (sessions.value.length) {
      await nextTick()
      renderTrendBar()
      renderDimTrend()
      if (validSessions.value.length) renderDimRadar()
    }
  } catch (e) {
    loading.value = false
    toast('加载历史记录失败: ' + e.message)
  }
}

async function viewSession(sessionId) {
  loading.value = true
  destroyCharts()
  try {
    const s = await api.get('/api/interview/session/' + sessionId)
    detail.value = s
    view.value = 'detail'
    await nextTick()
    if (s.type !== 'mock' && s.report) renderDetailRadar()
  } catch (e) {
    toast('加载详情失败: ' + e.message)
    view.value = 'list'
  }
  loading.value = false
}

async function deleteSession(sessionId) {
  if (!confirm('确定删除这条面试记录？此操作不可恢复。')) return
  try {
    await api.delete('/api/history/' + sessionId)
    toast('已删除')
    await loadHistory()
  } catch (e) {
    toast('删除失败: ' + e.message)
  }
}

onMounted(loadHistory)
onBeforeUnmount(destroyCharts)

function printPage() {
  window.print()
}
</script>

<template>
  <div>
    <!-- ============ 列表视图 ============ -->
    <div v-if="view === 'list'">
      <div v-if="loading" class="loading">
        <div class="spinner"></div>
        <div style="margin-top: 8px">加载历史记录...</div>
      </div>
      <div v-else-if="!sessions.length" class="empty-state">
        暂无面试记录<br><span style="font-size: 13px">完成一次模拟面试后，记录会出现在这里</span>
      </div>

      <template v-else>
        <!-- 统计摘要 -->
        <div class="stats-grid">
          <div class="stat-card"><div class="stat-value">{{ statTotal }}</div><div class="stat-label">面试次数</div></div>
          <div class="stat-card"><div class="stat-value" :style="{ color: scoreColor(statAvg) }">{{ statAvg.toFixed(1) }}</div><div class="stat-label">平均分</div></div>
          <div class="stat-card"><div class="stat-value" :style="{ color: scoreColor(statMax) }">{{ statMax.toFixed(1) }}</div><div class="stat-label">最高分</div></div>
          <div class="stat-card"><div class="stat-value"><span class="stat-trend" :class="statTrend.cls">{{ statTrend.text }}</span></div><div class="stat-label">最近趋势</div></div>
        </div>

        <!-- 图表 -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px">
          <div class="chart-container"><h3>分数趋势</h3><div class="chart-wrap"><canvas ref="trendBarRef"></canvas></div></div>
          <div class="chart-container"><h3>各维度走势</h3><div class="chart-wrap"><canvas ref="trendLineRef"></canvas></div></div>
        </div>

        <!-- 能力分析 -->
        <div class="analysis-grid" style="display: grid; grid-template-columns: 1fr; gap: 16px; margin-bottom: 16px">
          <div class="card">
            <h2>各维度平均分</h2>
            <div style="max-width: 240px; margin: 12px auto 0">
              <canvas ref="dimRadarRef"></canvas>
            </div>
            <div class="score-row" style="margin-top: 12px; justify-content: center">
              <span v-for="(label, key) in DIM_LABELS" :key="key" class="score-tag">
                {{ label }} <span class="val" :style="{ color: scoreColor(avgDims[key]) }">{{ avgDims[key] }}</span>
              </span>
            </div>
          </div>
          <div class="card">
            <h2>薄弱点与建议</h2>
            <div style="margin-bottom: 12px">
              <div style="font-size: 13px; font-weight: 600; color: var(--yellow); margin-bottom: 6px">常见薄弱点</div>
              <div v-if="weakList.length" class="weakness-chips">
                <span v-for="[text, count] in weakList" :key="text" class="weakness-chip">
                  {{ text }}<em v-if="count > 1" class="chip-count">×{{ count }}</em>
                </span>
              </div>
              <p v-else style="font-size: 13px; color: var(--text2); margin: 0">暂无数据</p>
            </div>
            <div>
              <div style="font-size: 13px; font-weight: 600; color: var(--accent2); margin-bottom: 6px">复习建议汇总</div>
              <div v-if="adviceList.length" class="weakness-chips">
                <span v-for="[text, count] in adviceList" :key="text" class="weakness-chip">
                  {{ text }}<em v-if="count > 1" class="chip-count">×{{ count }}</em>
                </span>
              </div>
              <p v-else style="font-size: 13px; color: var(--text2); margin: 0">暂无数据</p>
            </div>
          </div>
        </div>

        <!-- 列表标题 -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
          <h3 style="font-size: 14px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin: 0">历史记录</h3>
          <button class="btn btn-secondary btn-sm" @click="printPage">导出 PDF</button>
        </div>

        <!-- 普通面试（当前页） -->
        <template v-if="pageNormals.length">
          <div
            v-for="s in pageNormals"
            :key="s.id"
            class="history-item"
          >
            <div class="hi-main">
              <div class="hi-info" style="cursor: pointer" @click="viewSession(s.id)">
                <div class="hi-position">{{ s.position }}</div>
                <div class="hi-meta">
                  <template v-if="s.company">{{ s.company }} · </template>
                  {{ ROUND_NAMES[s.round] || s.round || '' }}
                  <template v-if="ROUND_NAMES[s.round] || s.round"> · </template>
                  {{ formatDateTime(s.date) }} · {{ s.total_questions }} 题 · 评分 {{ s.overall_score }}
                </div>
              </div>
              <button class="btn btn-danger btn-sm" style="margin-left: 8px; flex-shrink: 0" @click="deleteSession(s.id)">删除</button>
            </div>
          </div>
        </template>

        <!-- 记录分页 -->
        <div v-if="historyTotalPages > 1" class="fav-pagination" style="margin-top: 12px">
          <button class="page-btn" :disabled="historyPage <= 1" @click="goHistoryPage(historyPage - 1)">‹</button>
          <template v-for="(p, i) in historyPageList()" :key="i">
            <span v-if="p === '...'" class="page-dots">…</span>
            <button v-else class="page-btn" :class="{ active: p === historyPage }" @click="goHistoryPage(p)">{{ p }}</button>
          </template>
          <button class="page-btn" :disabled="historyPage >= historyTotalPages" @click="goHistoryPage(historyPage + 1)">›</button>
        </div>
      </template>
    </div>

    <!-- ============ 详情视图 ============ -->
    <div v-else-if="view === 'detail' && detail">
      <div style="margin-bottom: 8px; display: flex; justify-content: space-between">
        <button class="btn btn-secondary btn-sm" @click="loadHistory">← 返回列表</button>
        <button v-if="detail.type !== 'mock'" class="btn btn-secondary btn-sm" @click="printPage">导出 PDF</button>
      </div>

      <!-- 普通面试详情 -->
      <div class="card">
        <h2 style="text-transform: none; color: var(--text)">{{ detail.position || '未知岗位' }}</h2>
        <div style="font-size: 13px; color: var(--text2); margin-bottom: 12px">
          <template v-if="detail.company">{{ detail.company }} · </template>
          {{ formatDateTime(detail.date) }}
          <template v-if="detail.round"> · <span style="color: var(--accent2)">{{ ROUND_NAMES[detail.round] || detail.round }}</span></template>
        </div>

        <template v-if="detail.report">
          <div class="score-row">
            <span class="score-tag">总评 <span class="val" :style="{ color: scoreColor(detail.report.overall_score) }">{{ detail.report.overall_score || 0 }}</span></span>
            <span class="score-tag">技术 <span class="val" :style="{ color: scoreColor(detail.report.score_breakdown?.technical) }">{{ detail.report.score_breakdown?.technical || 0 }}</span></span>
            <span class="score-tag">逻辑 <span class="val" :style="{ color: scoreColor(detail.report.score_breakdown?.logic) }">{{ detail.report.score_breakdown?.logic || 0 }}</span></span>
            <span class="score-tag">深度 <span class="val" :style="{ color: scoreColor(detail.report.score_breakdown?.depth) }">{{ detail.report.score_breakdown?.depth || 0 }}</span></span>
            <span class="score-tag">表达 <span class="val" :style="{ color: scoreColor(detail.report.score_breakdown?.communication) }">{{ detail.report.score_breakdown?.communication || 0 }}</span></span>
          </div>

          <div class="chart-container" style="margin-top: 12px">
            <h3>五维能力雷达</h3>
            <div class="chart-wrap" style="max-width: 300px; margin: 0 auto"><canvas ref="detailRadarRef"></canvas></div>
          </div>

          <div v-if="detail.report.final_verdict" class="markdown-body" style="font-size: 13px; margin-top: 8px; line-height: 1.6" v-html="md(detail.report.final_verdict)"></div>
          <div v-if="detail.report.skill_summary" class="markdown-body" style="font-size: 12px; color: var(--text2); margin-top: 4px" v-html="md(detail.report.skill_summary)"></div>

          <div v-if="detail.report.strengths && detail.report.strengths.length" style="margin-top: 8px">
            <strong style="color: var(--green)">优势</strong><br>
            <span style="font-size: 13px" class="markdown-body" v-html="detail.report.strengths.map((s) => md(s)).join('；')"></span>
          </div>
          <div v-if="detail.report.weaknesses && detail.report.weaknesses.length" style="margin-top: 4px">
            <strong style="color: var(--yellow)">待提升</strong><br>
            <span style="font-size: 13px" class="markdown-body" v-html="detail.report.weaknesses.map((w) => md(w)).join('；')"></span>
          </div>
          <div v-if="detail.report.preparation_advice && detail.report.preparation_advice.length" style="margin-top: 8px">
            <strong>复习建议</strong><br>
            <ul style="font-size: 13px; padding-left: 20px; margin-top: 4px">
              <li v-for="(a, i) in detail.report.preparation_advice" :key="i" class="markdown-body" v-html="md(a)"></li>
            </ul>
          </div>
        </template>

        <template v-if="(detail.history || []).length">
          <div
            v-for="(h, i) in (detail.history || [])"
            :key="i"
            style="background: var(--surface2); border-radius: 8px; padding: 12px; margin-top: 8px"
          >
            <div style="font-size: 12px; color: var(--accent2)">第 {{ i + 1 }} 题 · 得分 {{ (h.score && h.score.overall_score) || 0 }}</div>
            <div style="font-size: 13px; margin: 4px 0" class="markdown-body" v-html="md('**问：**' + esc(h.q || ''))"></div>
            <div style="font-size: 13px; color: var(--text2)" class="markdown-body" v-html="md('**答：**' + esc((h.a || '').slice(0, 200)) + ((h.a || '').length > 200 ? '...' : ''))"></div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.weakness-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.weakness-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
  color: var(--text);
  line-height: 1.4;
}
.weakness-chip .chip-count {
  font-style: normal;
  font-size: 11px;
  color: var(--text2);
  background: var(--surface);
  border-radius: 10px;
  padding: 1px 7px;
}
</style>
