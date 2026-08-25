/**
 * Host loader: LIN source is src/lin_mutation_generator.lin
 * Compiles LIN mutation generator in-memory to execute live dogfooded LIN code.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lin_mutation_generator.lin');
let mod = null;

export function getMod() {
  if (mod) return mod;
  const lin = fs.readFileSync(LIN, 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple', lossy: true, skipRefineProof: true });
  const tmp = path.join(os.tmpdir(), `lin_mutation_generator_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return mod;
}

export function mutateFormatting(src) { return getMod().mutateFormatting(src); }
export function mutateComment(src, seed) { return getMod().mutateComment(src, seed); }
export function mutateReorderExports(src) { return getMod().mutateReorderExports(src); }
export function mutateRenameLocal(src) { return getMod().mutateRenameLocal(src); }
export function mutateAlterParameter(src) { return getMod().mutateAlterParameter(src); }
export function mutateAlterType(src) { return getMod().mutateAlterType(src); }
export function mutateAlterEffect(src) { return getMod().mutateAlterEffect(src); }
export function mutateAlterRefinement(src) { return getMod().mutateAlterRefinement(src); }
export function mutateAlterExportedSymbol(src) { return getMod().mutateAlterExportedSymbol(src); }
export function mutateAliasReexport(src) { return getMod().mutateAliasReexport(src); }
export function mutateDependencyEdge(src, seed) { return getMod().mutateDependencyEdge(src, seed); }
export function mutateBodySemantics(src) { return getMod().mutateBodySemantics(src); }

export function getMutatorPool() {
  return [
    { name: 'formatting', isSemanticIntent: false, apply: (s) => mutateFormatting(s) },
    { name: 'comment', isSemanticIntent: false, apply: (s, seed) => mutateComment(s, seed) },
    { name: 'reorder_exports', isSemanticIntent: false, apply: (s) => mutateReorderExports(s) },
    { name: 'rename_local', isSemanticIntent: false, apply: (s) => mutateRenameLocal(s) },
    { name: 'alter_parameter', isSemanticIntent: true, apply: (s) => mutateAlterParameter(s) },
    { name: 'alter_type', isSemanticIntent: true, apply: (s) => mutateAlterType(s) },
    { name: 'alter_effect', isSemanticIntent: true, apply: (s) => mutateAlterEffect(s) },
    { name: 'alter_refinement', isSemanticIntent: true, apply: (s) => mutateAlterRefinement(s) },
    { name: 'alter_exported_symbol', isSemanticIntent: true, apply: (s) => mutateAlterExportedSymbol(s) },
    { name: 'alias_reexport', isSemanticIntent: true, apply: (s) => mutateAliasReexport(s) },
    { name: 'dependency_edge', isSemanticIntent: false, apply: (s, seed) => mutateDependencyEdge(s, seed) },
    { name: 'body_semantics', isSemanticIntent: true, apply: (s) => mutateBodySemantics(s) }
  ];
}
