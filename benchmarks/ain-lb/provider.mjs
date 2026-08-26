import { performance } from 'node:perf_hooks'
import { createHash } from 'node:crypto'

export function createProvider(opts = {}) {
  if (opts.mock) return { name: 'mock', generate: mockGenerate, isMock: true }
  return { name: providerName(), generate: httpGenerate, isMock: false }
}

export function isMockMode(flag, env = process.env) {
  return flag === true || flag === 'true' || !env.OPENAI_API_KEY
}

function providerName() {
  return process.env.AINLB_PROVIDER === '9router' ? '9router'
    : process.env.OPENAI_BASE_URL ? 'openai-compatible'
    : 'openai'
}

function seededRng(seed) {
  let a = parseInt(createHash('sha256').update(String(seed)).digest('hex').slice(0, 8), 16) || 1
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function mockGenerate(lang, taskId, _prompt, opts = {}) {
  const rng = seededRng(opts.seed ?? 'ain-lb')
  const c = lang === 'py' ? '#' : '//'
  const body = `${c} mock ${taskId} ${lang}\n` + langSkeleton(lang)
  return {
    text: body,
    tokens: Math.ceil(body.length / 4),
    elapsedMs: Math.round(40 + rng() * 60),
    isMock: true,
    lang,
  }
}

function langSkeleton(lang) {
  if (lang === 'py') return `def answer():\n    return 42\n`
  if (lang === 'rust') return `pub fn answer() -> i32 { 42 }\n`
  if (lang === 'lin') return `!answer(){^42}` + `\n=ex{answer}\n`
  return `export function answer(): number { return 42 }\n`
}

async function httpGenerate(lang, taskId, prompt, opts = {}) {
  const t0 = performance.now()
  const base = process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1'
  const model = process.env.OPENAI_MODEL || opts.model || 'gpt-4o-mini'
  const key = process.env.OPENAI_API_KEY
  const body = JSON.stringify({
    model,
    messages: [
      { role: 'system', content: `You are a benchmarked code generator. Target language: ${lang}. Reply with only code.` },
      { role: 'user', content: prompt },
    ],
    temperature: 0,
  })
  const maxTries = Number(process.env.AINLB_RETRIES || 10)
  const timeoutMs = Number(process.env.AINLB_TIMEOUT_MS || 120000)
  let res
  let lastErr = null
  for (let tryN = 0; tryN < maxTries; tryN += 1) {
    const ac = new AbortController()
    const timer = setTimeout(() => ac.abort(), timeoutMs)
    try {
      res = await fetch(`${base}/chat/completions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
        body,
        signal: ac.signal,
      })
      lastErr = null
    } catch (e) {
      lastErr = e
      res = null
    } finally {
      clearTimeout(timer)
    }
    if (res && res.ok) break
    let status = res?.status || 0
    let detail = ''
    if (res) detail = await res.text().catch(() => '')
    if (lastErr) status = lastErr.name === 'AbortError' ? 504 : 502
    const retryable = status === 429 || status >= 500
    if (retryable && tryN < maxTries - 1) {
      const wait = lastErr ? 2000 * (tryN + 1) : waitMs(detail, status, tryN)
      await sleep(wait)
      continue
    }
    throw new Error(`provider HTTP ${status || 'NET'}: ${(detail || lastErr?.message || '').slice(0, 200)}`)
  }
  if (!res || !res.ok) throw new Error('provider HTTP failed after retries')
  const data = await parseBody(res)
  const text = data?.choices?.[0]?.message?.content ?? ''
  const usage = data?.usage
  const elapsedMs = performance.now() - t0
  const tokens = usage?.total_tokens ?? Math.ceil(text.length / 4)
  return { text: stripFences(text), tokens, elapsedMs, isMock: false, lang }
}

function stripFences(text) {
  const m = String(text).match(/```[^\n]*\n([\s\S]*?)(?:```|$)/)
  return m ? m[1].trim() : String(text).trim()
}

function waitMs(detail, status, tryN) {
  const mStr = String(detail).match(/(?:reset after|try again in|retry after)\s*([0-9a-z\s\.]+)/i);
  if (mStr) {
    const raw = mStr[1];
    let totalSec = 0;
    const h = raw.match(/(\d+(?:\.\d+)?)\s*h/i);
    const m = raw.match(/(\d+(?:\.\d+)?)\s*m(?!s)/i);
    const s = raw.match(/(\d+(?:\.\d+)?)\s*s/i);
    if (h) totalSec += parseFloat(h[1]) * 3600;
    if (m) totalSec += parseFloat(m[1]) * 60;
    if (s) totalSec += parseFloat(s[1]);
    if (totalSec > 0) {
      const wait = Math.ceil(totalSec) * 1000 + 2000;
      console.log(`[RateLimit 429] Provider requested cooldown of ${Math.ceil(totalSec)}s. Waiting...`);
      return wait;
    }
  }
  if (status === 429) return Math.min(3000 * Math.pow(2, tryN), 30000);
  return 1000 * (tryN + 1);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function parseBody(res) {
  const raw = await res.text()
  // case 1: a single JSON object, possibly with a trailing `data: [DONE]` glued on
  try {
    const cleaned = raw.replace(/\s*data: \[DONE\]\s*$/, '').trim()
    return JSON.parse(cleaned)
  } catch { /* not a clean single JSON; try SSE below */ }
  // case 2: SSE stream of `data: {...}` lines (delta or full message chunks)
  let content = ''
  let usage = null
  for (const line of raw.split('\n')) {
    const t = line.trim()
    if (!t.startsWith('data:')) continue
    const payload = t.slice(5).trim()
    if (!payload || payload === '[DONE]') continue
    try {
      const j = JSON.parse(payload)
      const c = j.choices?.[0]
      if (c?.message?.content) content += c.message.content
      else if (c?.delta?.content) content += c.delta.content
      if (j.usage) usage = j.usage
    } catch { /* skip partial chunk */ }
  }
  return { choices: [{ message: { content } }], usage }
}
