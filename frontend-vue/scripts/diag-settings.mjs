import { spawn } from 'node:child_process'
import { writeFileSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOT = 'C:/Users/27644/.codex/visualizations/2026/08/01/019fbc9f-4ee5-7ba2-8a7c-a7bf4ab23ce7/settings_loggedin.png'

// 1. 注册诊断用户
const email = 'diag' + Date.now() + '@test.dev'
let r = await fetch(BACKEND + '/api/auth/send-code', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email }),
})
let code = (await r.json()).dev_code
if (!code) {
  const log = readFileSync(path.resolve(process.cwd(), '../backend/data/mockmate.log'), 'utf8')
  const lines = log.split(/\r?\n/).filter((l) => l.includes(email) && l.includes('验证码'))
  const last = lines[lines.length - 1]
  const m = last && last.match(/: (\d{4,8})\s*$/)
  code = m ? m[1] : null
}
r = await fetch(BACKEND + '/api/auth/register', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'test123456', code, nickname: '诊断' }),
})
const auth = await r.json()
console.log('registered:', email, 'token:', !!auth.token, auth.detail || '')

// 2. 启动无头 Chrome（CDP）
const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9333', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

// 3. 建标签页
r = await fetch('http://127.0.0.1:9333/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
const tab = await r.json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
let msgId = 0
const pending = new Map()
const events = []

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
  } else if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails
    events.push('EXC: ' + (d?.exception?.description || d?.text || ''))
  } else if (msg.method === 'Runtime.consoleAPICalled') {
    events.push('CONSOLE[' + msg.params.type + ']: ' + msg.params.args.map((a) => a.value ?? a.description ?? '').join(' '))
  } else if (msg.method === 'Log.entryAdded') {
    events.push('LOG[' + msg.params.entry.level + ']: ' + msg.params.entry.text)
  } else if (msg.method === 'Network.loadingFailed') {
    events.push('NET-FAIL: ' + msg.params.errorText + ' ' + (msg.params.blockedReason || ''))
  }
}
await new Promise((res) => { ws.onopen = res })
await send('Page.enable')
await send('Runtime.enable')
await send('Log.enable')
await send('Network.enable')
await new Promise((res) => setTimeout(res, 4000))

// 4. 注入登录态
await send('Runtime.evaluate', {
  expression: `localStorage.setItem('mockmate_auth_token', ${JSON.stringify(auth.token)});
localStorage.setItem('mockmate_user_email', ${JSON.stringify(email)});
localStorage.setItem('mockmate_user_nickname', '诊断'); 'ok'`,
})

// 5. 跳转设置页
await send('Page.navigate', { url: BACKEND + '/settings' })
await new Promise((res) => setTimeout(res, 5000))

// 6. 截图 + 页面文本 + 错误
const shot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(SHOT, Buffer.from(shot.data, 'base64'))
console.log('screenshot saved:', SHOT)

const body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 2000)' })
console.log('--- body text ---')
console.log(JSON.stringify(body.result?.value ?? '(empty)', null, 2))

// 回归断言：设置页关键内容必须渲染（裸 <template> 会导致空白）
const pageText = body.result?.value ?? ''
const contentOk = pageText.includes('AI 服务配置') && pageText.includes('语音播报') && pageText.includes('测试连接')
console.log('ASSERT settings content:', contentOk ? 'PASS' : 'FAIL')

console.log('--- events ---')
console.log(events.join('\n') || '(no console errors)')

chrome.kill()
process.exit(contentOk ? 0 : 1)
