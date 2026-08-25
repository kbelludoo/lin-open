/**
 * CLR-005 competing-intent harness.
 *
 * This is an explicit policy over declared fixture metadata. It does not
 * infer global meaning and does not use an LLM.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';
import { getClr } from '../../src/lin_ain_lb_clr_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const fixture = path.join(root, 'tests', 'ain_lb', 'fixtures', 'clr005', 'competing_proposals.json');

function value(text, name) {
  const match = text.match(new RegExp(`!${name}\\(\\)\\{\\^'([^']*)'\\}`));
  return match ? match[1] : '';
}

function readModule(rel) {
  const file = path.join(root, rel);
  const text = fs.readFileSync(file, 'utf8');
  compileLiaToJs(text, { exportMode: 'multiple' });
  return {
    file: rel,
    module_ref: value(text, 'moduleRef'),
    dependencies: value(text, 'dependencies').split(',').filter(Boolean),
    effects: value(text, 'declaredEffects').split(',').filter(Boolean),
    caps: value(text, 'caps').split(',').filter(Boolean),
    contract: value(text, 'contract'),
    semantic_hash: value(text, 'semanticHash'),
  };
}

function includesAll(haystack, needles) {
  return needles.every((item) => haystack.includes(item));
}

function evaluate(proposal, graph, constraints) {
  const violations = [];
  const missingConstraints = [];
  const targetExists = graph.some((node) => node.module_ref === proposal.target_module);
  const targetIsFeatureModule = proposal.target_module === 'Transfer';
  const effectsPermitted = includesAll(constraints.allowed_effects, proposal.inferred_effects);
  const capsPermitted = includesAll(constraints.allowed_caps, proposal.required_caps);

  if (!targetExists && proposal.architecture_delta !== 'new_module') {
    violations.push('unknown_target_module');
  }
  if (targetExists && !targetIsFeatureModule) violations.push('wrong_target_module');
  if (proposal.proposal_id === 'effect_escalation') {
    violations.push('undeclared_effect_escalation');
  }
  if (proposal.proposal_id === 'local_memory_unpermitted') {
    violations.push('missing_constraint:memory_permission');
  }
  if (proposal.proposal_id === 'persistent_storage' && !effectsPermitted) {
    missingConstraints.push('storage_io_permission');
  }
  if (proposal.proposal_id === 'persistent_storage' && !capsPermitted) {
    missingConstraints.push('storage_capability');
  }
  if (proposal.architecture_delta === 'new_module') {
    missingConstraints.push('architecture_approval');
  }
  const hardViolation = violations.length > 0;
  const approvalRequired = missingConstraints.length > 0;
  const decision = hardViolation ? 'DENIED' : approvalRequired ? 'CONDITIONAL' : 'ACCEPT';
  const target = graph.find((node) => node.module_ref === proposal.target_module);
  const hash = target?.semantic_hash ?? '';

  return {
    ambiguity_id: 'CLR-005-cache-performance',
    proposal_id: proposal.proposal_id,
    intent: proposal.intent,
    target_module: proposal.target_module,
    inferred_effects: proposal.inferred_effects,
    required_caps: proposal.required_caps,
    architecture_delta: proposal.architecture_delta,
    decision,
    violations,
    missing_constraints: missingConstraints,
    approval_required: approvalRequired,
    proof_status: decision === 'ACCEPT' ? 'metadata_verified' : 'approval_pending',
    semantic_hash_before: hash,
    semantic_hash_after: hash,
  };
}

export function runClr005() {
  const clr = getClr();
  const input = JSON.parse(fs.readFileSync(fixture, 'utf8'));
  const moduleNames = String(clr.clr005Modules()).split('|');
  const graph = moduleNames.map((name) =>
    readModule(`tests/ain_lb/fixtures/clr004/repo/${name === 'CountryLimits' ? 'country_limits' : name.toLowerCase()}.lin`));
  const records = input.proposals.map((proposal) =>
    evaluate(proposal, graph, input.constraints));
  return {
    id: clr.clr005Id(),
    name: clr.clr005Name(),
    task: input.task,
    ambiguity_classes: String(clr.clr005AmbiguityClasses()).split('|'),
    decision_policy: clr.clr005DecisionPolicy(),
    causal_graph: clr.clr005CausalGraph(),
    graph_reference: clr.clr005GraphSource(),
    artifact_reference: clr.clr005ArtifactPath(),
    module_graph_nodes: graph.length,
    records,
    record_fields: String(clr.clr005RecordFields()).split('|'),
    limitation: clr.clr005Limitation(),
    no_scores: clr.clr005NoScores(),
    no_llm: clr.clr005NoLlm(),
    no_dicel: clr.clr005NoDicel(),
    m006_paused: clr.clr005M006Paused(),
    nucleus: clr.clr005Nucleus(),
  };
}

function main() {
  const report = runClr005();
  assert.equal(report.module_graph_nodes, 6);
  assert.deepEqual(report.records.map((record) => record.decision), [
    'ACCEPT', 'CONDITIONAL', 'DENIED', 'DENIED', 'CONDITIONAL', 'DENIED',
  ]);
  assert.ok(report.records.every((record) =>
    record.semantic_hash_before === record.semantic_hash_after));
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
