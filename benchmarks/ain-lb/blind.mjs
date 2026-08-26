import { createHash } from 'node:crypto'

// Anonymize submissions so the judged model never sees the language label.
// Only the orchestrator/evaluator holds the secret map. (R4)
export function createBlindRun(submissions, seed) {
  const items = submissions.map((s) => ({ lang: s.lang, task: s.task, text: s.text }))
  shuffle(items, seed)
  const labels = items.map((_, i) => `candidate_${String.fromCharCode(65 + i)}`)
  const map = {}
  const candidates = items.map((it, i) => {
    map[labels[i]] = it.lang
    return { label: labels[i], task: it.task, lang: it.lang, text: it.text }
  })
  return { candidates, map, seed }
}

export function unmap(results, map) {
  const byLang = {}
  for (const r of results) {
    const lang = map[r.label]
    if (!lang) continue
    byLang[lang] ??= []
    byLang[lang].push(r)
  }
  return byLang
}

function shuffle(arr, seed) {
  const rng = seededRng(seed)
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
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
