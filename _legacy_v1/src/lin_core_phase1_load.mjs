/**
 * Host loader: LIN source is src/lin_core_phase1.lin
 * Compiles LIN core phase1 definition in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_core_phase1.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_core_phase1_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function coreBanner() { return getMod().coreBanner(); }
export function coreHostLang() { return getMod().coreHostLang(); }
export function cliDefaultLang() { return getMod().cliDefaultLang(); }
