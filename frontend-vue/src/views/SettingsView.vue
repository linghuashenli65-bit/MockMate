<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useSettingsStore } from '../stores/settings'
import { api } from '../services/api'
import { toast } from '../utils/helpers'

const settings = useSettingsStore()

const PROVIDERS = [
  { id: 'mimo', name: 'MiMo（小米）', caps: '推理/出题 · 图片识别 · 语音合成', tts: true },
  { id: 'deepseek', name: 'DeepSeek', caps: '推理/出题 · 对话（不支持图片/语音）', tts: false },
  { id: 'qwen', name: '通义千问', caps: '推理/出题 · 对话 · 图片识别 · 语音合成/识别', tts: true },
  { id: 'zhipu', name: '智谱 GLM', caps: '推理/出题 · 对话 · 语音合成', tts: true },
]

const MODEL_FIELDS = [
  { key: 'qwen_reasoner_model', provider: '通义千问', label: '推理出题模型', default: 'qwen-plus' },
  { key: 'qwen_chat_model', provider: '通义千问', label: '对话模型', default: 'qwen-plus' },
  { key: 'qwen_written_eval_model', provider: '通义千问', label: '笔试判卷模型', default: 'qwen-turbo' },
  { key: 'qwen_tts_model', provider: '通义千问', label: '语音合成模型', default: 'cosyvoice-v3.5-flash' },
  { key: 'zhipu_reasoner_model', provider: '智谱', label: '推理出题模型', default: 'glm-4.7-flash' },
  { key: 'zhipu_chat_model', provider: '智谱', label: '对话模型', default: 'glm-4.7-flash' },
  { key: 'zhipu_written_eval_model', provider: '智谱', label: '笔试判卷模型', default: 'glm-4-flash' },
  { key: 'zhipu_tts_model', provider: '智谱', label: '语音合成模型', default: 'glm-tts' },
]

const keyInputs = reactive({ mimo: '', deepseek: '', qwen: '', zhipu: '' })
const modelDrafts = reactive({})
const testing = ref(false)
const testResult = ref('')

const providerCaps = (id) => PROVIDERS.find((p) => p.id === id)?.caps || ''
const ttsProviderName = () => {
  const map = { mimo: 'MiMo 语音合成', deepseek: 'DeepSeek（不支持语音）', qwen: '通义千问 CosyVoice', zhipu: '智谱 GLM-TTS' }
  return map[settings.provider] || '未知'
}
const ttsSupported = () => settings.provider !== 'deepseek'

function initDrafts() {
  MODEL_FIELDS.forEach((f) => {
    modelDrafts[f.key] = settings.models[f.key] || ''
  })
}

onMounted(async () => {
  if (!settings.loaded) await settings.loadSettings()
  initDrafts()
})

async function saveKey(providerId) {
  const value = (keyInputs[providerId] || '').trim()
  if (!value) {
    toast('请输入 ' + PROVIDERS.find((p) => p.id === providerId)?.name + ' API Key')
    return
  }
  try {
    await settings.updateSettings({ keys: { [providerId]: value } })
    keyInputs[providerId] = ''
    toast(PROVIDERS.find((p) => p.id === providerId)?.name + ' API Key 已保存（服务端加密）')
    window.dispatchEvent(new CustomEvent('mockmate-settings-changed'))
  } catch (e) {
    toast('保存失败: ' + e.message)
  }
}

async function clearKey(providerId) {
  try {
    await settings.updateSettings({ keys: { [providerId]: '' } })
    toast('已清除 ' + PROVIDERS.find((p) => p.id === providerId)?.name + ' API Key')
    window.dispatchEvent(new CustomEvent('mockmate-settings-changed'))
  } catch (e) {
    toast('清除失败: ' + e.message)
  }
}

async function saveProvider(e) {
  const provider = e.target.value
  try {
    await settings.updateSettings({ provider })
    toast('已切换到 ' + (PROVIDERS.find((p) => p.id === provider)?.name || provider))
    window.dispatchEvent(new CustomEvent('mockmate-settings-changed'))
  } catch (e) {
    toast('切换失败: ' + e.message)
  }
}

async function saveModels() {
  try {
    await settings.updateSettings({ models: { ...modelDrafts } })
    toast('模型配置已保存（留空的项使用默认模型）')
  } catch (e) {
    toast('保存失败: ' + e.message)
  }
}

