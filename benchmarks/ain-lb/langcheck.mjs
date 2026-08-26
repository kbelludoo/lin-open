import { spawnSync } from 'node:child_process'
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { createRequire } from 'node:module'
import { compileLia } from '../../src/multi_emit.mjs'

const gate = createRequire(import.meta.url)('../../src/lin_semantic_gate.compiled.cjs')

export function check(lang, code, opts = {}) {
  return lang === 'lin' ? checkLin(code, opts) : checkSyntax(lang, code)
}

export function checkLin(source, opts = {}) {
  const target = opts.target || 'ts'
  // stage 1: LIN semantic diagnostics (effects/refinement/data-race)
  const g = gate
  const gateResult = g.semanticGate(source)
  if (!gateResult.valid) {
    return { ok: false, stage: 'LIN_SEMANTIC', reason: (gateResult.errors || []).join('; ').slice(0, 200) }
  }
  // stage 2: compile + formal gate to target
  let code
  try {
    const res = compileLia(source, { target })
    code = res.code
  } catch (e) {
    return { ok: false, stage: 'LIN_COMPILE', reason: String(e && e.message || e).slice(0, 200) }
  }
  // stage 3: toolchain-check the generated target
  const t = checkSyntax(target, code)
  return { ok: t.ok, stage: t.ok ? 'LIN_EMIT_TS' : 'LIN_EMIT_TS_FAIL', reason: t.reason, target }
}

export function checkSyntax(lang, code) {
  const dir = mkdtempSync(join(tmpdir(), 'ainlb-'))
  try {
    const file = join(dir, `probe.${extFor(lang)}`)
    writeFileSync(file, code)
    return runCheck(lang, file)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

function extFor(lang) {
  return lang === 'py' ? 'py' : lang === 'rust' ? 'rs' : 'ts'
}

function runCheck(lang, file) {
  const cmd = cmdFor(lang, file)
  if (!cmd) return { ok: false, reason: 'no-toolchain' }
  const r = spawnSync(cmd.bin, cmd.args, { encoding: 'utf8', timeout: 30000, shell: false })
  return { ok: r.status === 0, reason: r.status === 0 ? 'ok' : (r.stderr || r.stdout || '').slice(0, 200).trim() }
}

function cmdFor(lang, file) {
  if (lang === 'py') return { bin: 'python', args: ['-m', 'py_compile', file] }
  if (lang === 'rust') return { bin: 'rustc', args: ['--edition', '2021', '--crate-type', 'lib', file, '-o', `${file}.rlib`] }
  if (lang === 'ts') return { bin: process.execPath, args: [tscBin(), '--noEmit', '--skipLibCheck', '--target', 'es2020', '--module', 'esnext', file] }
  return null
}

function tscBin() {
  return resolve(process.cwd(), 'node_modules', 'typescript', 'bin', 'tsc')
}
