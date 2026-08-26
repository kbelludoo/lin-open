/**
 * Host loader: LIN source is src/lin_type_infer.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_type_infer.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_lin_type_infer_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function inferType(...args) {
  return getMod().inferType(...args);
}

export function inferParamType(...args) {
  return getMod().inferParamType(...args);
}

export function inferReturnType(...args) {
  return getMod().inferReturnType(...args);
}

export function inferFnSignature(...args) {
  return getMod().inferFnSignature(...args);
}

export function isPureBody(...args) {
  return getMod().isPureBody(...args);
}

export function unifyTypes(...args) {
  return getMod().unifyTypes(...args);
}
