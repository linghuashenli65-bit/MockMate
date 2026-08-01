import { defineStore } from 'pinia'
import { ls } from '../utils/helpers'
import { api } from '../services/api'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    authToken: ls.get('auth_token', '') || '',
    // 服务端用户设置（/api/settings）
    server: {
      provider: 'mimo',
      keys: { mimo: null, deepseek: null, qwen: null, zhipu: null },
      configured: { mimo: false, deepseek: false, qwen: false, zhipu: false },
      models: {},
      tts_enabled: true,
    },
    loaded: false,
    status: null, // /api/status 结果
  }),

  getters: {
    provider: (s) => s.server.provider || 'mimo',
    isLoggedIn: (s) => Boolean(s.authToken),
    ttsEnabled: (s) => Boolean(s.server.tts_enabled),
    models: (s) => s.server.models || {},
  },

  actions: {
    async loadSettings() {
      if (!this.authToken) return
      try {
        const data = await api.getSettings()
        this.server = { ...this.server, ...data }
        this.loaded = true
      } catch { /* 未登录/接口暂不可用时保持默认 */ }
    },
    async updateSettings(payload) {
      const data = await api.updateSettings(payload)
      this.server = { ...this.server, ...data }
      return data
    },
    login(token) {
      this.authToken = token
      ls.set('auth_token', token)
      this.loadSettings()
    },
    logout() {
      this.authToken = ''
      ls.remove('auth_token')
      this.loaded = false
    },
    setStatus(data) {
      this.status = data
    },
  },
})
