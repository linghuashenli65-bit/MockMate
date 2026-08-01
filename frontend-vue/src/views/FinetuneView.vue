<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'
import { esc, toast } from '../utils/helpers'

const stats = ref({
  total_raw: 0,
  evaluations: 0,
  scores: 0,
  reviewed: 0,
  quality_good: 0,
  quality_bad: 0,
})
const records = ref([])
const filterType = ref('')
const filterQuality = ref('')
const filterSource = ref('raw')
const page = ref(1)
const PAGE_SIZE = 10

async function loadStats() {
  try {
    stats.value = await api.get('/api/training/stats')
  } catch (e) {
    toast('加载统计数据失败')
  }
}

async function loadRecords() {
  page.value = 1
  try {
    const resp = await api.post('/api/training/data', {
      record_type: filterType.value || null,
      quality: filterQuality.value === '__pending__' ? null : (filterQuality.value || null),
      source: filterSource.value,
    })
    records.value = resp.records || []
  } catch (e) {
    records.value = []
    toast('加载训练数据失败')
  }
}

function refresh() {
  loadStats()
  loadRecords()
}

const totalPages = computed(() => Math.max(1, Math.ceil(records.value.length / PAGE_SIZE)))
const pageItems = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return records.value.slice(start, start + PAGE_SIZE)
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

onMounted(refresh)
</script>

<template>
  <div>
    <div class="card">
      <h2>训练数据</h2>
      <div id="trainingStats" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 12px 0">
        <div class="stat-box"><div class="stat-num">{{ stats.total_raw || 0 }}</div><div class="stat-label">总采集</div></div>
        <div class="stat-box"><div class="stat-num">{{ stats.evaluations || 0 }}</div><div class="stat-label">面试评分</div></div>
        <div class="stat-box"><div class="stat-num">{{ stats.scores || 0 }}</div><div class="stat-label">简历评分</div></div>
        <div class="stat-box"><div class="stat-num">{{ stats.reviewed || 0 }}</div><div class="stat-label">已修正</div></div>
        <div class="stat-box" style="border-left-color: var(--green)"><div class="stat-num">{{ stats.quality_good || 0 }}</div><div class="stat-label">👍 可用</div></div>
        <div class="stat-box" style="border-left-color: var(--red)"><div class="stat-num">{{ stats.quality_bad || 0 }}</div><div class="stat-label">👎 待修</div></div>
      </div>
    </div>

    <div class="card">
      <h2>数据浏览</h2>
      <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap">
        <select v-model="filterType" class="form-input" style="width: auto; min-width: 120px" @change="loadRecords">
          <option value="">全部类型</option>
          <option value="eval">面试评分</option>
          <option value="score">简历评分</option>
        </select>
        <select v-model="filterQuality" class="form-input" style="width: auto; min-width: 120px" @change="loadRecords">
          <option value="">全部状态</option>
          <option value="good">👍 已采纳</option>
          <option value="bad">👎 已点踩</option>
          <option value="__pending__">⏳ 待反馈</option>
        </select>
        <select v-model="filterSource" class="form-input" style="width: auto; min-width: 120px" @change="loadRecords">
          <option value="raw">原始数据</option>
          <option value="reviewed">已修正</option>
        </select>
        <button class="btn btn-primary btn-sm" @click="refresh">刷新</button>
      </div>
      <div v-if="!records.length" class="empty-state">暂无数据</div>
      <div
        v-for="r in pageItems"
        :key="r.id"
        class="feedback-item"
        style="padding: 10px; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px"
      >
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px">
          <span style="font-size: 12px; color: var(--accent2); font-weight: 600">{{ r.type === 'eval' ? '面试评分' : '简历评分' }}</span>
          <span style="font-size: 12px; color: var(--text2)">
            {{ r.quality === 'good' ? '👍' : (r.quality === 'bad' ? '👎' : '⏳') }}
            {{ (r.timestamp || '').slice(0, 16).replace('T', ' ') }}
            <span v-if="r.reviewed" style="font-size: 11px; color: var(--accent2); margin-left: 6px">[已修正]</span>
          </span>
        </div>
        <div style="font-size: 13px; margin-bottom: 4px"><strong>题目：</strong>{{ esc(r.type === 'eval' ? (r.question || '').slice(0, 60) : '简历评分') }}</div>
        <div v-if="r.type === 'eval' && r.answer" style="font-size: 12px; color: var(--text2); margin-bottom: 4px">
          <strong>回答：</strong>{{ esc(r.answer.slice(0, 80)) }}
        </div>
        <div style="font-size: 12px; color: var(--text2)">
          {{ r.type === 'eval' ? '综合评分：' + ((r.result && r.result.overall_score) ?? '-') : '匹配度：' + ((r.result && r.result.score) ?? '-') + '/100' }}
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
    </div>

    <div class="card" style="opacity: 0.6">
      <h2>LoRA 训练 <span style="font-size: 12px; color: var(--text2); font-weight: 400">（开发中）</span></h2>
      <p style="font-size: 13px; color: var(--text2)">将在后续版本中支持：选择基座模型、配置 LoRA 参数、启动训练、实时 loss 显示</p>
    </div>
    <div class="card" style="opacity: 0.6">
      <h2>Adapter 管理 <span style="font-size: 12px; color: var(--text2); font-weight: 400">（开发中）</span></h2>
      <p style="font-size: 13px; color: var(--text2)">将在后续版本中支持：加载/卸载 adapter、版本管理、训练数据对比</p>
    </div>
  </div>
</template>
