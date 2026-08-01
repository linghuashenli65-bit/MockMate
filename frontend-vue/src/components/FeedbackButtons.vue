<script setup>
import { computed, ref } from 'vue'
import { api } from '../services/api'
import { toast } from '../utils/helpers'

const props = defineProps({
  recordType: { type: String, required: true }, // 'score' | 'eval'
  recordId: { type: [Number, String], required: true },
  data: { type: Object, default: () => ({}) },
})

const rated = ref('')
const modalOpen = ref(false)
const submitting = ref(false)
const form = ref({})

const fields = computed(() => {
  if (props.recordType === 'score') {
    return [
      { key: 'score', label: '综合评分（0-100）', type: 'number', value: props.data?.score ?? 0 },
      ...(props.data?.strengths || []).map((s, i) => ({ key: 'strength_' + i, label: '优点', value: s })),
      ...(props.data?.weaknesses || []).map((s, i) => ({ key: 'weakness_' + i, label: '不足', value: s })),
      ...(props.data?.suggestions || []).map((s, i) => ({ key: 'suggestion_' + i, label: '优化建议', value: s })),
    ]
  }
  return [
    { key: 'technical_score', label: '技术评分（0-10）', type: 'number', value: props.data?.technical_score ?? 0 },
    { key: 'logic_score', label: '逻辑评分（0-10）', type: 'number', value: props.data?.logic_score ?? 0 },
    { key: 'depth_score', label: '深度评分（0-10）', type: 'number', value: props.data?.depth_score ?? 0 },
    { key: 'communication_score', label: '表达评分（0-10）', type: 'number', value: props.data?.communication_score ?? 0 },
    { key: 'overall_score', label: '综合评分（0-10）', type: 'number', value: props.data?.overall_score ?? 0 },
    { key: 'summary', label: '评语', type: 'textarea', value: props.data?.summary || '' },
    { key: 'strengths', label: '优点（逗号分隔）', value: (props.data?.strengths || []).join('、') },
    { key: 'improvements', label: '改进建议（逗号分隔）', value: (props.data?.improvements || []).join('、') },
    { key: 'reference_answer', label: '参考回答', type: 'textarea', value: props.data?.reference_answer || '' },
  ]
})

async function submitRating(rating) {
  if (rating === 'up') {
    await api.post('/api/feedback/submit', {
      record_type: props.recordType, record_id: props.recordId, rating: 'up', corrections: null,
    })
    rated.value = 'up'
    toast('感谢反馈！')
  } else {
    modalOpen.value = true
    const f = {}
    fields.value.forEach((x) => { f[x.key] = x.value })
    form.value = f
  }
}

async function submitCorrection() {
  submitting.value = true
  try {
    await api.post('/api/feedback/submit', {
      record_type: props.recordType,
      record_id: props.recordId,
      rating: 'down',
      corrections: { ...form.value },
    })
    rated.value = 'down'
    modalOpen.value = false
    toast('感谢反馈，评分已修正')
  } catch (e) {
    toast('提交失败: ' + e.message)
  }
  submitting.value = false
}
</script>

<template>
  <div class="feedback-buttons" style="display: flex; align-items: center; gap: 8px; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border)">
    <span style="font-size: 12px; color: var(--text2); margin-right: 4px">这个评分准确吗？</span>
    <button
      class="fb-btn"
      :disabled="!!rated"
      @click="submitRating('up')"
    >{{ rated === 'up' ? '✅ 已采纳' : '👍 准确' }}</button>
    <button
      class="fb-btn"
      :disabled="!!rated"
      @click="submitRating('down')"
    >{{ rated === 'down' ? '👎 已提交修正' : '👎 不准确' }}</button>
  </div>

  <!-- 修正弹窗 -->
  <Teleport to="body">
    <div v-if="modalOpen" class="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 10000; display: flex; align-items: center; justify-content: center">
      <div style="background: var(--surface); border-radius: 12px; padding: 24px; max-width: 560px; width: 90%; max-height: 80vh; overflow-y: auto">
        <h3 style="margin: 0 0 16px; font-size: 16px">修正评分</h3>
        <div v-for="f in fields" :key="f.key" class="form-group">
          <label>{{ f.label }}</label>
          <input v-if="f.type === 'number'" v-model.number="form[f.key]" type="number" style="width: 100px">
          <textarea v-else-if="f.type === 'textarea'" v-model="form[f.key]" rows="3" style="width: 100%"></textarea>
          <input v-else v-model="form[f.key]" type="text" style="width: 100%">
        </div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px">
          <button class="btn btn-secondary" @click="modalOpen = false">取消</button>
          <button class="btn btn-primary" :disabled="submitting" @click="submitCorrection">
            {{ submitting ? '提交中...' : '提交修正' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.fb-btn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text2);
  cursor: pointer;
}
.fb-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
