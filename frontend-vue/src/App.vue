<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSettingsStore } from './stores/settings'
import { api } from './services/api'
import { ls, toast } from './utils/helpers'

const settings = useSettingsStore()
const route = useRoute()

const tabs = [
  { name: 'setup', label: '准备面试', path: '/' },
  { name: 'mock-interview', label: '拟真面试', path: '/mock-interview' },
  { name: 'interview', label: '模拟面试', path: '/interview' },
  { name: 'favorites', label: '题目收藏', path: '/favorites' },
  { name: 'custom', label: '自定义题目', path: '/custom' },
  { name: 'finetune', label: '微调', path: '/finetune' },
  { name: 'settings', label: '设置', path: '/settings' },
]

const statusText = ref('连接中...')
const statusClass = ref('yellow')
const userInfo = ref(null)

onMounted(async () => {
  await checkStatus()
  await checkAuth()
  if (settings.authToken) {
    await settings.loadSettings()
    await checkStatus()
  }
  window.addEventListener('mockmate-settings-changed', () => checkStatus())
})

// 登录状态变化时联动头部用户信息
watch(
  () => settings.authToken,
  async (token) => {
    if (token) {
      userInfo.value = {
        email: ls.get('user_email', ''),
        nickname: ls.get('user_nickname', ''),
      }
      await settings.loadSettings()
      await checkStatus()
    } else {
      userInfo.value = null
    }
  }
)

async function checkStatus() {
  try {
    const data = await api.get('/api/status')
    settings.setStatus(data)
    const p = data.provider || 'mimo'
    const readyMap = {
      mimo: data.mimo_ready,
      deepseek: data.deepseek_ready,
      qwen: data.qwen_ready,
      zhipu: data.zhipu_ready,
    }
    if (readyMap[p]) {
      statusText.value = '已连接'
      statusClass.value = 'green'
    } else if (data.status === 'ok') {
      statusText.value = '未完全配置'
      statusClass.value = 'yellow'
    } else {
      statusText.value = '异常'
      statusClass.value = 'red'
    }
  } catch (e) {
    statusText.value = '连接失败'
    statusClass.value = 'red'
  }
}

async function checkAuth() {
  if (!settings.authToken) return
  try {
    const me = await api.get('/api/auth/me')
    userInfo.value = me
  } catch {
    userInfo.value = null
  }
}

function logout() {
  settings.logout()
  userInfo.value = null
  toast('已退出登录')
}
</script>

<template>
  <div class="app">
    <header>
      <div>
        <h1>MockMate</h1>
        <div class="sub">AI 面试模拟陪练</div>
      </div>
      <div class="status">
        <span class="dot" :class="statusClass"></span>
        <span id="statusText">{{ statusText }}</span>
      </div>
      <div class="user-info" v-if="userInfo">
        <span id="userNickname">{{ userInfo.nickname || userInfo.email }}</span>
        <button class="btn btn-sm btn-secondary" @click="logout">退出</button>
      </div>
      <div class="user-info" v-else-if="!settings.authToken">
        <RouterLink class="btn btn-sm btn-secondary" to="/login">登录</RouterLink>
      </div>
    </header>

    <nav class="tabs">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.name"
        class="tab"
        :class="{ active: route.name === tab.name }"
        :to="tab.path"
      >{{ tab.label }}</RouterLink>
    </nav>

    <main class="tab-content active">
      <RouterView />
    </main>
  </div>
</template>
