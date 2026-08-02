<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePrepStore } from '../stores/prep'
import { api } from '../services/api'
import { esc, md, toast } from '../utils/helpers'
import FeedbackButtons from '../components/FeedbackButtons.vue'

const router = useRouter()
const prep = usePrepStore()

const fileName = ref('')
const researching = ref(false)
const scoring = ref(false)
const customOptions = ref([])

const canStart = computed(() =>
  prep.resume.trim() && prep.profile && prep.resumeScore && prep.resumeScore.score >= 70
)

onMounted(async () => {
  if (prep.useCustom) await loadCustomQuestions()
})

/* ---------- 简历上传 ---------- */
async function handleResumeUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  fileName.value = file.name
  const formData = new FormData()
  formData.append('file', file)
  try {
    const result = await api.upload('/api/resume/parse', formData)
    prep.setResume(result.text)
    prep.clearScore()
    toast('简历已识别')
  } catch (err) {
    toast('简历识别失败: ' + err.message)
  }
}

/* ---------- 岗位画像 ---------- */
async function doResearch(refresh) {
  const pos = prep.position.trim()
  if (!pos) {
    toast('请先输入目标岗位')
    return
  }
  researching.value = true
  prep.profile = null // 清掉旧画像，避免分析中显示过期内容
  try {
    const data = await api.post('/api/research', { position: pos, company: prep.company.trim(), refresh })
    prep.profile = data
    toast(refresh ? '重新分析完成' : '岗位分析完成')
  } catch (err) {
    toast('分析失败: ' + err.message)
  } finally {
    researching.value = false
  }
}

/* ---------- 简历评分 ---------- */
async function scoreResume() {
  const resume = prep.resume.trim()
  const profile = prep.profile
  if (!resume) { toast('请先填写或上传简历'); return }
  if (!profile || !Object.keys(profile).length) { toast('请先生成岗位画像'); return }
  scoring.value = true
  try {
    const result = await api.post('/api/resume/score', { resume, profile })
    prep.resumeScore = result
    if (result.score >= 70) toast('简历评分 ' + result.score + ' 分，可以开始面试')
    else toast('简历评分 ' + result.score + ' 分，建议优化后再面试')
  } catch (err) {
    toast('评分失败: ' + err.message)
  }
  scoring.value = false
}

const scoreColor = computed(() => {
  const s = Math.min(100, Math.max(0, prep.resumeScore?.score || 0))
  if (s >= 70) return 'var(--green)'
  if (s >= 50) return 'var(--yellow)'
  return 'var(--red)'
})
const scoreLabel = computed(() => {
  const s = prep.resumeScore?.score ?? 0
  if (s >= 90) return '非常匹配'
  if (s >= 70) return '良好匹配'
  if (s >= 60) return '部分匹配'
  if (s >= 50) return '匹配度较低'
  return '匹配度低'
})

/* ---------- 自定义题目选择 ---------- */
async function loadCustomQuestions() {
  try {
    const result = await api.get('/api/custom/questions')
    customOptions.value = result.questions || []
  } catch {
    customOptions.value = []
  }
}

async function onUseCustom(e) {
  prep.useCustom = e.target.checked
  if (prep.useCustom) await loadCustomQuestions()
}

function toggleCustom(id, checked) {
  if (checked) {
    if (!prep.selectedCustomIds.includes(id)) prep.selectedCustomIds.push(id)
  } else {
    prep.selectedCustomIds = prep.selectedCustomIds.filter((x) => x !== id)
  }
}

/* ---------- 清除本地缓存 ---------- */
function clearLocalData() {
  if (!confirm('确定清除所有本地缓存（表单记忆、草稿、登录状态）吗？')) return
  prep.setPosition('')
  prep.setCompany('')
  prep.setResume('')
  prep.profile = null
  prep.clearScore()
  prep.selectedCustomIds = []
  localStorage.clear()
  toast('本地缓存已清除')
  setTimeout(() => window.location.reload(), 500)
}

/* ---------- 跳转 ---------- */
function goInterview() {
  if (!canStart.value) {
    if (!prep.resume.trim()) { toast('请先填写或上传简历'); return }
    if (!prep.profile) { toast('请先生成岗位画像'); return }
    if (!prep.resumeScore) { toast('请先对简历进行评分'); return }
    toast('简历评分低于 70 分，请优化简历后再面试')
    return
  }
  router.push('/interview')
}

function goMock() {
  if (!canStart.value) {
    toast('请先完成前三步：填写信息 → 岗位画像 → 简历评分')
    return
  }
  router.push('/mock-interview')
}
</script>

