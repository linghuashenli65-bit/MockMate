<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../services/api'
import { diffLabel, esc, formatDateTime, md, scoreColor, toast } from '../utils/helpers'

const items = ref([])
const page = ref(1)
const totalPages = ref(0)
const search = ref('')
const loading = ref(false)
const expanded = ref(new Set())

const PAGE_SIZE = 10
let requestId = 0
let searchTimer = null

async function loadFavorites(p) {
  const id = ++requestId
  loading.value = true
  page.value = p || 1
  try {
    const params = new URLSearchParams({ page: page.value, page_size: PAGE_SIZE, search: search.value })
    const result = await api.get('/api/favorites?' + params.toString())
    if (id !== requestId) return
    items.value = result.items || []
    totalPages.value = (result.pagination || {}).total_pages || 0
  } catch (e) {
    if (id !== requestId) return
    toast('加载失败: ' + e.message)
  } finally {
    if (id === requestId) loading.value = false
  }
}

function onSearch(e) {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    search.value = e.target.value.trim()
    loadFavorites(1)
  }, 300)
}

function toggleExpand(itemId) {
  const next = new Set(expanded.value)
  if (next.has(itemId)) next.delete(itemId)
  else next.add(itemId)
  expanded.value = next
}

async function removeFavorite(favId) {
  if (!confirm('确定删除这条收藏吗？')) return
  try {
    await api.delete('/api/favorites/' + favId)
    toast('已取消收藏')
    await loadFavorites(page.value)
  } catch (e) {
    toast('删除失败: ' + e.message)
  }
}

function pageList() {
  const total = totalPages.value
  const cur = page.value
  const pages = []
  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 4) pages.push('...')
    const start = Math.max(2, cur - 2)
    const end = Math.min(total - 1, cur + 2)
    for (let i = start; i <= end; i++) pages.push(i)
    if (cur < total - 3) pages.push('...')
    pages.push(total)
  }
  return pages
}

onMounted(() => loadFavorites(1))
</script>

<template>
  <div>
    <div class="fav-search-bar">
      <span class="fav-search-icon">🔍</span>
      <input type="text" placeholder="搜索题目、话题、类型…" autocomplete="off" @input="onSearch">
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div></div>
    <div v-else-if="!items.length" class="empty-state">
      {{ search ? '没有找到匹配的收藏题目' : '还没有收藏的题目' }}
    </div>

    <div v-for="item in items" :key="item.id" class="fav-item" :class="{ expanded: expanded.has(item.id) }">
      <div class="fav-main">
        <div class="fav-question markdown-body" v-html="md(item.question)"></div>
        <div class="fav-info">
          <div class="fav-meta">
            <span v-if="item.type" class="fav-tag">{{ item.type }}</span>
            <template v-if="diffLabel(item.difficulty)"><span class="fav-tag">{{ diffLabel(item.difficulty) }}</span></template>
            <span v-if="item.topic" class="fav-tag">{{ item.topic }}</span>
            <span class="fav-score" :style="{ color: scoreColor(item.overall_score) }">{{ item.overall_score }}分</span>
          </div>
          <div class="fav-actions">
            <span class="fav-time">{{ formatDateTime(item.saved_at) }}</span>
            <button class="expand-btn" @click="toggleExpand(item.id)">
              {{ expanded.has(item.id) ? '收起' : '展开回答' }}
            </button>
            <button class="btn btn-danger btn-sm" @click="removeFavorite(item.id)">删除</button>
          </div>
        </div>
      </div>
      <div v-show="expanded.has(item.id)" class="fav-body">
        <div v-if="item.user_answer" class="fav-answer markdown-body" v-html="md('**我的回答：**<br>' + esc(item.user_answer))"></div>
        <div v-if="item.reference_answer" class="fav-ref markdown-body" v-html="md('**参考回答：**<br>' + esc(item.reference_answer))"></div>
      </div>
    </div>

    <div v-if="totalPages > 1" class="fav-pagination">
      <button class="page-btn" :disabled="page <= 1" @click="loadFavorites(page - 1)">‹</button>
      <template v-for="(p, i) in pageList()" :key="i">
        <span v-if="p === '...'" class="page-dots">…</span>
        <button v-else class="page-btn" :class="{ active: p === page }" @click="loadFavorites(p)">{{ p }}</button>
      </template>
      <button class="page-btn" :disabled="page >= totalPages" @click="loadFavorites(page + 1)">›</button>
    </div>
  </div>
</template>
