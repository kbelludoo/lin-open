/**
 * run_b_vs_c.mjs
 *
 * Benchmark formal: Condição B (TypeScript) vs Condição C (LIN few-shot)
 * usando a infraestrutura existente do AIN-LB.
 *
 * Uso:
 *   OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
 *   OPENAI_MODEL=qwen2.5-coder:7b \
 *   node benchmarks/ain-lb/run_b_vs_c.mjs [--task T1,T2,T3] [--attempts 3] [--out report.txt]
 */

import { TASKS, RECOVERY_TASK, COLD_TASK } from './tasks/define.mjs'
import { createProvider } from './provider.mjs'
import { check } from './langcheck.mjs'
import { computeMetrics, modelVariance, repairEfficiency, compressionRatio, round } from './metrics.mjs'
import { withLINGrammar } from './lin_grammar_injector.mjs'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __here = dirname(fileURLToPath(import.meta.url))

const OLLAMA_BASE = process.env.OPENAI_BASE_URL?.replace('/v1', '') || 'http://127.0.0.1:11434'
const MODEL = process.env.OPENAI_MODEL || 'qwen2.5-coder:7b'

// ── helpers ──────────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const o = { attempts: 3, tasks: ['T1', 'T2', 'T3'], out: null }
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--task' || argv[i] === '--tasks') o.tasks = argv[i + 1].split(',')
    if (argv[i] === '--attempts') o.attempts = Number(argv[i + 1])
    if (argv[i] === '--out') o.out = argv[i + 1]
  }
  return o
}

function taskFor(key) {
  if (key === 'T0') return RECOVERY_TASK
  if (key === 'T7') return COLD_TASK
  return TASKS[key]
}

