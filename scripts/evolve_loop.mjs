#!/usr/bin/env node
/** LIA auto-improve / auto-evolve bootstrap. Spec: spec/LIA_AUTONOMY.dicel
 *  Mutates compiler candidates only; never edits .lia to hide emit bugs.
 *  LIA must stay >= Dicel (gate).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STORAGE = path.join(ROOT, 'storage');
const LEDGER = path.join(STORAGE, 'lia_ledger.dicel');
const TRAUMA = path.join(STORAGE, 'lia_trauma.dicel');

function appendDicelEntry(file, block) {
  const prev = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
  const stamp = new Date().toISOString();
  const entry = `\n@E{t="${stamp}" ${block}}\n`;
  fs.appendFileSync(file, entry, 'utf8');
  return { file, stamp };
}

function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8', shell: true });
  return { status: r.status ?? 1, out: (r.stdout || '') + (r.stderr || '') };
}

function autonomyStatus() {
  const files = ['lia_ledger.dicel', 'lia_trauma.dicel', 'lia_knowledge.dicel', 'lia_hypotheses.dicel'];
  const mem = {};
  for (const f of files) {
    const p = path.join(STORAGE, f);
    mem[f] = fs.existsSync(p) ? fs.statSync(p).size : 0;
  }
  const tests = run('npm', ['test']);
  const multi = run('npm', ['run', 'test:multi']);
  return {
    status: 'AUTONOMY_BOOTSTRAP',
    goal: 'LIA_supersedes_Dicel_plus_auto_improve_evolve',
    gate: 'LIA_ge_Dicel',
    memory_bytes: mem,
    npm_test: tests.status === 0 ? 'PASS' : 'FAIL',
    multi_emit: multi.status === 0 ? 'PASS' : 'FAIL',
    next: ['persist_trauma_on_fail', 'candidate_compiler_patches', 'vs_dicel_bench'],
  };
}

function improveOnce() {
  const smoke = run('node', ['scripts/self_repair.mjs', '--smoke']);
  const ok = smoke.status === 0;
  appendDicelEntry(LEDGER, `kind=improve ok=${ok} path=self_repair_smoke`);
  if (!ok) {
    appendDicelEntry(TRAUMA, `class=SELF_REPAIR_SMOKE note="see self_repair out" fix_target=compiler_not_lia`);
  }
  return { status: ok ? 'IMPROVE_OK' : 'IMPROVE_FAIL', ledger: LEDGER, out: smoke.out.slice(0, 500) };
}

function evolveOnce() {
  // Phase0: verify baseline; no core mutate. Candidates dir reserved.
  const candDir = path.join(ROOT, 'candidates');
  if (!fs.existsSync(candDir)) fs.mkdirSync(candDir, { recursive: true });
  const base = autonomyStatus();
  const ok = base.npm_test === 'PASS' && base.multi_emit === 'PASS';
  appendDicelEntry(LEDGER, `kind=evolve_epoch ok=${ok} promote=none mutate=candidates_only`);
  return {
    status: ok ? 'EVOLVE_EPOCH_GREEN' : 'EVOLVE_EPOCH_BLOCKED',
    gate: 'LIA_ge_Dicel',
    promote: [],
    note: 'no_promote_without_Hypothesis_prove_gates; fix_compiler_on_fail',
    baseline: base,
  };
}

const cmd = process.argv[2] || 'status';
let result;
if (cmd === 'status' || cmd === 'autonomy-status') result = autonomyStatus();
else if (cmd === 'improve') result = improveOnce();
else if (cmd === 'evolve') result = evolveOnce();
else {
  console.error('usage: node scripts/evolve_loop.mjs <status|improve|evolve>');
  process.exit(2);
}
console.log(JSON.stringify(result, null, 2));
process.exit(result.status && String(result.status).includes('FAIL') ? 1 : 0);
