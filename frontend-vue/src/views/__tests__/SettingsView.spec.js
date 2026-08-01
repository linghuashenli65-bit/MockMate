import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '../SettingsView.vue'

vi.mock('../../services/api', () => ({
  api: {
    getSettings: vi.fn().mockResolvedValue({
      provider: 'mimo',
      keys: { mimo: null, deepseek: null, qwen: null, zhipu: null },
      configured: { mimo: false, deepseek: false, qwen: false, zhipu: false },
      models: {},
      tts_enabled: true,
    }),
    updateSettings: vi.fn().mockResolvedValue({}),
    get: vi.fn().mockResolvedValue({}),
  },
}))

const stubs = {
  RouterLink: { template: '<a><slot /></a>' },
}

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('渲染 AI 服务配置、四个提供商与语音播报内容（回归：裸 <template> 导致内容区空白）', async () => {
    const wrapper = mount(SettingsView, { global: { stubs } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('AI 服务配置')
    expect(text).toContain('MiMo')
    expect(text).toContain('DeepSeek')
    expect(text).toContain('通义千问')
    expect(text).toContain('智谱 GLM')
    expect(text).toContain('测试连接')
    expect(text).toContain('语音播报')
    expect(text).toContain('保存模型配置')
    // 回归：内容不得被裸 <template> 包裹（真实浏览器中不会渲染其内容）
    expect(wrapper.html()).not.toContain('<template>')
  })
})
