<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSettingsStore } from '../stores/settings'
import { api } from '../services/api'
import { ls, toast } from '../utils/helpers'

const router = useRouter()
const settings = useSettingsStore()

const mode = ref('login')
const loginEmail = ref('')
const loginPassword = ref('')
const regEmail = ref('')
const regNickname = ref('')
const regPassword = ref('')
const regCode = ref('')
const sendingCode = ref(false)
const countdown = ref(0)
const submitting = ref(false)

function switchMode(m) {
  mode.value = m
}

async function sendCode() {
  const email = regEmail.value.trim()
  if (!email || email.indexOf('@') === -1) {
    toast('请输入有效邮箱')
    return
  }
  sendingCode.value = true
  try {
    const res = await api.post('/api/auth/send-code', { email })
    toast('验证码已发送')
    if (res.dev_code) {
      toast('开发模式，验证码: ' + res.dev_code)
      regCode.value = res.dev_code
    }
    countdown.value = 60
    const timer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        clearInterval(timer)
        countdown.value = 0
      }
    }, 1000)
  } catch (e) {
    toast('发送失败: ' + e.message)
  }
  sendingCode.value = false
}

function finishAuth(res) {
  settings.login(res.token)
  ls.set('user_email', res.user.email)
  ls.set('user_nickname', res.user.nickname || res.user.email.split('@')[0])
  toast('欢迎，' + (res.user.nickname || res.user.email))
  router.push('/settings')
}

async function doLogin() {
  const email = loginEmail.value.trim()
  const password = loginPassword.value
  if (!email || !password) {
    toast('请输入邮箱和密码')
    return
  }
  submitting.value = true
  try {
    const res = await api.post('/api/auth/login', { email, password })
    finishAuth(res)
  } catch (e) {
    toast('登录失败: ' + e.message)
  }
  submitting.value = false
}

async function doRegister() {
  const email = regEmail.value.trim()
  const nickname = regNickname.value.trim()
  const password = regPassword.value
  const code = regCode.value.trim()
  if (!email || email.indexOf('@') === -1) {
    toast('请输入有效邮箱')
    return
  }
  if (password.length < 6) {
    toast('密码至少 6 位')
    return
  }
  if (!code) {
    toast('请输入验证码')
    return
  }
  submitting.value = true
  try {
    const res = await api.post('/api/auth/register', { email, password, code, nickname })
    finishAuth(res)
  } catch (e) {
    toast('注册失败: ' + e.message)
  }
  submitting.value = false
}
</script>

<template>
  <div class="login-page" @keydown.enter="mode === 'login' ? doLogin() : doRegister()">
    <h1>MockMate</h1>
    <div class="sub">AI 面试模拟陪练</div>

    <div class="auth-tabs">
      <button class="auth-tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
      <button class="auth-tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
    </div>

    <!-- 登录 -->
    <div v-if="mode === 'login'">
      <div class="form-group">
        <label>邮箱</label>
        <input v-model="loginEmail" type="email" placeholder="请输入邮箱" autocomplete="email">
      </div>
      <div class="form-group">
        <label>密码</label>
        <input v-model="loginPassword" type="password" placeholder="请输入密码" autocomplete="current-password">
      </div>
      <button class="btn btn-primary" :disabled="submitting" @click="doLogin">
        {{ submitting ? '登录中...' : '登录' }}
      </button>
      <div class="bottom-link">还没有账号？<a @click="switchMode('register')">立即注册</a></div>
    </div>

    <!-- 注册 -->
    <div v-else>
      <div class="form-group">
        <label>邮箱</label>
        <input v-model="regEmail" type="email" placeholder="请输入邮箱" autocomplete="email">
      </div>
      <div class="form-group">
        <label>昵称（选填）</label>
        <input v-model="regNickname" type="text" placeholder="如何称呼你">
      </div>
      <div class="form-group">
        <label>密码</label>
        <input v-model="regPassword" type="password" placeholder="至少 6 位" autocomplete="new-password">
      </div>
      <div class="form-group">
        <label>邮箱验证码</label>
        <div class="code-row">
          <input v-model="regCode" type="text" placeholder="输入验证码">
          <button class="btn btn-secondary btn-sm" :disabled="sendingCode || countdown > 0" @click="sendCode">
            {{ countdown > 0 ? countdown + 's' : (sendingCode ? '发送中...' : '发送验证码') }}
          </button>
        </div>
      </div>
      <button class="btn btn-primary" :disabled="submitting" @click="doRegister">
        {{ submitting ? '注册中...' : '注册' }}
      </button>
      <div class="bottom-link">已有账号？<a @click="switchMode('login')">立即登录</a></div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  max-width: 380px;
  margin: 24px auto;
  padding: 32px 28px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.login-page h1 {
  text-align: center;
  font-size: 26px;
  margin-bottom: 4px;
  background: linear-gradient(135deg, var(--accent2), var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.login-page .sub {
  text-align: center;
  font-size: 13px;
  color: var(--text2);
  margin-bottom: 24px;
}
.login-page .form-group {
  margin-bottom: 16px;
}
.login-page .form-group label {
  font-size: 12px;
  color: var(--text2);
  margin-bottom: 4px;
  display: block;
}
.login-page .form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}
.login-page .form-group input:focus {
  border-color: var(--accent);
}
.login-page .btn-primary {
  width: 100%;
  padding: 12px;
  font-size: 15px;
}
.auth-tabs {
  display: flex;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.auth-tab {
  flex: 1;
  padding: 10px;
  background: none;
  border: none;
  color: var(--text2);
  font-size: 15px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.auth-tab.active {
  color: var(--accent2);
  border-bottom-color: var(--accent);
}
.code-row {
  display: flex;
  gap: 8px;
}
.code-row input {
  flex: 1;
}
.bottom-link {
  margin-top: 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text2);
}
.bottom-link a {
  color: var(--accent2);
  cursor: pointer;
}
</style>
