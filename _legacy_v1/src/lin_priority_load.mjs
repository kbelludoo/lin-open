/**
 * Host loader: LIN source is src/lin_priority.lin
 * Compiles LIN priority table in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_priority.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_priority_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function priCount() { return getMod().priCount(); }
export function priAt(i) { return getMod().priAt(i); }
export function priById(id) { return getMod().priById(id); }
export function priAllLines() { return getMod().priAllLines(); }
export function pipeNow() { return getMod().pipeNow(); }
export function pipeNot() { return getMod().pipeNot(); }
