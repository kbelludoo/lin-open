import { TASKS, RECOVERY_TASK, COLD_TASK, LANGUAGES } from './tasks/define.mjs'
import { createProvider } from './provider.mjs'
import { check } from './langcheck.mjs'
import { computeMetrics, modelVariance, repairEfficiency, compressionRatio } from './metrics.mjs'
import { createBlindRun, unmap } from './blind.mjs'
import { runCCR } from './ccr.mjs'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __here = dirname(fileURLToPath(import.meta.url))
const HELP = `
AIN-LB runner
  node benchmarks/ain-lb/runner.mjs [options]

Modes:
  default   run tasks per language, toolchain-check each submission
  --blind   anonymize submissions into candidate_A..D before judging

Options:
  --language <py|ts|rust|lin>  languages (default: py|ts|rust)
  --task <T1..T6|T0>           run a single task (default: all)
  --attempts <n>               tries per task (default: 3)
  --mock                       deterministic provider (no API key needed)
  --blind                      anonymize before judging
  --ccr                        run T8 Catastrophic Context Loss Recovery
  --ccr-layer <1|2|3|4>        run a single CCR layer
  --ccr-keep <0..1>            fraction of files kept after amnesia (default 0.5)
  --ccr-small                  use compact build (calibration) instead of full T1 fixture
  --seed <s>                   shuffle seed for blind mode
  --trad-tokens <n>            traditional tokens (compression ratio)
  --lin-tokens <n>             LIN tokens (compression ratio)
  --out <path>                 write report file
`

function parseArgs(argv) {
  const o = { attempts: 3, tasks: null, langs: null, mock: false, blind: false, ccr: false, ccrLayer: null, ccrKeep: 0.5, ccrSmall: false, seed: 'ain-lb', out: null, tradTokens: null, linTokens: null, model: process.env.OPENAI_MODEL || 'api' }
  for (let i = 0; i < argv.length; i += 1) {
    const k = argv[i]
    const v = argv[i + 1]
    if (k === '--language') o.langs = v.split(',')
    else if (k === '--task') o.tasks = v.split(',')
    else if (k === '--attempts') o.attempts = Number(v)
    else if (k === '--mock') o.mock = true
    else if (k === '--blind') o.blind = true
    else if (k === '--ccr') o.ccr = true
    else if (k === '--ccr-layer') o.ccrLayer = Number(v)
    else if (k === '--ccr-keep') o.ccrKeep = Number(v)
    else if (k === '--ccr-small') o.ccrSmall = true
    else if (k === '--seed') o.seed = v
    else if (k === '--trad-tokens') o.tradTokens = Number(v)
    else if (k === '--lin-tokens') o.linTokens = Number(v)
    else if (k === '--out') o.out = v
    else if (k === '--model') o.model = v
    else if (k === '--help') o.help = true
  }
  return o
}

function taskFor(key) {
  if (key === 'T0') return RECOVERY_TASK
  if (key === 'T7') return COLD_TASK
  return TASKS[key]
}

function taskKeys(opts) {
  return opts.tasks && opts.tasks.length ? opts.tasks : ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T0', 'T7']
}

async function standardMode(opts) {
  const provider = createProvider({ mock: opts.mock })
  const compression = compressionOpt(opts)
  const out = []
  for (const lang of opts.langs) {
    const allRuns = []
    const recoveryFlags = []
    for (const key of taskKeys(opts)) {
      const task = taskFor(key)
      if (!task) continue
      for (let n = 0; n < opts.attempts; n += 1) {
        const gen = await provider.generate(lang, task.id, task.spec(lang), { mock: opts.mock, seed: opts.seed })
        const ck = check(lang, gen.text)
        allRuns.push({ task: key, lang, attempt: n + 1, tokens: gen.tokens, elapsedMs: gen.elapsedMs, check: ck })
      }
      if (key === 'T0') recoveryFlags.push(allRuns.slice(-opts.attempts).some((r) => r.check?.ok === true))
    }
    const metrics = computeMetrics(allRuns, { recoveryPass: recoveryFlags.some(Boolean) })
    const variance = modelVariance(allRuns)
    const repair = repairEfficiency(allRuns)
    out.push(renderStandard(lang, metrics, variance, repair, { ...opts, compression }))
  }
  return out.join('\n\n')
}

