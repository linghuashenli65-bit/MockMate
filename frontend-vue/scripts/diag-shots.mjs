import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOT_DIR = 'C:/Users/27644/.codex/visualizations/2026/08/01/019fbc9f-4ee5-7ba2-8a7c-a7bf4ab23ce7'

const PAGES = [
  { path: '/', file: 'page-setup.png' },
  { path: '/settings', file: 'page-settings.png' },
  { path: '/custom', file: 'page-custom.png' },
  { path: '/favorites', file: 'page-favorites.png' },
  { path: '/finetune', file: 'page-finetune.png' },
  { path: '/history', file: 'page-history.png' },
  { path: '/interview', file: 'page-interview.png' },
  { path: '/mock-interview', file: 'page-mock.png' },
  { path: '/asr', file: 'page-asr.png' },
]

const email = 'shot' + Date.now() + '@test.dev'
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
  body: JSON.stringify({ email, password: 'test123456', code, nickname: '截图巡检' }),
})
const auth = await r.json()
console.log('registered:', !!auth.token)

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-shots-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9336', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

r = await fetch('http://127.0.0.1:9336/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
localStorage.setItem('mockmate_user_nickname', '截图巡检'); 'ok'`,
})

await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1200, deviceScaleFactor: 1, mobile: false })

for (const page of PAGES) {
  await send('Page.navigate', { url: BACKEND + page.path })
  // 历史页含图表，多等一会儿
  await new Promise((res) => setTimeout(res, page.path === '/history' ? 4000 : 2800))
  const shot = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(path.join(SHOT_DIR, page.file), Buffer.from(shot.data, 'base64'))
  console.log('saved', page.file)
}

chrome.kill()
process.exit(0)
