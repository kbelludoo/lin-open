/**
 * Host: LIN auto-generate from clone INTEL fails.
 * Source of truth: src/lin_auto_generate.lin
 * Never marks stub as PASS. Never mutates nucleus.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../src/compiler.mjs';
import { emitAilFromSource } from '../src/emitter.mjs';

import {
  failClass,
  isStubLin,
  neverPassIfStub,
  gateFrom,
  linHeader,
  safeIdent,
  wrapCandidate,
  proposeCandidate,
  rowSummary,
  summarizeRows
} from '../src/lin_auto_generate_load.mjs';

export {
  failClass,
  isStubLin,
  neverPassIfStub,
  gateFrom,
  linHeader,
  safeIdent,
  wrapCandidate,
  proposeCandidate,
  rowSummary,
  summarizeRows
};

function paramsOf(fail) {
  if (Array.isArray(fail.params)) return fail.params.join(',');
  return String(fail.params || '');
}

function emitRetry(fail) {
  if (!fail || !fail.body) return null;
  const classic = `function ${fail.name}(${paramsOf(fail)}){${fail.body}}`;
  try {
    const lia = emitAilFromSource(classic, { shortenLocals: false });
    if (lia && String(lia).includes(`!${fail.name}(`)) return lia;
  } catch { /* emit gap is a fail, not a fake pass */ }
  return null;
}

function compileOk(text) {
  try {
    compileLiaToJs(text, { exportMode: 'single' });
    return true;
  } catch {
    return false;
  }
}

function writeRulel(linPath, row, slug) {
  const body = [
    '@RULEL:LIN_AUTOGEN:1.0.0',
    '~R{.m=meta .g=gate .f=forbid}',
    `.m{slug=${slug} fn=${row.name} class=${row.class} stub=${row.stub} lin="${path.basename(linPath)}"}`,
    `.g{compile=${row.compileOk} behavior_eq=${row.behaviorEq == null ? 'none' : row.behaviorEq} gate=${row.gate} stub_not_pass=true}`,
    '.f{fake_green stub_as_pass mutate_nucleus}',
    '',
  ].join('\n');
  fs.writeFileSync(linPath.replace(/\.lin$/, '.rulel'), body, 'utf8');
}

/** INTEL fails → candidates/*.lin → compile → honest gate. stubs ≠ PASS. */
export function autoGenerateFromFails(root, candDir, results, slug) {
  const fails = (results || []).filter((r) => r && r.status === 'fail');
  fs.mkdirSync(candDir, { recursive: true });
  const rows = [];
  for (const f of fails) {
    const cls = failClass(f.reason || f.stage);
    let text = null;
    if (f.lia && String(f.lia).includes('!')) text = String(f.lia);
    if (!text) text = emitRetry(f);
    if (!text) text = proposeCandidate({ name: f.name, params: paramsOf(f), lia: null });
    const stub = isStubLin(text) === true;
    const ok = compileOk(text);
    const behaviorEq = typeof f.behavior_eq === 'number' ? f.behavior_eq : null;
    const gate = gateFrom(ok, behaviorEq, stub);
    const safe = `${slug}_${safeIdent(f.name)}`.slice(0, 80);
    const linPath = path.join(candDir, `AUTOGEN_${safe}.lin`);
    fs.writeFileSync(linPath, text, 'utf8');
    const row = rowSummary(f.name, cls, gate, ok, behaviorEq, stub);
    row.path = linPath;
    row.reason = String(f.reason || f.stage || '');
    rows.push(row);
    writeRulel(linPath, row, slug);
  }
  return {
    n: rows.length,
    rows,
    summary: summarizeRows(rows) || 'no_fails',
    root,
  };
}
