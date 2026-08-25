/**
 * Host loader: LIN source is src/clone_lin_full_repo_gate.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'clone_lin_full_repo_gate.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_clone_lin_full_repo_gate_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function cloneLinFullRepoGate(...args) {
  return getMod().cloneLinFullRepoGate(...args);
}