async function blindMode(opts) {
  const provider = createProvider({ mock: opts.mock })
  const keys = taskKeys(opts)
  const lines = []
  lines.push('AIN-LB BLIND REPORT')
  lines.push('='.repeat(32))
  lines.push(`seed: ${opts.seed}`)
  lines.push('')
  const byLang = {}
  for (const key of keys) {
    const task = taskFor(key)
    if (!task) continue
    // one blind run per task: N language representations of the SAME task -> candidate_A..N
    const subs = []
    for (const lang of opts.langs) {
      const gen = await provider.generate(lang, task.id, task.spec(lang), { mock: opts.mock, seed: `${opts.seed}-${lang}-${key}` })
      subs.push({ lang, task: key, text: gen.text })
    }
    const blind = createBlindRun(subs, `${opts.seed}-${key}`)
    lines.push(`TASK ${key} (${task.name})`)
    for (const c of blind.candidates) lines.push(`  ${c.label} -> ${c.lang}`)
    const judged = []
    for (const c of blind.candidates) {
      const judge = await provider.generate('BLIND', c.task, judgePrompt(c), { mock: opts.mock, seed: `${opts.seed}-${c.label}` })
      judged.push({ label: c.label, task: c.task, tokens: judge.tokens, elapsedMs: judge.elapsedMs, check: { ok: judge.text.trim().length > 0 } })
    }
    const perTask = unmap(judged, blind.map)
    for (const [lang, runs] of Object.entries(perTask)) {
      byLang[lang] ??= []
      byLang[lang].push(...runs)
    }
  }
  lines.push('')
  for (const [lang, runs] of Object.entries(byLang)) {
    const metrics = computeMetrics(runs, { recoveryPass: runs.some((r) => r.check?.ok === true) })
    const variance = modelVariance(runs)
    lines.push(renderStandard(lang, metrics, variance, { ...opts, model: `${provider.name} (blind)` }))
    lines.push('')
  }
  return lines.join('\n')
}

function judgePrompt(c) {
  const t = taskFor(c.task)
  return `You are judging an ANONYMIZED software representation labeled "${c.label}". Its real language is hidden from you.\n\nTask: ${t.name}\n\nApply the task to this representation. Do not assume any language based on syntax; treat it as an opaque artifact. Return a result and a confidence score 0..1.\n\nARTIFACT:\n${c.text}`
}

function compressionOpt(opts) {
  return opts.linTokens && opts.tradTokens
    ? { lin: opts.linTokens, trad: opts.tradTokens, ratio: compressionRatio(opts.linTokens, opts.tradTokens) }
    : null
}

function renderStandard(lang, metrics, variance, repair, opts) {
  const lines = []
  lines.push('AIN-LB REPORT')
  lines.push('='.repeat(28))
  lines.push(`Language:        ${lang}${opts.mock ? ' (mock)' : ''}`)
  lines.push(`Model:           ${opts.model}`)
  lines.push(`Attempts:        ${metrics.raw.attempts}`)
  lines.push(`Passing checks:  ${metrics.raw.passing}`)
  lines.push('')
  lines.push(`Tokens:          ${metrics.raw.tokens}`)
  lines.push(`Tokens/task:     ${metrics.raw.tokens_per_task}`)
  lines.push(`Elapsed (ms):    ${metrics.raw.elapsed_ms}`)
  lines.push('')
  lines.push(`First-pass rate:         ${metrics.raw.first_pass}`)
  lines.push(`Reliability:             ${metrics.raw.reliability}`)
  lines.push(`Context efficiency:      ${metrics.raw.context_efficiency}`)
  lines.push(`Semantic recovery (T0):  ${metrics.raw.semantic_recovery}`)
  lines.push(`Regression stability:    ${metrics.raw.regression_stability}`)
  if (repair) {
    lines.push(`[Repair efficiency]`)
    lines.push(`  attempts until success: ${repair.attempts_until_success}`)
    lines.push(`  tokens until success:   ${repair.tokens_until_success}`)
    lines.push(`  time until success:     ${repair.time_ms}ms`)
  }
  if (variance) {
    lines.push(`[Model variance]`)
    lines.push(`  pass rate:   ${variance.pass_rate}`)
    lines.push(`  std dev:     ${variance.std_dev}`)
    lines.push(`  median tok:  ${variance.median_tokens}`)
  }
  if (opts.compression) lines.push(`Compression ratio:       ${opts.compression.trad}/${opts.compression.lin} = x${opts.compression.ratio}`)
  lines.push('')
  lines.push(`AI_DEVELOPMENT_SCORE:    ${metrics.composite}`)
  lines.push('='.repeat(28))
  return lines.join('\n')
}

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  if (opts.help) { console.log(HELP); return }
  opts.langs = opts.langs && opts.langs.length ? opts.langs : LANGUAGES
  const joined = opts.ccr ? await runCCR(opts) : opts.blind ? await blindMode(opts) : await standardMode(opts)
  console.log(joined)
  if (opts.out) {
    const dest = resolve(opts.out)
    mkdirSync(dirname(dest), { recursive: true })
    writeFileSync(dest, joined + '\n')
    console.log(`\nreport -> ${dest}`)
  }
}

await main()