<template>
  <div>
    <!-- 1. 填写信息 -->
    <div class="card">
      <h2>1. 填写信息</h2>
      <div class="form-group">
        <label>目标岗位</label>
        <input v-model="prep.position" type="text" placeholder="例如：Python后端开发 3年经验" @input="prep.saveFormMemory">
      </div>
      <div class="form-group">
        <label>目标公司（选填）</label>
        <input v-model="prep.company" type="text" placeholder="例如：字节跳动、腾讯... 留空则不限定" @input="prep.saveFormMemory">
      </div>
      <div class="form-group">
        <label>简历内容（粘贴或上传简历文件）</label>
        <textarea v-model="prep.resume" rows="6" placeholder="粘贴你的简历内容，包括技能、项目经验、工作经历等..." @input="prep.clearScore(); prep.saveFormMemory()"></textarea>
        <div class="form-hint" style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap">
          也支持上传简历文件（JPG/PNG/PDF/Word/Markdown）：
          <input type="file" accept=".jpg,.jpeg,.png,.pdf,.docx,.md" @change="handleResumeUpload">
          <span style="margin-left: 6px; font-size: 12px; color: var(--text2)">{{ fileName }}</span>
        </div>
      </div>
      <div style="margin-top: 8px">
        <button class="btn btn-secondary btn-sm" @click="clearLocalData">清除本地缓存</button>
      </div>
    </div>

    <!-- 2. 岗位画像 -->
    <div class="card">
      <h2>2. 生成岗位画像</h2>
      <p style="font-size: 13px; color: var(--text2); margin-bottom: 12px">
        AI 将分析该岗位的招聘要求和技术栈，生成针对性的面试画像。
      </p>
      <button class="btn btn-primary" :disabled="researching" @click="doResearch(false)">
        {{ researching ? '分析中...' : '开始分析岗位' }}
      </button>
      <div v-if="researching" style="margin-top: 12px; padding: 20px; text-align: center; color: var(--text2)">
        AI 正在分析岗位要求...<br>约需 15-30 秒
      </div>
      <div v-if="prep.profile" style="background: var(--surface2); border-radius: var(--radius); padding: 16px; margin-top: 8px">
        <div style="font-weight: 600; font-size: 16px; margin-bottom: 8px">{{ prep.profile.position || prep.position }}</div>
        <div v-if="prep.profile.company" style="margin-bottom: 6px">
          <span class="skill-tag" style="background: var(--accent)">🏢 {{ prep.profile.company }}</span>
        </div>
        <div v-if="prep.profile.hiring_status || prep.profile.salary_range" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px">
          <span v-if="prep.profile.hiring_status" class="score-tag">招聘状态：{{ prep.profile.hiring_status }}</span>
          <span v-if="prep.profile.salary_range" class="score-tag">薪酬：{{ prep.profile.salary_range }}</span>
        </div>
        <div v-if="prep.profile.summary" class="markdown-body" style="font-size: 13px; color: var(--text2); margin-bottom: 8px" v-html="md(prep.profile.summary)"></div>
        <div v-if="prep.profile.company_insights" class="markdown-body" style="font-size: 13px; color: var(--text); margin-bottom: 8px; padding: 8px 10px; background: var(--surface); border-left: 3px solid var(--accent); border-radius: 6px" v-html="md(prep.profile.company_insights)"></div>
        <div v-if="prep.profile.required_skills && prep.profile.required_skills.length" style="margin-bottom: 6px">
          <strong style="font-size: 13px">必备技能：</strong><br>
          <span v-for="s in prep.profile.required_skills" :key="s" class="skill-tag">{{ s }}</span>
        </div>
        <div v-if="prep.profile.nice_to_have && prep.profile.nice_to_have.length" style="margin-bottom: 6px">
          <strong style="font-size: 13px">加分项：</strong><br>
          <span v-for="s in prep.profile.nice_to_have" :key="s" class="skill-tag">{{ s }}</span>
        </div>
        <div v-if="prep.profile.tech_stack && prep.profile.tech_stack.length" style="font-size: 13px; color: var(--text2); margin-bottom: 6px">
          <strong>技术栈：</strong>{{ prep.profile.tech_stack.join('、') }}
        </div>
        <div v-if="prep.profile.responsibilities && prep.profile.responsibilities.length" style="margin-bottom: 8px">
          <strong style="font-size: 13px">主要职责：</strong><br>
          <div v-for="r in prep.profile.responsibilities" :key="r" style="font-size: 12px; color: var(--text2); padding-left: 12px">- {{ r }}</div>
        </div>
        <div v-if="prep.profile.common_interview_topics && prep.profile.common_interview_topics.length" style="margin-bottom: 8px">
          <strong style="font-size: 13px">常见面试题：</strong><br>
          <div v-for="(t, i) in prep.profile.common_interview_topics" :key="i" class="topic-item markdown-body" v-html="md(t)"></div>
        </div>
        <div v-if="prep.profile.interview_focus && prep.profile.interview_focus.length" style="margin-bottom: 8px">
          <strong style="font-size: 13px">考察重点：</strong><br>
          <span v-for="f in prep.profile.interview_focus" :key="f" class="focus-tag">{{ f }}</span>
        </div>
        <div v-if="prep.profile.difficulty || prep.profile.years_experience" style="font-size: 12px; color: var(--text2); margin-bottom: 4px">
          <template v-if="prep.profile.difficulty">难度级别：{{ ({ junior: '初级', mid: '中级', senior: '高级' })[prep.profile.difficulty] || prep.profile.difficulty }} · </template>
          <template v-if="prep.profile.years_experience">经验要求：{{ prep.profile.years_experience }}</template>
        </div>
        <div v-if="prep.profile.industry_insights" class="markdown-body" style="font-size: 12px; color: var(--text2); margin-top: 6px; padding: 8px; background: var(--surface); border-radius: 6px" v-html="md(prep.profile.industry_insights)"></div>
        <div v-if="prep.profile.sources && prep.profile.sources.length" style="font-size: 12px; color: var(--text2); margin-top: 8px">
          <strong>参考来源：</strong>
          <span v-for="(s, i) in prep.profile.sources.slice(0, 5)" :key="i" style="display: block; margin-top: 2px">{{ s }}</span>
        </div>
        <div style="margin-top: 8px"><button class="btn btn-secondary btn-sm" :disabled="researching" @click="doResearch(true)">重新分析</button></div>
      </div>
    </div>

    <!-- 3. 简历评分 -->
    <div class="card">
      <h2>3. 简历评分</h2>
      <p style="font-size: 13px; color: var(--text2); margin-bottom: 12px">
        评估简历与目标岗位的匹配度，低于 70 分建议优化后再面试。
      </p>
      <button class="btn btn-primary" :disabled="scoring" @click="scoreResume">
        {{ scoring ? '评分中...' : (prep.resumeScore ? '重新评分' : '开始评分') }}
      </button>
      <div v-if="prep.resumeScore" style="padding: 16px 0">
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 12px">
          <div class="score-number" :style="{ color: scoreColor }">{{ Math.min(100, Math.max(0, prep.resumeScore.score)) }}</div>
          <div style="flex: 1">
            <div class="score-label" :style="{ color: scoreColor }">{{ scoreLabel }}</div>
            <div class="score-bar">
              <div class="score-bar-fill" :style="{ width: Math.min(100, Math.max(0, prep.resumeScore.score)) + '%', background: scoreColor }"></div>
            </div>
          </div>
        </div>
        <div v-if="prep.resumeScore.strengths && prep.resumeScore.strengths.length">
          <div class="score-section-title" style="color: var(--green)">优势</div>
          <ul class="score-detail-list"><li v-for="s in prep.resumeScore.strengths" :key="s" class="strength">{{ s }}</li></ul>
        </div>
        <div v-if="prep.resumeScore.weaknesses && prep.resumeScore.weaknesses.length">
          <div class="score-section-title" style="color: var(--yellow)">不足</div>
          <ul class="score-detail-list"><li v-for="s in prep.resumeScore.weaknesses" :key="s" class="weakness">{{ s }}</li></ul>
        </div>
        <div v-if="prep.resumeScore.suggestions && prep.resumeScore.suggestions.length">
          <div class="score-section-title" style="color: var(--accent2)">优化建议</div>
          <ul class="score-detail-list"><li v-for="s in prep.resumeScore.suggestions" :key="s" class="suggestion">{{ s }}</li></ul>
        </div>
        <FeedbackButtons
          v-if="prep.resumeScore._record_id"
          record-type="score"
          :record-id="prep.resumeScore._record_id"
          :data="prep.resumeScore"
        />
      </div>
    </div>

    <!-- 4. 开始面试 -->
    <div class="card">
      <h2>4. 开始面试</h2>
      <p style="font-size: 13px; color: var(--text2); margin-bottom: 12px">
        准备好后点击下方按钮，AI 面试官将根据你的简历和岗位要求进行模拟面试。
      </p>
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px">
        <div style="display: flex; gap: 8px; flex-wrap: wrap">
          <button class="btn btn-primary" :disabled="!canStart" @click="goInterview">开始模拟面试</button>
          <button class="btn btn-secondary" :disabled="!canStart" title="请先完成前三步：填写信息 → 岗位画像 → 简历评分" @click="goMock">🎭 开始拟真面试</button>
        </div>
        <label style="display: flex; align-items: center; cursor: pointer; font-size: 13px; gap: 8px; flex-shrink: 0">
          <input type="checkbox" class="custom-checkbox" style="width: auto" :checked="prep.useCustom" @change="onUseCustom">
          <span>使用自定义题目 <span style="font-size: 11px; color: var(--text2)">（需先在「自定义题目」标签页添加）</span></span>
        </label>
      </div>
      <div v-if="prep.useCustom" style="margin-top: 8px; padding: 10px; background: var(--surface2); border-radius: 8px; max-height: 200px; overflow-y: auto">
        <div v-if="!customOptions.length" class="empty-state" style="font-size: 13px">暂无自定义题目，请先到「自定义题目」页添加</div>
        <label v-for="q in customOptions" :key="q.id" style="display: flex; gap: 8px; padding: 6px 4px; font-size: 13px; cursor: pointer; align-items: flex-start">
          <input type="checkbox" style="width: auto; margin-top: 2px" :checked="prep.selectedCustomIds.includes(q.id)" @change="toggleCustom(q.id, $event.target.checked)">
          <span>{{ (q.question || '').slice(0, 60) }}</span>
        </label>
      </div>
    </div>
  </div>
</template>
