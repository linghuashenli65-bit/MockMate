<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'
import { diffLabel, esc, toast } from '../utils/helpers'

const list = ref([])
const loading = ref(false)
const editing = ref(false)
const editId = ref(null)
const page = ref(1)
const PAGE_SIZE = 10
const form = ref({
  question: '',
  type: '技术',
  difficulty: 'medium',
  topic: '',
  expected_points: '',
  tags: '',
})

async function loadQuestions() {
  loading.value = true
  page.value = 1
  try {
    const result = await api.get('/api/custom/questions')
    list.value = result.questions || []
  } catch (e) {
    toast('加载失败: ' + e.message)
  }
  loading.value = false
}

const totalPages = computed(() => Math.max(1, Math.ceil(list.value.length / PAGE_SIZE)))
const pageItems = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return list.value.slice(start, start + PAGE_SIZE)
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

function openEditor(qid) {
  editId.value = qid || null
  editing.value = true
  form.value = { question: '', type: '技术', difficulty: 'medium', topic: '', expected_points: '', tags: '' }
  if (qid) {
    api.get('/api/custom/questions/' + qid)
      .then((item) => {
        form.value = {
          question: item.question || '',
          type: item.type || '技术',
          difficulty: item.difficulty || 'medium',
          topic: item.topic || '',
          expected_points: (item.expected_points || []).join('\n'),
          tags: item.tags || '',
        }
      })
      .catch(() => toast('加载题目失败'))
  }
}

async function saveQuestion() {
  const question = form.value.question.trim()
  if (!question) {
    toast('请输入题目内容')
    return
  }
  const data = {
    question,
    type: form.value.type,
    difficulty: form.value.difficulty,
    topic: form.value.topic.trim(),
    expected_points: form.value.expected_points.split('\n').filter((s) => s.trim()),
    tags: form.value.tags.trim(),
  }
  try {
    if (editId.value) {
      await api.put('/api/custom/questions/' + editId.value, data)
      toast('题目已更新')
    } else {
      await api.post('/api/custom/questions', data)
      toast('题目已创建')
    }
    editing.value = false
    await loadQuestions()
  } catch (e) {
    toast('保存失败: ' + e.message)
  }
}

async function removeQuestion(qid) {
  if (!confirm('确定删除这道题目吗？')) return
  try {
    await api.delete('/api/custom/questions/' + qid)
    toast('题目已删除')
    await loadQuestions()
  } catch (e) {
    toast('删除失败: ' + e.message)
  }
}

onMounted(loadQuestions)
</script>

<template>
  <div>
    <div style="margin-bottom: 12px">
      <button class="btn btn-primary" @click="openEditor(null)">+ 添加新题目</button>
    </div>

    <!-- 编辑器 -->
    <div v-if="editing" class="card" style="border-left: 3px solid var(--accent)">
      <h2 style="font-size: 16px; text-transform: none; color: var(--text)">
        {{ editId ? '编辑题目' : '添加新题目' }}
      </h2>
      <div class="form-group">
        <label>题目内容</label>
        <textarea v-model="form.question" rows="4" placeholder="输入面试题目..."></textarea>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px">
        <div class="form-group">
          <label>类型</label>
          <select v-model="form.type">
            <option value="技术">技术</option>
            <option value="行为">行为</option>
            <option value="设计">设计</option>
            <option value="项目">项目</option>
          </select>
        </div>
        <div class="form-group">
          <label>难度</label>
          <select v-model="form.difficulty">
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </div>
        <div class="form-group">
          <label>主题</label>
          <input v-model="form.topic" type="text" placeholder="如：系统设计">
        </div>
      </div>
      <div class="form-group">
        <label>考察要点（每行一个）</label>
        <textarea v-model="form.expected_points" rows="3" placeholder="每行一个考察要点..."></textarea>
      </div>
      <div class="form-group">
        <label>标签（逗号分隔）</label>
        <input v-model="form.tags" type="text" placeholder="如：Redis, 缓存, 高并发">
      </div>
      <div style="display: flex; gap: 10px; margin-top: 12px">
        <button class="btn btn-primary" @click="saveQuestion">保存</button>
        <button class="btn btn-secondary" @click="editing = false">取消</button>
      </div>
    </div>

    <!-- 列表 -->
    <div v-else>
      <div v-if="loading" class="loading"><div class="spinner"></div></div>
      <div v-else-if="!list.length" class="empty-state">还没有自定义题目，点击上方按钮添加</div>
      <div
        v-for="item in pageItems"
        :key="item.id"
        class="history-item"
        style="margin-bottom: 8px"
      >
        <div class="hi-main">
          <div class="hi-info" style="flex: 1">
            <div class="hi-position">
              {{ item.type || '技术' }}
              <template v-if="diffLabel(item.difficulty)"> · {{ diffLabel(item.difficulty) }}</template>
              <template v-if="item.topic"> · {{ item.topic }}</template>
              <template v-if="item.tags"> · {{ item.tags }}</template>
            </div>
            <div class="hi-meta" style="margin-top: 4px; font-size: 13px; line-height: 1.5">
              {{ (item.question || '').length > 80 ? item.question.slice(0, 80) + '...' : item.question }}
            </div>
          </div>
          <div style="display: flex; gap: 6px">
            <button class="btn btn-secondary btn-sm" @click="openEditor(item.id)">编辑</button>
            <button class="btn btn-danger btn-sm" @click="removeQuestion(item.id)">删除</button>
          </div>
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
  </div>
</template>
