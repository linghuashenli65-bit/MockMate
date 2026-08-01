import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOT_DIR = 'C:/Users/27644/.codex/visualizations/2026/08/01/019fbc9f-4ee5-7ba2-8a7c-a7bf4ab23ce7'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'mh@test.dev'

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-mh-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9341', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9341/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
  }
}
await new Promise((res) => { ws.onopen = res })
await send('Page.enable')
await send('Runtime.enable')
await new Promise((res) => setTimeout(res, 4000))

await send('Runtime.evaluate', {
  expression: `localStorage.setItem('mockmate_auth_token', ${JSON.stringify(token)});
localStorage.setItem('mockmate_user_email', ${JSON.stringify(email)});
localStorage.setItem('mockmate_user_nickname', '拟真验证'); 'ok'`,
})
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1400, deviceScaleFactor: 1, mobile: false })

// 拟真面试页（含子导航）
await send('Page.navigate', { url: BACKEND + '/mock-interview' })
await new Promise((res) => setTimeout(res, 3500))
let shot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(path.join(SHOT_DIR, 'mock-nav.png'), Buffer.from(shot.data, 'base64'))
let body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 2500)', returnByValue: true })
console.log('--- mock page body ---')
console.log(JSON.stringify(body.result?.value || ''))

// 点击"历史记录"子导航
await send('Runtime.evaluate', {
  expression: `(() => { const b = [...document.querySelectorAll('.mock-subtab')].find(x => x.textContent.includes('历史记录')); if (b) b.click(); return !!b; })()`,
})
await new Promise((res) => setTimeout(res, 3500))
shot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(path.join(SHOT_DIR, 'mock-sub-history.png'), Buffer.from(shot.data, 'base64'))
body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 3000)', returnByValue: true })
console.log('--- mock history subview body ---')
console.log(JSON.stringify(body.result?.value || ''))
console.log('--- events ---')
console.log(events.join('\n') || '(no errors)')

chrome.kill()
process.exit(0)
