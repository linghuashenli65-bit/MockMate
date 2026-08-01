import { useSettingsStore } from '../stores/settings'

function buildHeaders(extra) {
  const headers = { ...(extra || {}) }
  const settings = useSettingsStore()

  if (settings.authToken) {
    headers['Authorization'] = 'Bearer ' + settings.authToken
  }
  return headers
}

async function request(url, options) {
  const settings = useSettingsStore()
  try {
    const r = await fetch(url, options)
    if (r.status === 401) {
      settings.logout()
      const detail = (await r.json().catch(() => ({}))).detail || '登录已过期，请重新登录'
      throw new Error(detail)
    }
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({}))).detail || r.statusText
      throw new Error(detail)
    }
    return r.json()
  } catch (e) {
    if (e instanceof TypeError && e.message === 'Failed to fetch') {
      throw new Error('无法连接到服务器，请确认服务已启动')
    }
    throw e
  }
}

export const api = {
  get(url) {
    return request(url, { method: 'GET', headers: buildHeaders() })
  },
  post(url, data) {
    return request(url, {
      method: 'POST',
      headers: buildHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(data),
    })
  },
  put(url, data) {
    return request(url, {
      method: 'PUT',
      headers: buildHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(data),
    })
  },
  delete(url) {
    return request(url, { method: 'DELETE', headers: buildHeaders() })
  },
  async upload(url, formData) {
    const headers = buildHeaders()
    delete headers['Content-Type']
    try {
      const r = await fetch(url, { method: 'POST', body: formData, headers })
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))).detail || r.statusText
        throw new Error(detail)
      }
      return r.json()
    } catch (e) {
      if (e instanceof TypeError && e.message === 'Failed to fetch') {
        throw new Error('无法连接到服务器')
      }
      throw e
    }
  },

  /* ---------- 拟真面试 ---------- */
  mockCreateInterviewer(data) { return this.post('/api/mock/interviewers', data) },
  mockListInterviewers() { return this.get('/api/mock/interviewers') },
  mockGetInterviewer(id) { return this.get('/api/mock/interviewers/' + id) },
  mockUpdateInterviewer(id, data) { return this.put('/api/mock/interviewers/' + id, data) },
  mockDeleteInterviewer(id) { return this.delete('/api/mock/interviewers/' + id) },
  mockStartInterview(data) { return this.post('/api/mock/interview/start', data) },
  mockSubmitAnswer(data) { return this.post('/api/mock/interview/answer', data) },
  mockEndInterview(sessionId) { return this.post('/api/mock/interview/end/' + sessionId) },
  mockGetState(sessionId) { return this.get('/api/mock/interview/state/' + sessionId) },
  mockGetReport(sessionId) { return this.get('/api/mock/interview/report/' + sessionId) },
  mockGetHistory() { return this.get('/api/mock/interview/history') },

  /* ---------- 用户设置（服务端存储） ---------- */
  getSettings() { return this.get('/api/settings') },
  updateSettings(payload) { return this.put('/api/settings', payload) },
}

export default api
