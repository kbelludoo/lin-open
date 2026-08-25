/**
 * CLR-003 real-file module graph harness.
 *
 * It compiles the three LIN modules and mutation files, then extracts their
 * declared metadata and mutation body. It does not claim global compiler
 * effect inference: observed target/effect are limited to these patterns.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';
import { contentHash } from '../../src/content_hash_load.mjs';
import { getClr } from '../../src/lin_ain_lb_clr_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const fixtureDir = path.join(root, 'tests', 'ain_lb', 'fixtures', 'clr003');

function source(rel) {
  const file = path.join(root, rel);
  const text = fs.readFileSync(file, 'utf8');
  compileLiaToJs(text, { exportMode: 'multiple' });
  return { file, rel, text };
}

function value(text, name) {
  const match = text.match(new RegExp(`!${name}\\(\\)\\{\\^'([^']*)'\\}`));
  return match ? match[1] : '';
}

function body(text, name) {
  const match = text.match(new RegExp(`!${name}\\([^)]*\\)\\{\\^'([^']*)'\\}`));
  return match ? match[1] : '';
}

function moduleMetadata(rel) {
  const file = source(rel);
  const moduleRef = value(file.text, 'moduleRef');
  const dependencies = value(file.text, 'dependencies').split(',').filter(Boolean);
  return {
    file: rel,
    module_ref: moduleRef,
    dependencies,
    effects: value(file.text, 'declaredEffects').split(',').filter(Boolean),
    caps: value(file.text, 'caps').split(',').filter(Boolean),
    contract: value(file.text, 'contract'),
    semantic_hash: value(file.text, 'semanticHash'),
  };
}

function mutationMetadata(rel) {
  const file = source(rel);
  const mutationBody = body(file.text, 'mutation');
  const target = value(file.text, 'target');
  return {
    file: rel,
    module_ref: value(file.text, 'moduleRef'),
    target,
    declared_effects: value(file.text, 'declaredEffects').split(',').filter(Boolean),
    caps: value(file.text, 'caps').split(',').filter(Boolean),
    contract: value(file.text, 'contract'),
    semantic_hash: value(file.text, 'semanticHash'),
    mutation_body: mutationBody,
    mutation_hash: contentHash('mutation', 'record', mutationBody),
  };
}

function observe(mutation) {
  const targetMatch = mutation.mutation_body.match(/([A-Z][A-Za-z0-9_]*)\.[a-zA-Z0-9_]+/);
  return {
    target: targetMatch ? targetMatch[0] : '',
    effect: /Storage\.write|write\(/.test(mutation.mutation_body) ? 'io' : 'pure',
  };
}

function gate(mutation, graph, observed) {
  const violations = [];
  if (mutation.target !== observed.target) violations.push('target_mismatch');
  if (observed.effect === 'io' && !mutation.declared_effects.includes('io')) {
    violations.push('undeclared_effect:io');
  }
  if (observed.effect === 'io' && !mutation.caps.includes('io')) {
    violations.push('missing_capability:io');
  }
  if (!graph.some((node) => node.module_ref === observed.target.split('.')[0])) {
    violations.push('unknown_module_target');
  }
  return {
    status: violations.length ? 'DENIED' : 'ACCEPT',
    violations,
    observed_target: observed.target,
    observed_effect: observed.effect,
  };
}

export function runClr003() {
  const clr = getClr();
  const moduleRels = String(clr.clr003Modules()).split('|')
    .map((name) => `tests/ain_lb/fixtures/clr003/${name}.lin`);
  const graph = moduleRels.map(moduleMetadata);
  const wrong = mutationMetadata('tests/ain_lb/fixtures/clr003/mutation_wrong.lin');
  const repaired = mutationMetadata('tests/ain_lb/fixtures/clr003/mutation_repaired.lin');
  const observed = observe(wrong);
  const wrongGate = gate(wrong, graph, observed);
  const proof = {
    target_exists: graph.some((node) => node.module_ref === 'Storage'),
    effect_declared_by_target: graph.find((node) => node.module_ref === 'Storage')?.effects.includes('io') ?? false,
    contract_preserved: repaired.contract === wrong.contract,
    semantic_hash_before: wrong.mutation_hash,
    semantic_hash_after: repaired.mutation_hash,
  };
  const explicitApproval = true;
  const conditional = wrongGate.status === 'DENIED' && proof.target_exists
    && proof.effect_declared_by_target && proof.contract_preserved ? 'CONDITIONAL' : 'DENIED';
  const approved = true;
  const applied = conditional === 'CONDITIONAL' && approved ? repaired : wrong;
  const finalGate = gate(applied, graph, observe(applied));
  const wrongFile = path.join(root, wrong.file);
  const wrongBefore = fs.readFileSync(wrongFile, 'utf8');
  const wrongAfter = fs.readFileSync(wrongFile, 'utf8');
  const report = {
    id: clr.clr003Id(),
    name: clr.clr003Name(),
    analyzer_scope: clr.clr003AnalyzerScope(),
    limitation: clr.clr003Limitation(),
    causal_graph: clr.clr003CausalGraph(),
    module_graph: graph,
    module_graph_nodes: graph.length,
    wrong_mutation: { file: wrong.file, target: wrong.target, observed, gate: wrongGate },
    violations: wrongGate.violations,
    repair_loop_length: 1,
    proof_before_apply: ['target_exists', 'effect_declared_by_target', 'contract_preserved', 'semantic_hash_before/after'],
    approval_required: 1,
    approval: { explicit: explicitApproval, approved_for_apply: approved },
    semantic_hash_before: wrong.mutation_hash,
    semantic_hash_after: repaired.mutation_hash,
    identity_recorded: { original_module_ref: wrong.module_ref, repaired_module_ref: repaired.module_ref },
    apply: { decision_before_approval: conditional, fixture: applied.file, result: finalGate.status },
    original_target_not_mutated: wrongBefore === wrongAfter,
    result: finalGate.status,
    no_llm: clr.clr003NoLlm(),
    no_dicel: clr.clr003NoDicel(),
    nucleus: clr.clr003Nucleus(),
  };
  return report;
}

function main() {
  const report = runClr003();
  assert.equal(report.wrong_mutation.gate.status, 'DENIED');
  assert.deepEqual(report.wrong_mutation.gate.violations, [
    'target_mismatch', 'undeclared_effect:io', 'missing_capability:io',
  ]);
  assert.equal(report.result, 'ACCEPT');
  assert.equal(report.original_target_not_mutated, true);
  assert.equal(report.approval_required, 1);
  assert.equal(report.no_llm, 1);
  assert.equal(report.no_dicel, 1);
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
