import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'seed@test.dev'

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-hc-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9338', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9338/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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

await send('Runtime.evaluate', {
  expression: `localStorage.setItem('mockmate_auth_token', ${JSON.stringify(token)});
localStorage.setItem('mockmate_user_email', ${JSON.stringify(email)});
localStorage.setItem('mockmate_user_nickname', '种子用户'); 'ok'`,
})
const target = process.argv[2] || '/history'
await send('Page.navigate', { url: BACKEND + target })
await new Promise((res) => setTimeout(res, 6000))

const body = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 3000)', returnByValue: true })
const pageText = body.result?.value || ''
console.log('--- body text (tail) ---')
console.log(JSON.stringify(pageText.slice(-600)))
const canvases = await send('Runtime.evaluate', {
  expression: `(() => {
    const out = [];
    document.querySelectorAll('canvas').forEach((c, i) => {
      let nonEmpty = 0, sampled = 0;
      try {
        const ctx = c.getContext('2d');
        const img = ctx.getImageData(0, 0, c.width, c.height).data;
        for (let p = 3; p < img.length; p += 40) {
          sampled++;
          if (img[p] > 0) nonEmpty++;
        }
      } catch (e) { out.push({ i, err: String(e) }); return; }
      out.push({ i, w: c.width, h: c.height, nonEmpty, sampled, ratio: sampled ? +(nonEmpty / sampled).toFixed(2) : 0 });
    });
    const wrap = document.querySelector('.chart-wrap');
    return JSON.stringify({ canvases: out, wrapHeight: wrap ? getComputedStyle(wrap).height : null });
  })()`,
  returnByValue: true,
})
console.log('--- canvas ---')
console.log(canvases.result?.value)
const styles = await send('Runtime.evaluate', {
  expression: `(() => {
    const t = document.querySelector('.stat-trend');
    const v = document.querySelector('.stat-value');
    return JSON.stringify({
      trendFont: t ? getComputedStyle(t).fontSize + '/' + getComputedStyle(t).fontWeight : null,
      statValueFont: v ? getComputedStyle(v).fontSize + '/' + getComputedStyle(v).fontWeight : null,
      chips: document.querySelectorAll('.weakness-chip').length,
    });
  })()`,
  returnByValue: true,
})
console.log('--- styles ---')
console.log(styles.result?.value)
console.log('--- events ---')
console.log(events.join('\n') || '(no errors)')
const hasPagination = /‹\s*1\s*2/.test(pageText) || /›/.test(pageText)
console.log('PAGINATION:', hasPagination ? 'PASS' : 'FAIL')

chrome.kill()
process.exit(0)
