/**
 * CLR-006 autonomous design-choice protocol.
 *
 * The runner is a deterministic judge for an external proposal. It does not
 * generate hypotheses, rank designs, or claim that an agent found the best
 * solution. All repository facts come from LIN artifacts after a simulated
 * context wipe.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';
import { getClr } from '../../src/lin_ain_lb_clr_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const base = path.join(root, 'tests', 'ain_lb', 'fixtures', 'clr006');

function value(text, name) {
  const match = text.match(new RegExp(`!${name}\\(\\)\\{\\^'([^']*)'\\}`));
  return match ? match[1] : '';
}

function list(text, name) {
  return value(text, name).split(',').map((item) => item.trim()).filter(Boolean);
}

function moduleMetadata(rel) {
  const file = path.join(root, rel);
  const text = fs.readFileSync(file, 'utf8');
  compileLiaToJs(text, { exportMode: 'multiple' });
  return {
    file: rel,
    module_ref: value(text, 'moduleRef'),
    dependencies: list(text, 'dependencies'),
    effects: list(text, 'declaredEffects'),
    caps: list(text, 'caps'),
    contract: value(text, 'contract'),
    semantic_hash: value(text, 'semanticHash'),
  };
}

function loadContext() {
  const contract = JSON.parse(fs.readFileSync(path.join(base, 'performance_contract.json'), 'utf8'));
  const artifacts = JSON.parse(fs.readFileSync(
    path.join(root, 'tests', 'ain_lb', 'fixtures', 'clr004', 'wipe', 'context_artifacts.json'),
    'utf8',
  ));
  const names = ['auth', 'storage', 'transfer', 'audit', 'fx', 'country_limits'];
  const graph = names.map((name) => moduleMetadata(`tests/ain_lb/fixtures/clr004/repo/${name}.lin`));
  const refsVerified = artifacts.module_refs.every((ref) =>
    graph.some((node) => node.module_ref === ref));
  const hashesVerified = graph.every((node) => artifacts.semantic_hashes[node.module_ref] === node.semantic_hash);
  return { contract, artifacts, graph, refsVerified, hashesVerified };
}

function semanticDistance(proposal, graph) {
  const known = new Set(graph.map((node) => node.module_ref));
  return [
    proposal.affected_modules?.some((moduleRef) => !known.has(moduleRef)) ?? true,
    proposal.architecture_delta !== 'none',
    (proposal.inferred_effects ?? []).includes('io'),
    (proposal.required_caps ?? []).includes('io'),
  ].filter(Boolean).length;
}

function evaluate(proposal, context) {
  const { contract, artifacts, graph, refsVerified, hashesVerified } = context;
  const affectedModules = [...new Set(proposal.affected_modules ?? [])];
  const violations = [];
  const repairs = [];
  const missingApprovals = [];
  const known = new Set(graph.map((node) => node.module_ref));

  if (affectedModules.length === 0 || affectedModules.some((ref) => !known.has(ref))) {
    violations.push('unknown_affected_module');
  }
  if (proposal.constraints_preserved !== true) violations.push('performance_contract_not_preserved');
  if ((proposal.inferred_effects ?? []).some((effect) =>
    contract.constraints.forbidden_effects.includes(effect))) {
    violations.push('forbidden_effect:io');
    repairs.push('remove_io_effect_or_request_a_new_contract');
  }
  if ((proposal.required_caps ?? []).some((cap) =>
    contract.constraints.forbidden_caps.includes(cap))) {
    violations.push('forbidden_capability');
    repairs.push('remove_storage_capability');
  }
  if ((proposal.architecture_delta ?? 'none') !== 'none') {
    missingApprovals.push('architecture_approval');
  }
  if ((proposal.required_caps ?? []).includes('concurrency') &&
      !contract.constraints.concurrency_approval) {
    missingApprovals.push('concurrency_approval');
  }
  if (!refsVerified || !hashesVerified) violations.push('artifact_integrity_failure');
  const proof = proposal.proof_status === 'metadata_verified' && refsVerified && hashesVerified;
  if (!proof) repairs.push('provide_metadata_and_contract_proof');
  const approvalRequired = missingApprovals.length > 0 || !proof;
  const hardViolation = violations.length > 0;
  const decision = hardViolation ? 'DENIED' : approvalRequired ? 'CONDITIONAL' : 'ACCEPT';
  const causalResult = hardViolation
    ? `DENIED because ${violations.join(', ')}`
    : approvalRequired
      ? `CONDITIONAL pending ${missingApprovals.concat(proof ? [] : ['proof']).join(', ')}`
      : 'ACCEPT because artifacts, proof, effects, caps, and contract passed';

  return {
    proposal_id: String(proposal.proposal_id ?? ''),
    hypothesis: String(proposal.hypothesis ?? ''),
    semantic_distance: semanticDistance(proposal, graph),
    affected_modules: affectedModules,
    constraints_preserved: proposal.constraints_preserved === true,
    violations,
    repairs,
    proof_status: proof ? 'verified' : 'unproven',
    approval_required: approvalRequired,
    attempts: 1,
    tokens_input: '',
    tokens_output: '',
    time_ms: '',
    agent_unobserved: true,
    model_runs: 0,
    decision,
    causal_result: causalResult,
    missing_approvals: missingApprovals,
    semantic_hashes: artifacts.semantic_hashes,
  };
}

export function runClr006({ proposal, proposals } = {}) {
  const clr = getClr();
  const context = loadContext();
  const input = proposals ?? (proposal ? [proposal] : JSON.parse(
    fs.readFileSync(path.join(base, 'proposals.json'), 'utf8'),
  ).proposals);
  const records = input.map((item) => evaluate(item, context));
  return {
    id: clr.clr006Id(),
    name: clr.clr006Name(),
    task: clr.clr006Task(),
    policy: clr.clr006Policy(),
    causal_graph: clr.clr006CausalGraph(),
    context_loss: { repo_loaded: true, artifacts_loaded: true, agent_unobserved: true },
    module_graph: context.graph,
    module_graph_nodes: context.graph.length,
    performance_contract: context.contract,
    records,
    record_fields: String(clr.clr006RecordFields()).split('|'),
    no_scores: clr.clr006NoScores(),
    no_llm: clr.clr006NoLlm(),
    agent_unobserved: clr.clr006AgentUnobserved(),
    model_runs: clr.clr006ModelRuns(),
    m006_paused: clr.clr006M006Paused(),
    limitation: 'Deterministic policy proves judge/protocol behavior only; it cannot establish best-design discovery.',
    nucleus: clr.clr006Nucleus(),
  };
}

function main() {
  const proposalFlag = process.argv.indexOf('--proposal');
  const proposal = proposalFlag >= 0
    ? JSON.parse(fs.readFileSync(path.resolve(process.argv[proposalFlag + 1]), 'utf8'))
    : undefined;
  const report = runClr006({ proposal });
  assert.equal(report.module_graph_nodes, 6);
  assert.ok(report.records.every((record) => record.agent_unobserved && record.model_runs === 0));
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
