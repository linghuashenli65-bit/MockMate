import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const IMG_DIR = 'C:/Users/27644/Desktop/MockMate/images'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'img@test.dev'

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-imgs-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9343', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9343/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
localStorage.setItem('mockmate_user_nickname', '截图验证');
localStorage.setItem('mockmate_position', '后端开发');
localStorage.setItem('mockmate_company', '示例科技'); 'ok'`,
})
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 2, mobile: false })

const sleep = (ms) => new Promise((res) => setTimeout(res, ms))
async function setViewport(h) {
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: h, deviceScaleFactor: 2, mobile: false })
}
async function shot(file) {
  const s = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(path.join(IMG_DIR, file), Buffer.from(s.data, 'base64'))
  console.log('saved', file)
}
async function dump(label) {
  const b = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 1200)', returnByValue: true })
  console.log('[' + label + ']', JSON.stringify((b.result?.value || '').slice(0, 300)))
}

// 1. 准备面试页（表单）
await send('Page.navigate', { url: BACKEND + '/' })
await sleep(3500)
await shot('准备面试页.png')

// 2. 岗位画像分析（填岗位 → 点分析，走缓存）
await setViewport(1600)
await send('Runtime.evaluate', {
  expression: `(() => {
    const inp = [...document.querySelectorAll('input')].find(i => i.placeholder && i.placeholder.includes('Python'));
    if (inp) { inp.value = '后端开发'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('开始分析岗位'));
    if (btn) btn.click();
    return !!btn;
  })()`,
})
await sleep(5000)
await send('Runtime.evaluate', {
  expression: `(() => { const c = [...document.querySelectorAll('.card')].find(x => x.textContent.includes('必备技能')); if (c) c.scrollIntoView({ block: 'start' }); return !!c; })()`,
})
await sleep(800)
await dump('research')
await shot('岗位画像分析.png')
await setViewport(1000)

// 3. 模拟面试页（配置/轮次选择）
await send('Page.navigate', { url: BACKEND + '/interview' })
await sleep(3500)
await shot('模拟面试页.png')

// 4. 历史记录页（模拟面试 → 历史记录子页）
await setViewport(1400)
await send('Runtime.evaluate', {
  expression: `(() => { const b = [...document.querySelectorAll('.mock-subtab')].find(x => x.textContent.includes('历史记录')); if (b) b.click(); return !!b; })()`,
})
await sleep(4500)
await dump('history-subview')
await shot('历史记录页.png')
await setViewport(1100)

// 5. 历史记录详情页（雷达图报告）
await send('Runtime.evaluate', {
  expression: `(() => { const el = document.querySelector('.history-item .hi-info'); if (el) el.click(); return !!el; })()`,
})
await sleep(4500)
await dump('history-detail')
await shot('历史记录详情页.png')

console.log('--- events ---')
console.log(events.join('\n') || '(no errors)')
chrome.kill()
process.exit(0)
