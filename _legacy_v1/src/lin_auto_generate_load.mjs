/**
 * Host loader: LIN source is src/lin_auto_generate.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_auto_generate.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_lin_auto_generate_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function failClass(...args) {
  return getMod().failClass(...args);
}

export function isStubLin(...args) {
  return getMod().isStubLin(...args);
}

export function neverPassIfStub(...args) {
  return getMod().neverPassIfStub(...args);
}

export function gateFrom(...args) {
  return getMod().gateFrom(...args);
}

export function linHeader(...args) {
  return getMod().linHeader(...args);
}

export function safeIdent(...args) {
  return getMod().safeIdent(...args);
}

export function wrapCandidate(...args) {
  return getMod().wrapCandidate(...args);
}

export function proposeCandidate(...args) {
  return getMod().proposeCandidate(...args);
}

export function rowSummary(...args) {
  return getMod().rowSummary(...args);
}

export function summarizeRows(...args) {
  return getMod().summarizeRows(...args);
}
