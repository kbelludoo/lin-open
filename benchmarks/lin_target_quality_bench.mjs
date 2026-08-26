#!/usr/bin/env node
/**
 * LIN Target Quality Benchmark
 * FULL = compile+run PASS on all 7 real nucleus langs. COMPILE_ONLY is not done.
 * Rank only after every nucleus lang is FULL. INTEL/stub auto-PASS is forbidden.
 * fastest = wall-clock (C may win). best_in_memory / systems_pick = rust.
 * C is memory=unsafe, compile+run gate only — not the in-process LIN host.
 * Wipes .lin_quality_work each run.
 */
import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { spawnSync } from 'node:child_process';
import { compileLia } from '../src/multi_emit.mjs';
import { ensureToolchains } from './ensure_toolchains.mjs';
import {
  realNucleusLangs, refuseStubBenchmark, benchWarmupCount, benchRepeatCount,
  allRowsFull, rankQualityRows, futurePickBestLang,
} from './clone_lin_full_repo_gate.mjs';

ensureToolchains({ quiet: true });

const WIN = process.platform === 'win32';
const linCode = fs.readFileSync('tests/target_quality.lin', 'utf8');
const targets = realNucleusLangs().filter((t) => !refuseStubBenchmark(t));
const workRoot = path.join(process.cwd(), '.lin_quality_work');
const WARMUP = Number(benchWarmupCount()) || 2;
const REPEATS = Number(benchRepeatCount()) || 9;
fs.rmSync(workRoot, { recursive: true, force: true });

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, {
    encoding: 'utf8',
    timeout: opts.timeout || 60_000,
    shell: opts.shell ?? false,
    env: opts.env || process.env,
    cwd: opts.cwd,
    windowsHide: true,
  });
  const err = r.error ? String(r.error.message || r.error) : '';
  const out = `${r.stdout || ''}${r.stderr || ''}${err ? `\n${err}` : ''}`.slice(0, 800);
  return { status: r.status, out, error: err };
}

function runLooksOk(out) {
  const t = String(out || '');
  if (!t.includes('3628800')) return false;
  if (!t.includes('5050')) return false;
  if (!/\b64\b/.test(t)) return false;
  if (!/\b10\b/.test(t)) return false;
  return /false|False|\b0\b/.test(t);
}

function median(xs) {
  const a = [...xs].sort((x, y) => x - y);
  return a[Math.floor(a.length / 2)];
}

function timeRuns(runOnce, warmup, repeats) {
  for (let i = 0; i < warmup; i++) runOnce();
  const samples = [];
  let last = null;
  for (let i = 0; i < repeats; i++) {
    const t0 = performance.now();
    last = runOnce();
    samples.push(performance.now() - t0);
  }
  return { ms: median(samples), last, samples };
}

function extFor(target) {
  if (target === 'js') return 'cjs';
  if (target === 'ts') return 'ts';
  if (target === 'py') return 'py';
  if (target === 'rust') return 'rs';
  if (target === 'go') return 'go';
  if (target === 'c') return 'c';
  return 'java';
}

function prepareTarget(target, code) {
  const work = path.join(workRoot, target);
  fs.mkdirSync(work, { recursive: true });
  let fileName = `bench.${extFor(target)}`;
  if (target === 'java') {
    const m = code.match(/public class ([A-Za-z][A-Za-z0-9]*)/);
    if (m) fileName = `${m[1]}.java`;
  }
  const filePath = path.join(work, fileName);
  fs.writeFileSync(filePath, code, 'utf8');

  let compileOk = false;
  let detail = '';
  let runOnce = () => ({ status: 1, out: 'not_prepared' });

  if (target === 'js' || target === 'ts') {
    let jsFile = filePath;
    if (target === 'ts') {
      const tscPath = path.join(process.cwd(), 'node_modules', 'typescript', 'bin', 'tsc');
      const r1 = run('node', [tscPath, '--target', 'es2020', '--module', 'commonjs', '--outDir', work, filePath]);
      compileOk = r1.status === 0;
      detail = r1.out;
      jsFile = path.join(work, path.basename(fileName, '.ts') + '.js');
      const cjsFile = path.join(work, 'bench.cjs');
      if (compileOk && fs.existsSync(jsFile)) {
        fs.copyFileSync(jsFile, cjsFile);
        jsFile = cjsFile;
      }
    } else {
      compileOk = true;
    }
    const runner = path.join(work, 'run_quality.cjs');
    const reqName = path.basename(jsFile);
    fs.writeFileSync(runner, `'use strict';
const m = require('./${reqName}');
const f = m.default && m.default.factorial ? m.default : m;
const d = f.double_ || f.double;
console.log(JSON.stringify([f.factorial(10), f.isEven(7), f.sumTo(100), f.square(8), d(5)]));
`, 'utf8');
    runOnce = () => run('node', [runner], { cwd: work });
  } else if (target === 'py') {
    const r1 = run('python', ['-m', 'py_compile', filePath], { shell: WIN });
    compileOk = r1.status === 0;
    detail = r1.out;
    const runner = path.join(work, 'run_quality.py');
    fs.writeFileSync(runner, `import importlib.util
spec = importlib.util.spec_from_file_location("m", "bench.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ie = getattr(mod, "is_even", None) or getattr(mod, "isEven")
st = getattr(mod, "sum_to", None) or getattr(mod, "sumTo")
d = getattr(mod, "double_", None) or getattr(mod, "double")
print(mod.factorial(10), ie(7), st(100), mod.square(8), d(5))
`, 'utf8');
    runOnce = () => run('python', [runner], { cwd: work, shell: WIN });
  } else if (target === 'go') {
    fs.writeFileSync(path.join(work, 'go.mod'), 'module bench\n\ngo 1.22\n');
    const r1 = run('go', ['build', '-o', WIN ? 'bench.exe' : 'bench', 'bench.go'], { cwd: work, shell: WIN });
    compileOk = r1.status === 0;
    detail = r1.out;
    const exe = path.join(work, WIN ? 'bench.exe' : 'bench');
    runOnce = () => run(exe, [], { cwd: work });
  } else if (target === 'rust') {
    const exe = path.join(work, WIN ? 'bench.exe' : 'bench');
    const r1 = run('rustc', [filePath, '-o', exe, '--cap-lints', 'allow'], { shell: WIN });
    compileOk = r1.status === 0;
    detail = r1.out;
    runOnce = () => run(exe, [], { cwd: work });
  } else if (target === 'c') {
    const exe = path.join(work, WIN ? 'bench.exe' : 'bench');
    const r1 = run('gcc', ['-std=gnu11', filePath, '-o', exe], { shell: WIN });
    compileOk = r1.status === 0;
    detail = r1.out;
    runOnce = () => run(exe, [], { cwd: work });
  } else if (target === 'java') {
    const r1 = run('javac', [filePath], { shell: WIN });
    compileOk = r1.status === 0;
    detail = r1.out;
    const className = path.basename(fileName, '.java');
    runOnce = () => run('java', ['-cp', work, className], { shell: WIN });
  }

  return { compileOk, detail, bytes: Buffer.byteLength(code, 'utf8'), runOnce };
}

