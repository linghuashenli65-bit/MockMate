import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'cv@test.dev'

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-cv-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9344', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9344/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
localStorage.setItem('mockmate_company', '示例科技'); 'ok'`,
})
await send('Page.navigate', { url: BACKEND + '/' })
await new Promise((res) => setTimeout(res, 3500))
await send('Runtime.evaluate', {
  expression: `(() => {
    const inp = [...document.querySelectorAll('input')].find(i => i.placeholder && i.placeholder.includes('Python'));
    if (inp) { inp.value = '后端开发'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    const c = [...document.querySelectorAll('input')].find(i => i.placeholder && i.placeholder.includes('字节'));
    if (c) { c.value = '示例科技'; c.dispatchEvent(new Event('input', { bubbles: true })); }
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('开始分析岗位'));
    if (btn) btn.click();
    return true;
  })()`,
})
await new Promise((res) => setTimeout(res, 5000))
const body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 3000)', returnByValue: true })
const text = body.result?.value || ''
console.log('HAS 招聘状态:', text.includes('招聘状态') ? 'YES' : 'NO')
console.log('HAS 薪酬:', text.includes('薪酬') ? 'YES' : 'NO')
console.log('HAS 公司徽标:', text.includes('示例科技') ? 'YES' : 'NO')
console.log('HAS 参考来源:', text.includes('参考来源') ? 'YES' : 'NO')
console.log('--- body 关键段 ---')
const i = text.indexOf('招聘状态')
console.log(i >= 0 ? text.slice(Math.max(0, i - 120), i + 300) : text.slice(0, 400))
console.log('--- events ---')
console.log(events.join('\n') || '(no errors)')
chrome.kill()
process.exit(0)
