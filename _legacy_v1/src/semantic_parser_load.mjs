/**
 * Host loader: LIN source is src/semantic_parser.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'semantic_parser.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_semantic_parser_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function parseSemanticBlock(...args) {
  return getMod().parseSemanticBlock(...args);
}

export function parseSection(...args) {
  return getMod().parseSection(...args);
}

export function parseInputTypes(...args) {
  return getMod().parseInputTypes(...args);
}

export function parseRules(...args) {
  return getMod().parseRules(...args);
}

export function parseConstraints(...args) {
  return getMod().parseConstraints(...args);
}

export function parseEffects(...args) {
  return getMod().parseEffects(...args);
}

export function parseTarget(...args) {
  return getMod().parseTarget(...args);
}
