/**
 * Host loader: LIN source is src/lin_ast_data.lin
 * Compiles LIN in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_ast_data.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_lin_ast_data_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function astNode(...args) {
  return getMod().astNode(...args);
}

export function astFn(...args) {
  return getMod().astFn(...args);
}

export function astIf(...args) {
  return getMod().astIf(...args);
}

export function astFor(...args) {
  return getMod().astFor(...args);
}

export function astAssign(...args) {
  return getMod().astAssign(...args);
}

export function astReturn(...args) {
  return getMod().astReturn(...args);
}

export function astCall(...args) {
  return getMod().astCall(...args);
}

export function astLiteral(...args) {
  return getMod().astLiteral(...args);
}

export function astIdent(...args) {
  return getMod().astIdent(...args);
}

export function walkAst(...args) {
  return getMod().walkAst(...args);
}

export function transformAst(...args) {
  return getMod().transformAst(...args);
}

export function astToLin(...args) {
  return getMod().astToLin(...args);
}

export function astBodyToLin(...args) {
  return getMod().astBodyToLin(...args);
}

export function astToJson(...args) {
  return getMod().astToJson(...args);
}

export function astFromJson(...args) {
  return getMod().astFromJson(...args);
}
