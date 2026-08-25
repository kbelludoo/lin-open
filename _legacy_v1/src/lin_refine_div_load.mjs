/**
 * Host loader: LIN source is src/lin_refine_div.lin
 * Spec: spec/LIN_M006_PROOF.rulel — INV_REFINEMENT_SOUND before emit.
 * Does not touch verifier / semantic_hash / behavior_eq nucleus.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_refine_div.lin');
let mod = null;

function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_refine_div_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

function constCsv(prog) {
  const c = prog && prog.consts;
  if (!c) return '';
  return Object.entries(c).map(([k, v]) => `${k}=${v}`).join('|');
}

function allFns(prog) {
  const out = [...(prog.fns || [])];
  for (const m of prog.modules || []) {
    for (const fn of (m.program && m.program.fns) || []) out.push(fn);
  }
  return out;
}

export function assertDivProof(liaText, prog) {
  const src = String(liaText || '');
  if (src.indexOf('/') < 0) return;
  if (/\^ops=lin_refine_div\b/.test(src)) return;
  const m = getMod();
  const csv = constCsv(prog);
  for (const fn of allFns(prog)) {
    const err = m.checkFn(fn.name || '', fn.rawParams || fn.params || '', csv, fn.body || '');
    if (err) throw new Error(String(err));
  }
}
