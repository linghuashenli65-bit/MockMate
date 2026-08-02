import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'prov@test.dev'

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-prov-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9345', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9345/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
localStorage.setItem('mockmate_user_nickname', '切换验证'); 'ok'`,
})
await send('Page.navigate', { url: BACKEND + '/settings' })
await new Promise((res) => setTimeout(res, 3500))

// 切换下拉到 deepseek
await send('Runtime.evaluate', {
  expression: `(() => {
    const sel = document.querySelector('select');
    if (!sel) return 'no-select';
    sel.value = 'deepseek';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    return sel.options[sel.selectedIndex].text;
  })()`,
  returnByValue: true,
})
await new Promise((res) => setTimeout(res, 2500))

const check = await send('Runtime.evaluate', {
  expression: `(async () => {
    const sel = document.querySelector('select');
    const toastEl = document.getElementById('global-toast');
    const r = await fetch('/api/settings', { headers: { Authorization: 'Bearer ' + localStorage.getItem('mockmate_auth_token') } });
    const d = await r.json();
    return JSON.stringify({ selectValue: sel ? sel.value : null, toast: toastEl ? toastEl.textContent : '', serverProvider: d.provider });
  })()`,
  awaitPromise: true,
  returnByValue: true,
})
console.log('--- result ---')
console.log(check.result?.value)
console.log('--- events ---')
console.log(events.join('\n') || '(no errors)')
chrome.kill()
process.exit(0)
