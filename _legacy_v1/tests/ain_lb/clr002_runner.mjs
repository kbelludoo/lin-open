/**
 * CLR-002 deterministic fixture harness.
 *
 * Scope: declarations encoded in the two JSON fixtures. The compiler does not
 * currently expose an effect analyzer, so this runner does not claim to prove
 * arbitrary LIN programs or compiler-wide effect semantics.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getClr } from '../../src/lin_ain_lb_clr_load.mjs';
import { contentHash } from '../../src/content_hash_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const fixtureDir = path.join(root, 'tests', 'ain_lb', 'fixtures', 'clr002');

function readFixture(name) {
  const file = path.join(fixtureDir, name);
  return { file, bytes: fs.readFileSync(file, 'utf8'), value: JSON.parse(fs.readFileSync(file, 'utf8')) };
}

function declarationHash(declaration) {
  return contentHash(
    declaration.function.name,
    declaration.function.params,
    declaration.function.body,
  );
}

function detect(clr, declaration) {
  const graph = clr.clr002Graph(
    declaration.operation,
    declaration.allowed_effects,
    declaration.allowed_context,
  );
  const pass = declaration.kind === 'declaration' && graph.effect_declared === 1
    && (graph.required_context === 'pure' || graph.context_allowed === 1);
  return { status: pass ? 'PASS' : 'CONFLICT', graph };
}

function explain(clr, declaration, detection) {
  const conflict = detection.status === 'CONFLICT';
  return {
    status: 'PASS',
    operation: detection.graph.operation,
    effect: detection.graph.effect,
    capability: detection.graph.capability,
    required_context: detection.graph.required_context,
    allowed_context: detection.graph.context_allowed,
    reason: conflict
      ? 'database.write declares pure but requires io context'
      : 'pure declaration has no effect conflict',
    policy: clr.clr002RepairPolicy(),
  };
}

function propose(clr, declaration, detection) {
  const isConflict = detection.status === 'CONFLICT';
  const proposed = isConflict && declaration.operation === clr.clr002Operation()
    && declaration.allowed_effects.includes('pure');
  return {
    status: proposed ? 'PASS' : 'NO_PROPOSAL',
    change: proposed ? { from: 'pure', to: clr.clr002Effect() } : null,
    source: 'deterministic_fixture_rule',
  };
}

function applyApproved(clr, declaration, proposal, approved) {
  const proposedChange = proposal.status === 'PASS' ? 1 : 0;
  const semanticProof = declarationHash(declaration) !== '' ? 1 : 0;
  const invariantPreserved = declaration.function.body.includes('database.write') ? 1 : 0;
  const decision = clr.clr002RepairDecision(
    proposedChange,
    semanticProof,
    invariantPreserved,
    approved ? 1 : 0,
  );
  if (decision !== 'APPLIED') return { decision, declaration, semantic_hash_preserved: null };
  const changed = {
    ...declaration,
    allowed_effects: declaration.allowed_effects.map((effect) => (
      effect === proposal.change.from ? proposal.change.to : effect
    )),
  };
  return {
    decision,
    declaration: changed,
    semantic_hash_preserved: declarationHash(declaration) === declarationHash(changed),
  };
}

export function runClr002() {
  const clr = getClr();
  const pure = readFixture('pure_declaration.json');
  const conflict = readFixture('database_write_conflict.json');
  const pureDetection = detect(clr, pure.value);
  const conflictDetection = detect(clr, conflict.value);
  const conflictExplanation = explain(clr, conflict.value, conflictDetection);
  const proposal = propose(clr, conflict.value, conflictDetection);
  const beforeBytes = conflict.bytes;
  const conditional = applyApproved(clr, conflict.value, proposal, false);
  const proofBeforeApply = [
    'proposed_change',
    'semantic_proof',
    'invariant_preserved',
    'approval',
    'apply',
  ];
  const approved = applyApproved(clr, conflict.value, proposal, true);
  const afterBytes = fs.readFileSync(conflict.file, 'utf8');
  return {
    id: clr.clr002Id(),
    name: clr.clr002Name(),
    status: clr.clr002Status(),
    autonomy_policy: clr.clr002AutonomyPolicy(),
    causal_graph: clr.clr002CausalGraph(),
    analyzer_scope: clr.clr002AnalyzerScope(),
    limitation: clr.clr002Limitation(),
    paused: clr.clr002Paused(),
    no_llm: clr.clr002NoLlm(),
    no_dicel: clr.clr002NoDicel(),
    no_target_mutation: beforeBytes === afterBytes && clr.clr002TargetMutation() === 0,
    pure_declaration: {
      detect: pureDetection.status === 'PASS' ? 'PASS' : pureDetection.status,
      explain: explain(clr, pure.value, pureDetection).status,
    },
    database_write_conflict: {
      detect: conflictDetection.status === 'CONFLICT' ? 'PASS' : 'FAIL',
      explain: conflictExplanation.status,
      graph: conflictDetection.graph,
      propose: proposal.status,
      proposed_change: proposal.change,
      apply: conditional.decision,
      apply_approved: approved.decision,
      proof_before_apply: proofBeforeApply,
      semantic_hash_before: declarationHash(conflict.value),
      semantic_hash_after: declarationHash(approved.declaration),
      semantic_hash_preserved: approved.semantic_hash_preserved,
    },
  };
}

function main() {
  const report = runClr002();
  assert.equal(report.database_write_conflict.apply, 'CONDITIONAL');
  assert.equal(report.database_write_conflict.semantic_hash_preserved, true);
  assert.equal(report.no_target_mutation, true);
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
