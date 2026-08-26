/**
 * Host loader: LIN source is src/extract_native.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'extract_native.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_extract_native_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function extractNativeFns(...args) {
  return getMod().extractNativeFns(...args);
}

export function extractPy(...args) {
  return getMod().extractPy(...args);
}

export function extractGo(...args) {
  return getMod().extractGo(...args);
}

export function extractC(...args) {
  return getMod().extractC(...args);
}

export function extractRs(...args) {
  return getMod().extractRs(...args);
}

export function extractJava(...args) {
  return getMod().extractJava(...args);
}
