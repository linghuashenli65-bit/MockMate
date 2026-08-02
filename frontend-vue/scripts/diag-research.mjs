import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'rs@test.dev'

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-rs-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9346', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9346/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
localStorage.setItem('mockmate_position', '后端开发');
localStorage.setItem('mockmate_company', ''); 'ok'`,
})
await send('Page.navigate', { url: BACKEND + '/' })
await new Promise((res) => setTimeout(res, 3500))

const clickResearch = `(() => {
  const inp = [...document.querySelectorAll('input')].find(i => i.placeholder && i.placeholder.includes('Python'));
  if (inp) { inp.value = '后端开发'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
  const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('开始分析岗位'));
  if (btn) btn.click();
  return !!btn;
})()`

// 第一次：缓存命中
await send('Runtime.evaluate', { expression: clickResearch })
await new Promise((res) => setTimeout(res, 4000))
let body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 2000)', returnByValue: true })
let text = body.result?.value || ''
console.log('第一次后: 有画像卡片=', text.includes('必备技能'), '| 有加载中=', text.includes('正在分析岗位'))

// 重新分析（refresh=true，会走真实搜索）
await send('Runtime.evaluate', {
  expression: `(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.includes('重新分析')); if (b) b.click(); return !!b; })()`,
})
await new Promise((res) => setTimeout(res, 600))
body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 2000)', returnByValue: true })
text = body.result?.value || ''
console.log('点击重新分析后(600ms): 旧卡片已清=', !text.includes('必备技能'), '| 加载中=', text.includes('正在分析岗位'), '| 按钮分析中=', text.includes('分析中'))

// 等待完成（真实搜索可能 30-60s）
await new Promise((res) => setTimeout(res, 45000))
body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 1500)', returnByValue: true })
text = body.result?.value || ''
console.log('等待45s后: 仍加载中=', text.includes('正在分析岗位'), '| 按钮仍分析中=', text.includes('分析中'), '| 有新卡片=', text.includes('必备技能') || text.includes('重新分析'))
console.log('--- events ---')
console.log(events.join('\n') || '(no errors)')
chrome.kill()
process.exit(0)
