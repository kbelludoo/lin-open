/**
 * Host loader: LIN source is src/lin_rules_engine.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_rules_engine.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_lin_rules_engine_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function createKnowledgeBase(...args) {
  return getMod().createKnowledgeBase(...args);
}

export function assertFact(...args) {
  return getMod().assertFact(...args);
}

export function assertRule(...args) {
  return getMod().assertRule(...args);
}

export function queryFact(...args) {
  return getMod().queryFact(...args);
}

export function applyRules(...args) {
  return getMod().applyRules(...args);
}

export function inferRequirements(...args) {
  return getMod().inferRequirements(...args);
}

export function checkConstraints(...args) {
  return getMod().checkConstraints(...args);
}

export function kbToLin(...args) {
  return getMod().kbToLin(...args);
}
