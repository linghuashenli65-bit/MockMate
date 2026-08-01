import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const PAGES = [
  { path: '/', label: '准备面试', expect: '填写信息' },
  { path: '/settings', label: '设置', expect: 'AI 服务配置' },
  { path: '/custom', label: '自定义题目', expect: '添加新题目' },
  { path: '/favorites', label: '收藏', expect: '还没有收藏的题目' },
  { path: '/finetune', label: '微调', expect: '训练数据' },
  { path: '/interview', label: '模拟面试', expect: '面试轮次' },
  { path: '/mock-interview', label: '拟真面试', expect: '面试官角色配置' },
]

const email = 'page' + Date.now() + '@test.dev'
let r = await fetch(BACKEND + '/api/auth/send-code', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email }),
})
let code = (await r.json()).dev_code
if (!code) {
  const log = readFileSync(path.resolve(process.cwd(), '../backend/data/mockmate.log'), 'utf8')
  const lines = log.split(/\r?\n/).filter((l) => l.includes(email) && l.includes('验证码'))
  const m = lines[lines.length - 1]?.match(/: (\d{4,8})\s*$/)
  code = m ? m[1] : null
}
r = await fetch(BACKEND + '/api/auth/register', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'test123456', code, nickname: '巡检' }),
})
const auth = await r.json()
console.log('registered:', !!auth.token)

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-pages-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9335', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

r = await fetch('http://127.0.0.1:9335/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
const tab = await r.json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
let msgId = 0
const pending = new Map()
function send(method, params = {}) {
  return new Promise((resolve) => {
    const id = ++msgId
    pending.set(id, resolve)
    ws.send(JSON.stringify({ id, method, params }))
  })
}
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data)
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg.result)
    pending.delete(msg.id)
  }
}
await new Promise((res) => { ws.onopen = res })
await send('Page.enable')
await send('Runtime.enable')
await new Promise((res) => setTimeout(res, 4000))

await send('Runtime.evaluate', {
  expression: `localStorage.setItem('mockmate_auth_token', ${JSON.stringify(auth.token)});
localStorage.setItem('mockmate_user_email', ${JSON.stringify(email)});
localStorage.setItem('mockmate_user_nickname', '巡检'); 'ok'`,
})

let failures = 0
for (const page of PAGES) {
  await send('Page.navigate', { url: BACKEND + page.path })
  await new Promise((res) => setTimeout(res, 2500))
  const body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 3000)', returnByValue: true })
  const text = body.result?.value || ''
  const ok = text.includes(page.expect)
  if (!ok) failures++
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + page.label.padEnd(8, ' ') + ' ' + page.path + '  → ' + (ok ? '找到「' + page.expect + '」' : '未找到「' + page.expect + '」，body=' + JSON.stringify(text.slice(0, 120))))
}

chrome.kill()
console.log(failures === 0 ? 'ALL PAGES PASS' : failures + ' PAGES FAILED')
process.exit(failures === 0 ? 0 : 1)