async function unloadModel() {
  try {
    await fetch(`${OLLAMA_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: MODEL, prompt: '', keep_alive: 0 }),
    })
  } catch { /* ignore */ }
  await new Promise(r => setTimeout(r, 2000))
}

function bar(n, max = 60) {
  const filled = Math.round((n / Math.max(max, 1)) * 20)
  return '[' + '█'.repeat(filled) + '░'.repeat(20 - filled) + ']'
}

// ── core: run one condition ───────────────────────────────────────────────────

async function runCondition(label, lang, taskKeys, attempts, specTransform) {
  const provider = createProvider({ mock: false })
  const allRuns = []

  console.log(`\n${'─'.repeat(60)}`)
  console.log(`Condição ${label} — Language: ${lang.toUpperCase()} | Model: ${MODEL}`)
  console.log(`Tasks: ${taskKeys.join(', ')} | Attempts: ${attempts}`)
  console.log('─'.repeat(60))

  for (const key of taskKeys) {
    const task = taskFor(key)
    if (!task) { console.log(`  [skip] unknown task ${key}`); continue }

    for (let n = 0; n < attempts; n++) {
      const attemptLabel = `  [${key} attempt ${n + 1}/${attempts}]`
      process.stdout.write(`${attemptLabel} generating...`)

      const rawSpec = task.spec(lang)
      const spec = specTransform ? specTransform(rawSpec) : rawSpec

      try {
        const gen = await provider.generate(lang, task.id, spec)
        process.stdout.write(` ${gen.tokens} tok, ${(gen.elapsedMs / 1000).toFixed(1)}s → checking...`)

        const ck = check(lang, gen.text)
        const status = ck.ok ? '✅ PASS' : `❌ FAIL (${ck.stage}: ${(ck.reason || '').slice(0, 60)})`
        console.log(` ${status}`)

        allRuns.push({
          task: key, lang, attempt: n + 1,
          tokens: gen.tokens, elapsedMs: gen.elapsedMs,
          check: ck,
        })
      } catch (e) {
        console.log(` ⚠️  ERROR: ${e.message.slice(0, 80)}`)
        allRuns.push({ task: key, lang, attempt: n + 1, tokens: 0, elapsedMs: 0, check: { ok: false, stage: 'HARNESS_ERROR', reason: e.message } })
      }
    }
  }

  const metrics = computeMetrics(allRuns, {})
  const variance = modelVariance(allRuns)
  const repair = repairEfficiency(allRuns)

  // token efficiency = pass@1 * 1000 / tokens_per_task  (higher is better)
  const tokenEfficiency = metrics.raw.tokens_per_task > 0
    ? round(metrics.raw.first_pass * 1000 / metrics.raw.tokens_per_task, 4)
    : 0

  return { label, lang, metrics, variance, repair, tokenEfficiency, allRuns }
}

// ── report formatter ─────────────────────────────────────────────────────────

function renderComparison(b, c) {
  const lines = []
  const sep = '═'.repeat(64)
  const hr  = '─'.repeat(64)

  lines.push(sep)
  lines.push('  AIN-LB BENCHMARK: CONDIÇÃO B vs C')
  lines.push(`  Model: ${MODEL}`)
  lines.push(`  Tasks: ${b.allRuns.map(r => r.task).filter((v,i,a)=>a.indexOf(v)===i).join(', ')}`)
  lines.push(sep)
  lines.push('')

  const col = (v, w = 16) => String(v).padStart(w)

  lines.push(`${'Métrica'.padEnd(32)}${col('B (TypeScript)')}${col('C (LIN few-shot)')}`)
  lines.push(hr)

  const m = (label, bVal, cVal, better = 'higher') => {
    const bv = String(bVal)
    const cv = String(cVal)
    const bNum = parseFloat(bVal)
    const cNum = parseFloat(cVal)
    let indicator = ''
    if (!isNaN(bNum) && !isNaN(cNum) && bNum !== cNum) {
      const cBetter = better === 'higher' ? cNum > bNum : cNum < bNum
      indicator = cBetter ? ' ✅' : ' ⚠️'
    }
    lines.push(`${label.padEnd(32)}${col(bv)}${col(cv + indicator)}`)
  }

  m('pass@1 (first_pass)', b.metrics.raw.first_pass, c.metrics.raw.first_pass)
  m('Reliability', b.metrics.raw.reliability, c.metrics.raw.reliability)
  m('Tokens / task (avg)', b.metrics.raw.tokens_per_task, c.metrics.raw.tokens_per_task, 'lower')
  m('Latency / task (ms)', Math.round(b.metrics.raw.elapsed_ms / Math.max(b.allRuns.length,1)), Math.round(c.metrics.raw.elapsed_ms / Math.max(c.allRuns.length,1)), 'lower')
  m('Total tokens', b.metrics.raw.tokens, c.metrics.raw.tokens, 'lower')
  m('Token Efficiency (×1000)', b.tokenEfficiency, c.tokenEfficiency)
  m('Context Efficiency', b.metrics.raw.context_efficiency, c.metrics.raw.context_efficiency)
  m('AIN-LB Composite Score', b.metrics.composite, c.metrics.composite)

  lines.push(hr)
  lines.push('')

  // compression
  if (b.metrics.raw.tokens_per_task > 0 && c.metrics.raw.tokens_per_task > 0) {
    const ratio = round(b.metrics.raw.tokens_per_task / c.metrics.raw.tokens_per_task, 2)
    const pct = round((1 - c.metrics.raw.tokens_per_task / b.metrics.raw.tokens_per_task) * 100, 1)
    lines.push(`  Compression ratio B/C: x${ratio}`)
    lines.push(`  Token reduction:       ${pct}% fewer tokens in C (LIN)`)
    lines.push('')
  }

  // repair efficiency
  lines.push('  [Repair Efficiency]')
  lines.push(`  B: ${b.repair.attempts_until_success} attempts, ${b.repair.tokens_until_success} tokens until 1st pass (${b.repair.succeeded ? 'succeeded' : 'never passed'})`)
  lines.push(`  C: ${c.repair.attempts_until_success} attempts, ${c.repair.tokens_until_success} tokens until 1st pass (${c.repair.succeeded ? 'succeeded' : 'never passed'})`)
  lines.push('')

  // variance
  lines.push('  [Model Variance]')
  lines.push(`  B pass rate: ${b.variance.pass_rate} | std dev: ${b.variance.std_dev} | median tokens: ${b.variance.median_tokens}`)
  lines.push(`  C pass rate: ${c.variance.pass_rate} | std dev: ${c.variance.std_dev} | median tokens: ${c.variance.median_tokens}`)
  lines.push('')

  // interpretation
  lines.push('  [Interpretation]')
  const bEff = b.tokenEfficiency
  const cEff = c.tokenEfficiency
  if (c.metrics.raw.first_pass >= b.metrics.raw.first_pass && c.metrics.raw.tokens_per_task < b.metrics.raw.tokens_per_task) {
    lines.push('  → LIN DOMINANTE: mais compacto E igual ou melhor taxa de compilação')
  } else if (cEff > bEff) {
    lines.push('  → LIN TOKEN-EFFICIENT: maior eficiência apesar de menor taxa absoluta de compilação')
    lines.push('    (few-shot insuficiente — LoRA ou mais exemplos podem resolver)')
  } else if (c.metrics.raw.first_pass < 0.3) {
    lines.push('  → ⚠️  LIN PASS@1 < 30%: refinar gramática few-shot antes de escalar')
  } else {
    lines.push('  → Resultado inconclusivo: ampliar amostra (mais tarefas ou attempts)')
  }

  lines.push('')
  lines.push(sep)

  return lines.join('\n')
}

// ── main ─────────────────────────────────────────────────────────────────────

async function main() {
  const opts = parseArgs(process.argv.slice(2))

  console.log('╔══════════════════════════════════════════════════════════════╗')
  console.log('║   AIN-LB: BENCHMARK FORMAL B vs C                           ║')
  console.log('║   B = TypeScript (baseline)                                  ║')
  console.log('║   C = LIN (com gramática few-shot injetada)                  ║')
  console.log('╚══════════════════════════════════════════════════════════════╝')
  console.log(`\n  Model:    ${MODEL}`)
  console.log(`  Tasks:    ${opts.tasks.join(', ')}`)
  console.log(`  Attempts: ${opts.attempts}`)
  console.log(`  Timeout:  ${process.env.AINLB_TIMEOUT_MS || 120000}ms`)

  // Unload any existing model
  console.log('\n🔄 Descarregando modelos da VRAM...')
  await unloadModel()
  console.log('✅ VRAM limpa')

  // ── Condição B: TypeScript ────────────────────────────────────────────────
  const resultB = await runCondition('B', 'ts', opts.tasks, opts.attempts, null)

  // Unload before condition C
  console.log('\n🔄 Descarregando modelo para condição C...')
  await unloadModel()

  // ── Condição C: LIN com gramática ─────────────────────────────────────────
  const resultC = await runCondition('C', 'lin', opts.tasks, opts.attempts, withLINGrammar)

  // ── Relatório ─────────────────────────────────────────────────────────────
  const report = renderComparison(resultB, resultC)
  console.log('\n\n' + report)

  if (opts.out) {
    const dest = resolve(opts.out)
    mkdirSync(dirname(dest), { recursive: true })
    writeFileSync(dest, report + '\n')
    console.log(`\nreport → ${dest}`)
  }
}

await main()
