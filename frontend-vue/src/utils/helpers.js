import { marked } from 'marked'

/* ---------- localStorage（统一 mockmate_ 前缀） ---------- */
export const ls = {
  get(key, fallback = null) {
    try {
      const raw = localStorage.getItem('mockmate_' + key)
      return raw === null ? fallback : raw
    } catch {
      return fallback
    }
  },
  set(key, value) {
    try {
      localStorage.setItem('mockmate_' + key, String(value))
    } catch { /* ignore */ }
  },
  remove(key) {
    try {
      localStorage.removeItem('mockmate_' + key)
    } catch { /* ignore */ }
  },
  getJSON(key, fallback = null) {
    try {
      const raw = localStorage.getItem('mockmate_' + key)
      return raw === null ? fallback : JSON.parse(raw)
    } catch {
      return fallback
    }
  },
  setJSON(key, value) {
    try {
      localStorage.setItem('mockmate_' + key, JSON.stringify(value))
    } catch { /* ignore */ }
  },
}

/* ---------- XSS 转义 ---------- */
export function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/* ---------- Markdown 渲染 ---------- */
marked.setOptions({ breaks: true, gfm: true })
export function md(text) {
  try {
    return marked.parse(String(text ?? ''))
  } catch {
    return esc(text)
  }
}

/* ---------- Toast 提示 ---------- */
let _toastTimer = null
export function toast(msg, type = 'info', duration = 2600) {
  let el = document.getElementById('global-toast')
  if (!el) {
    el = document.createElement('div')
    el.id = 'global-toast'
    el.className = 'toast'
    document.body.appendChild(el)
  }
  el.textContent = msg
  el.className = 'toast show toast-' + type
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => {
    el.className = 'toast'
  }, duration)
}

export function closeToast() {
  const el = document.getElementById('global-toast')
  if (el) el.className = 'toast'
}

/* ---------- 通用常量 ---------- */
export const ROUND_NAMES = {
  written: '笔试',
  tech_1: '技术一面',
  tech_2: '技术二面',
  comprehensive: '综合面',
  custom: '自定义练习',
}

export function diffLabel(difficulty) {
  const map = { easy: '简单', medium: '中等', hard: '困难' }
  return map[difficulty] || ''
}

export function formatDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return String(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return String(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* ---------- 评分颜色 ---------- */
export function scoreColor(score) {
  const s = Number(score)
  if (s >= 7) return 'var(--green)'
  if (s >= 4) return 'var(--yellow)'
  return 'var(--red)'
}

/* ---------- 文件下载 ---------- */
export function downloadText(filename, text) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
