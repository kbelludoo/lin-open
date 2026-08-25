/**
 * Host loader: LIN source is src/lin_ccr002_signal.lin
 * Does not touch verifier / semantic_hash / behavior_eq nucleus.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_ccr002_signal.lin');
let mod = null;

export function getCcr002Signal() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple' });
  const tmp = path.join(os.tmpdir(), `lin_ccr002_signal_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function linPath() {
  return 'src/lin_ccr002_signal.lin';
}
