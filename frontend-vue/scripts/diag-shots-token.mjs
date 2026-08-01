import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const BACKEND = 'https://127.0.0.1:18633'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOT_DIR = 'C:/Users/27644/.codex/visualizations/2026/08/01/019fbc9f-4ee5-7ba2-8a7c-a7bf4ab23ce7'
const token = process.env.MM_TOKEN
const email = process.env.MM_EMAIL || 'seed@test.dev'
const paths = (process.argv[2] || '/history,/custom,/finetune').split(',')

const userData = mkdtempSync(path.join(tmpdir(), 'mm-cdp-tok-'))
const chrome = spawn(CHROME, [
  '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--ignore-certificate-errors',
  `--user-data-dir=${userData}`, '--remote-debugging-port=9340', 'about:blank',
], { stdio: 'ignore' })
await new Promise((res) => setTimeout(res, 2500))

let r = await fetch('http://127.0.0.1:9340/json/new?' + encodeURIComponent(BACKEND + '/login'), { method: 'PUT' })
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
  expression: `localStorage.setItem('mockmate_auth_token', ${JSON.stringify(token)});
localStorage.setItem('mockmate_user_email', ${JSON.stringify(email)});
localStorage.setItem('mockmate_user_nickname', '种子用户'); 'ok'`,
})
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1200, deviceScaleFactor: 1, mobile: false })

for (const p of paths) {
  const file = 'tok-' + p.replace(/^\//, '').replace(/\//g, '_') + '.png'
  await send('Page.navigate', { url: BACKEND + p })
  await new Promise((res) => setTimeout(res, p === '/history' ? 4500 : 3000))
  const shot = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(path.join(SHOT_DIR, file), Buffer.from(shot.data, 'base64'))
  console.log('saved', file)
}
chrome.kill()
process.exit(0)
