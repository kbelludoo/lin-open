/**
 * Golden: examples/safe-compare.lia → js|ts|py|go|rust + behavior checks.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { compileLiaToTargetFile } from '../src/multi_emit.mjs';
import { compileLiaToJs } from '../src/compiler.mjs';
import { ensureToolchains, hasCmd } from './ensure_toolchains.mjs';

const toolchain = ensureToolchains();
console.error(`[golden_multi_emit] toolchain=${JSON.stringify({ present: toolchain.present, installed: toolchain.installed, failed: toolchain.failed.map((f) => f.tool) })}`);

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(root, 'examples', 'safe-compare.lia');
const outDir = path.join(root, 'examples', '.multi_emit_out');
fs.mkdirSync(outDir, { recursive: true });

const report = [];


function checkPairs(fn) {
  assert.equal(fn('ab', 'ab'), true);
  assert.equal(fn('a', 'b'), false);
  assert.equal(fn('prefix', 'pre'), false);
  assert.equal(fn('', ''), true);
}

// --- TS (prefer-ts default; type-strip + node behavior) ---
{
  const r = compileLiaToTargetFile(src, path.join(outDir, 'safe-compare.ts'), { target: 'ts' });
  let code = r.code
    .replace(/^export /gm, '')
    .replace(/: unknown/g, '')
    .replace(/: boolean/g, '')
    .replace(/: any/g, '')
    .replace(/: Record<string, number>/g, '')
    .replace(/const \$K/g, 'var $K');
  code += '\nmodule.exports = safeCompare;\n';
  const tmp = path.join(outDir, 'safe-compare.ts.cjs');
  fs.writeFileSync(tmp, code, 'utf8');
  const fn = require(tmp);
  checkPairs(fn);
  report.push({ target: 'ts', emit: 'ok', run: 'ok', detail: 'type-strip + node behavior' });
}

// --- JS ---
{
  const lia = fs.readFileSync(src, 'utf8');
  const { js } = compileLiaToJs(lia, { exportMode: 'single' });
  const tmp = path.join(outDir, 'safe-compare.cjs');
  fs.writeFileSync(tmp, js, 'utf8');
  const fn = require(tmp);
  checkPairs(fn);
  report.push({ target: 'js', emit: 'ok', run: 'ok', detail: 'node require behavior' });
}

// --- Python ---
{
  const r = compileLiaToTargetFile(src, path.join(outDir, 'safe_compare.py'), { target: 'py' });
  const pyCheck = `
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sc", r${JSON.stringify(r.outPath)})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.safe_compare("ab","ab") is True
assert m.safe_compare("a","b") is False
assert m.safe_compare("prefix","pre") is False
assert m.safe_compare("","") is True
print("ok py safe-compare")
`;
  const pyFile = path.join(outDir, '_check_py.py');
  fs.writeFileSync(pyFile, pyCheck, 'utf8');
  const pr = spawnSync('python', [pyFile], { encoding: 'utf8' });
  if (pr.status !== 0) {
    report.push({ target: 'py', emit: 'ok', run: 'FAIL', detail: (pr.stderr || pr.stdout || '').slice(0, 400) });
  } else {
    report.push({ target: 'py', emit: 'ok', run: 'ok', detail: (pr.stdout || '').trim() });
  }
}

// --- Go ---
{
  const r = compileLiaToTargetFile(src, path.join(outDir, 'safe_compare.go'), { target: 'go' });
  if (!hasCmd('go')) {
    const f = toolchain.failed.find((x) => x.tool === 'go');
    report.push({
      target: 'go', emit: 'ok', run: 'SKIP',
      detail: f ? `install_failed_after_retry cmd=${f.cmd_for_user}` : 'go absent after ensure',
    });
  } else {
    const gr = spawnSync('go', ['run', r.outPath], { encoding: 'utf8', cwd: outDir });
    if (gr.status !== 0) {
      report.push({ target: 'go', emit: 'ok', run: 'FAIL', detail: (gr.stderr || gr.stdout || '').slice(0, 500) });
    } else {
      report.push({ target: 'go', emit: 'ok', run: 'ok', detail: (gr.stdout || '').trim() });
    }
  }
}

// --- Rust ---
{
  const r = compileLiaToTargetFile(src, path.join(outDir, 'safe_compare.rs'), { target: 'rust' });
  if (!hasCmd('rustc')) {
    const f = toolchain.failed.find((x) => x.tool === 'rustc');
    report.push({
      target: 'rust', emit: 'ok_stub', run: 'SKIP',
      detail: f ? `install_failed_after_retry cmd=${f.cmd_for_user}` : 'rustc absent after ensure; emit kept',
    });
  } else {
    const bin = path.join(outDir, 'safe_compare_rs.exe');
    const rr = spawnSync('rustc', [r.outPath, '-o', bin], { encoding: 'utf8', env: process.env });
    const rustErr = `${rr.stderr || ''}${rr.stdout || ''}`;
    if (rr.status !== 0 && /error(\[|:)/.test(rustErr)) {
      report.push({ target: 'rust', emit: 'ok_stub', run: 'FAIL', detail: rustErr.slice(0, 500) });
    } else {
      const run = spawnSync(bin, [], { encoding: 'utf8' });
      report.push({
        target: 'rust',
        emit: 'ok',
        run: run.status === 0 ? 'ok' : 'FAIL',
        detail: ((run.stdout || '') + (run.stderr || '')).trim().slice(0, 200),
      });
    }
  }
}

console.log(JSON.stringify({ golden: 'safe-compare.lia', report }, null, 2));
const failed = report.filter((x) => x.run === 'FAIL');
if (failed.length) process.exit(1);
console.log('ok golden multi-emit');
