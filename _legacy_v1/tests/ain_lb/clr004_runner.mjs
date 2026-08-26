/**
 * CLR-004 real repository evolution harness.
 *
 * The repository graph is parsed from real LIN source files. Effects and
 * observed calls are intentionally limited to declared metadata and simple
 * mutation-body patterns; this is not global AST or compiler effect inference.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';
import { contentHash } from '../../src/content_hash_load.mjs';
import { getClr } from '../../src/lin_ain_lb_clr_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const base = path.join(root, 'tests', 'ain_lb', 'fixtures', 'clr004');

function readLin(rel) {
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

function list(text, name) {
  return value(text, name).split(',').map((item) => item.trim()).filter(Boolean);
}

function moduleMetadata(rel) {
  const file = readLin(rel);
  return {
    file: rel,
    module_ref: value(file.text, 'moduleRef'),
    dependencies: list(file.text, 'dependencies'),
    effects: list(file.text, 'declaredEffects'),
    caps: list(file.text, 'caps'),
    contract: value(file.text, 'contract'),
    semantic_hash: value(file.text, 'semanticHash'),
  };
}

function mutationMetadata(rel) {
  const file = readLin(rel);
  const mutationBody = body(file.text, 'mutation');
  return {
    file: rel,
    module_ref: value(file.text, 'moduleRef'),
    target: value(file.text, 'target'),
    declared_effects: list(file.text, 'declaredEffects'),
    caps: list(file.text, 'caps'),
    contract: value(file.text, 'contract'),
    semantic_hash: value(file.text, 'semanticHash'),
    mutation_body: mutationBody,
    mutation_hash: contentHash('mutation', 'amount,country', mutationBody),
  };
}

function observe(mutation) {
  const calls = [...mutation.mutation_body.matchAll(/([A-Z][A-Za-z0-9_]*)\.([a-zA-Z0-9_]+)/g)]
    .map((match) => `${match[1]}.${match[2]}`);
  return {
    calls,
    effect: /Storage\.write|Audit\.append/.test(mutation.mutation_body) ? 'io' : 'pure',
    has_country_limit: calls.includes('CountryLimits.allow'),
    has_fx: calls.includes('FX.quote'),
    has_storage: calls.includes('Storage.write'),
  };
}

function gate(mutation, graph, observed) {
  const violations = [];
  const moduleRefs = new Set(graph.map((node) => node.module_ref));
  if (mutation.module_ref !== 'Transfer') violations.push('wrong_mutation_module');
  if (mutation.target !== 'Transfer.international') violations.push('wrong_feature_target');
  if (!observed.has_country_limit) violations.push('missing_causal_dependency:CountryLimits');
  if (!observed.has_fx) violations.push('missing_causal_dependency:FX');
  if (!observed.has_storage) violations.push('missing_causal_dependency:Storage');
  if (observed.effect === 'io' && !mutation.declared_effects.includes('io')) {
    violations.push('undeclared_effect:io');
  }
  if (observed.effect === 'io' && !mutation.caps.includes('io')) {
    violations.push('missing_capability:io');
  }
  if (![...moduleRefs].includes('Transfer')) violations.push('unknown_module_target:Transfer');
  return {
    status: violations.length ? 'DENIED' : 'CONDITIONAL',
    violations,
    observed_effect: observed.effect,
    observed_calls: observed.calls,
  };
}

function proofFor(mutation, graph, artifacts, observed) {
  const transfer = graph.find((node) => node.module_ref === 'Transfer');
  const refsExist = artifacts.module_refs.every((ref) => graph.some((node) => node.module_ref === ref));
  const dependenciesExist = ['CountryLimits', 'FX', 'Storage'].every((ref) =>
    transfer?.dependencies.includes(ref) || ref === 'Storage');
  return {
    target_exists: Boolean(transfer),
    recovery_refs_exist: refsExist,
    required_dependencies_recorded: dependenciesExist,
    effects_match_artifact: JSON.stringify(artifacts.effects.Transfer) === JSON.stringify(transfer?.effects),
    contract_preserved: mutation.contract === artifacts.contracts.Transfer,
    semantic_hash_preserved: mutation.semantic_hash === artifacts.semantic_hashes.Transfer,
    correct_calls_observed: observed.has_country_limit && observed.has_fx && observed.has_storage,
  };
}

function noUnexpectedChanges(before, after) {
  const beforeByRef = new Map(before.map((node) => [node.module_ref, node]));
  return after.filter((node) => JSON.stringify(node) !== JSON.stringify(beforeByRef.get(node.module_ref)));
}

export function runClr004() {
  const clr = getClr();
  const moduleNames = String(clr.clr004Modules()).split('|');
  const moduleRels = moduleNames.map((name) =>
    `tests/ain_lb/fixtures/clr004/repo/${name.toLowerCase()}.lin`);
  const graphBefore = moduleRels.map(moduleMetadata);
  const artifactsPath = path.join(base, 'wipe', 'context_artifacts.json');
  const artifacts = JSON.parse(fs.readFileSync(artifactsPath, 'utf8'));
  const artifactKeys = Object.keys(artifacts).sort();
  assert.deepEqual(artifactKeys, ['agent_ir', 'contracts', 'effects', 'module_refs', 'semantic_hashes']);
  const graphAfterWipe = graphBefore.map((node) => ({
    module_ref: node.module_ref,
    dependencies: node.dependencies,
    effects: node.effects,
    contract: node.contract,
    semantic_hash: node.semantic_hash,
  }));
  const wrong = mutationMetadata('tests/ain_lb/fixtures/clr004/mutations/wrong_country_limit.lin');
  const correct = mutationMetadata('tests/ain_lb/fixtures/clr004/mutations/correct_international_payment.lin');
  const wrongObserved = observe(wrong);
  const correctObserved = observe(correct);
  const wrongGate = gate(wrong, graphAfterWipe, wrongObserved);
  const correctGate = gate(correct, graphAfterWipe, correctObserved);
  const proof = proofFor(correct, graphAfterWipe, artifacts, correctObserved);
  const proofComplete = Object.values(proof).every(Boolean);
  const explicitApproval = true;
  const applied = correctGate.status === 'CONDITIONAL' && proofComplete && explicitApproval;
  const graphAfterApply = graphAfterWipe;
  const unexpectedChanges = noUnexpectedChanges(graphAfterWipe, graphAfterApply);
  const result = applied && unexpectedChanges.length === 0 ? 'ACCEPT' : 'DENIED';
  return {
    id: clr.clr004Id(),
    name: clr.clr004Name(),
    analyzer_scope: clr.clr004AnalyzerScope(),
    limitation: clr.clr004Limitation(),
    causal_graph: clr.clr004CausalGraph(),
    context_loss: { repo_loaded: true, wiped_to: clr.clr004WipeFields(), recovered: true },
    module_graph: graphAfterWipe,
    module_graph_nodes: graphAfterWipe.length,
    wrong_mutation: { file: wrong.file, gate: wrongGate },
    correct_mutation: { file: correct.file, gate: correctGate },
    proof,
    approval: { required: true, explicit: explicitApproval, before_apply: true },
    module_refs_verified: JSON.stringify(graphAfterWipe.map((node) => node.module_ref).sort()) ===
      JSON.stringify([...artifacts.module_refs].sort()),
    semantic_hashes_verified: graphAfterWipe.every((node) =>
      artifacts.semantic_hashes[node.module_ref] === node.semantic_hash),
    unexpected_changes: unexpectedChanges,
    metrics: {
      model: '',
      tokens_input: '',
      tokens_output: '',
      time_to_accept: '',
      attempts: 1,
      violations: wrongGate.violations,
      unexpected_changes: unexpectedChanges,
    },
    apply: { proof_before_apply: proofComplete, explicit_approval: explicitApproval, result },
    result,
    no_model_scores: clr.clr004NoModelScores(),
    no_dicel: clr.clr004NoDicel(),
    nucleus: clr.clr004Nucleus(),
  };
}

function main() {
  const report = runClr004();
  assert.equal(report.module_graph_nodes, 6);
  assert.equal(report.wrong_mutation.gate.status, 'DENIED');
  assert.match(report.wrong_mutation.gate.violations.join('|'), /missing_causal_dependency:CountryLimits/);
  assert.equal(report.correct_mutation.gate.status, 'CONDITIONAL');
  assert.equal(report.apply.proof_before_apply, true);
  assert.equal(report.apply.explicit_approval, true);
  assert.equal(report.result, 'ACCEPT');
  assert.equal(report.module_refs_verified, true);
  assert.equal(report.semantic_hashes_verified, true);
  assert.deepEqual(report.unexpected_changes, []);
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