function checkTarget(target, code) {
  const prep = prepareTarget(target, code);
  let runOk = false;
  let ms = 0;
  let detail = prep.detail;
  if (prep.compileOk) {
    const first = prep.runOnce();
    detail = first.out || detail;
    runOk = first.status === 0 && runLooksOk(first.out);
    if (target === 'js') prep.compileOk = first.status === 0;
    if (runOk) {
      const timed = timeRuns(prep.runOnce, WARMUP, REPEATS);
      runOk = timed.last && timed.last.status === 0 && runLooksOk(timed.last.out);
      ms = runOk ? timed.ms : 0;
      detail = (timed.last && timed.last.out) || detail;
    }
  }
  return { lang: target, compileOk: prep.compileOk, runOk, ms, bytes: prep.bytes, detail };
}

console.log('====================================================================');
console.log('LIN TARGET QUALITY BENCHMARK');
console.log(`warmup=${WARMUP} repeats=${REPEATS} (median wall ms of run)`);
console.log('====================================================================\n');

const rows = [];
for (const t of targets) {
  const emitted = compileLia(linCode, { target: t, stubRuntime: false });
  const code = emitted.code || '';
  const check = checkTarget(t, code);
  rows.push(check);
}

const full = allRowsFull(rows);
if (!full) {
  console.log('| lang   | compile | run  | ms | bytes | note         |');
  console.log('|--------|---------|------|----|-------|--------------|');
  for (const s of rows) {
    const note = s.compileOk && s.runOk ? 'FULL' : s.compileOk ? 'COMPILE_ONLY' : 'FAIL';
    console.log(`| ${s.lang.padEnd(6)} | ${s.compileOk ? 'PASS' : 'FAIL'}    | ${s.runOk ? 'PASS' : 'FAIL'} | — | ${String(s.bytes).padStart(5)} | ${note.padEnd(12)} |`);
  }
  console.log('\nNOT_FULL: every nucleus lang must compile AND run before rank. Fix emitters/harness.');
  for (const s of rows) {
    if (!s.compileOk || !s.runOk) console.log(`${s.lang}: ${String(s.detail || '').slice(0, 240)}`);
  }
  process.exit(1);
}

const ranked = rankQualityRows(rows);
const pick = futurePickBestLang({ rows: ranked });

console.log('| lang   | compile | run  | ms     | bytes | rank |');
console.log('|--------|---------|------|--------|-------|------|');
for (const s of ranked) {
  console.log(`| ${s.lang.padEnd(6)} | PASS    | PASS | ${Number(s.ms).toFixed(2).padStart(6)} | ${String(s.bytes).padStart(5)} | ${String(s.rank).padStart(4)} |`);
}

console.log('\n====================================================================');
if (pick.status === 'MEASURED') {
  console.log(`FASTEST: ${pick.fastest}  ${Number(pick.fastest_ms).toFixed(2)}ms  ${pick.fastest_bytes} bytes  (wall-clock; C may win)`);
  console.log(`BEST_IN_MEMORY: ${pick.best_in_memory}  systems_pick=${pick.systems_pick}  memory_winner=${pick.memory_winner}`);
  console.log(`IN_MEMORY_HOST: ${pick.in_memory_host}  runtime_winner=${pick.runtime_winner}  c_memory=${pick.c_memory}`);
  console.log('C is compile+run gate/portability only; not the in-process LIN host. Speed does not make C the best option.');
  console.log(`CLI default remains ${pick.prefer_until_bench || 'ts'} (clone/behavior_eq).`);
} else {
  console.log(`pick status=${pick.status} — no winner`);
  process.exit(1);
}
console.log('====================================================================');