async function toggleTts(e) {
  try {
    await settings.updateSettings({ tts_enabled: e.target.checked })
    toast('语音播报已' + (e.target.checked ? '开启' : '关闭'))
  } catch (err) {
    toast('保存失败: ' + err.message)
    e.target.checked = !e.target.checked
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = ''
  try {
    const data = await api.get('/api/status')
    const rows = PROVIDERS.map((p) => {
      const ready = data[p.id + '_ready']
      return p.name + (ready ? ' ✓' : ' ✗')
    })
    testResult.value = '当前提供商: ' + (data.provider || 'mimo') + '　|　' + rows.join('　')
  } catch (e) {
    testResult.value = '连接失败: ' + e.message
  }
  testing.value = false
}
</script>

<template>
  <div class="settings-page">
    <!-- 未登录 -->
    <div v-if="!settings.authToken" class="card login-tip">
      <h2>AI 服务配置</h2>
      <p class="muted">当前为只读预览：登录后可将 API Key 加密保存到你的账号（服务端存储），换设备自动同步。</p>
      <RouterLink to="/login" class="btn btn-primary">去登录</RouterLink>
    </div>

    <!-- ===== AI 服务配置 ===== -->
    <div class="card">
      <h2>AI 服务配置</h2>
      <p class="form-hint">每个提供商只需配置一个 API Key，对应能力自动启用；Key 加密保存在服务端，界面只显示掩码。</p>

      <div class="form-group">
        <label>默认 AI 提供商</label>
        <select :value="settings.server.provider" :disabled="!settings.authToken" @change="saveProvider">
          <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>

      <div v-for="p in PROVIDERS" :key="p.id" class="provider-row">
        <div class="provider-info">
          <strong>{{ p.name }}</strong>
          <span class="caps">{{ p.caps }}</span>
          <span v-if="settings.server.configured[p.id]" class="key-mask">{{ settings.server.keys[p.id] }}</span>
          <span v-else class="key-empty">未配置</span>
        </div>
        <input
          class="key-input"
          type="password"
          autocomplete="off"
          :placeholder="settings.server.configured[p.id] ? '输入新 Key 覆盖' : '粘贴 API Key'"
          v-model="keyInputs[p.id]"
        >
        <button class="btn btn-sm" :disabled="!settings.authToken" @click="saveKey(p.id)">保存</button>
        <button
          v-if="settings.server.configured[p.id]"
          class="btn btn-sm btn-secondary"
          :disabled="!settings.authToken"
          @click="clearKey(p.id)"
        >清除</button>
      </div>

      <div class="form-group test-row">
        <button class="btn btn-secondary" :disabled="testing" @click="testConnection">
          {{ testing ? '测试中...' : '测试连接' }}
        </button>
        <span v-if="testResult" class="test-result">{{ testResult }}</span>
      </div>
    </div>

    <!-- ===== 高级模型配置 ===== -->
    <details class="card">
      <summary><h2>高级模型配置 <span class="form-hint">（留空使用各提供商默认模型）</span></h2></summary>
      <div v-for="f in MODEL_FIELDS" :key="f.key" class="form-group">
        <label>{{ f.provider }} · {{ f.label }}</label>
        <input
          type="text"
          :placeholder="'默认: ' + f.default"
          :value="modelDrafts[f.key]"
          @input="modelDrafts[f.key] = $event.target.value"
        >
      </div>
      <button class="btn btn-primary" :disabled="!settings.authToken" @click="saveModels">保存模型配置</button>
    </details>

    <!-- ===== 语音播报 ===== -->
    <div class="card">
      <h2>语音播报</h2>
      <div class="setting-row">
        <span class="switch-label">语音播报</span>
        <label class="switch">
          <input
            type="checkbox"
            :checked="settings.server.tts_enabled"
            :disabled="!ttsSupported() || !settings.authToken"
            @change="toggleTts"
          >
          <span class="slider"></span>
        </label>
        <span class="muted">{{ settings.server.tts_enabled ? '开启' : '关闭' }} · 当前：{{ ttsProviderName() }}</span>
      </div>
      <p v-if="!ttsSupported()" class="form-hint warning">当前提供商 DeepSeek 不支持语音合成，已自动关闭。</p>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.provider-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.provider-row:last-of-type {
  border-bottom: none;
}
.provider-info {
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.caps {
  font-size: 12px;
  color: var(--text2);
}
.key-mask {
  font-size: 12px;
  color: var(--green);
}
.key-empty {
  font-size: 12px;
  color: var(--red);
}
.key-input {
  flex: 1;
  min-width: 200px;
}
.test-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.test-result {
  font-size: 13px;
  color: var(--text2);
}
.switch-label {
  min-width: 90px;
  color: var(--text);
}
.setting-row .switch {
  width: 44px;
  min-width: 44px;
  max-width: 44px;
}
.warning {
  color: var(--red) !important;
}
.muted {
  color: var(--text2);
  font-size: 13px;
}
</style>
