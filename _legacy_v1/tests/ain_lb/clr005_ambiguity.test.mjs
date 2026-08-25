import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getClr, linPath } from '../../src/lin_ain_lb_clr_load.mjs';
import { runClr005 } from './clr005_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const clr = getClr();

assert.equal(linPath(), 'src/lin_ain_lb_clr.lin');
assert.equal(clr.clr005Id(), 'CLR-005');
assert.equal(clr.clr005Name(), 'agent_ambiguity_competing_intent');
assert.equal(clr.clr005Status(), 'ACTIVE_DETERMINISTIC_POLICY_METADATA');
assert.match(clr.clr005DecisionPolicy(), /intent.*constraints.*effects.*caps.*architecture/);
assert.match(clr.clr005Limitation(), /not_global_semantic_understanding/);
assert.equal(clr.clr005NoScores(), 1);
assert.equal(clr.clr005NoLlm(), 1);
assert.equal(clr.clr005NoDicel(), 1);
assert.equal(clr.clr005M006Paused(), 1);
assert.match(clr.clr005Nucleus(), /UNTOUCHED/);

const report = runClr005();
assert.equal(report.module_graph_nodes, 6);
assert.deepEqual(report.records.map((record) => record.proposal_id), [
  'local_memory', 'persistent_storage', 'effect_escalation',
  'wrong_module', 'new_module', 'local_memory_unpermitted',
]);
assert.deepEqual(report.records.map((record) => record.decision), [
  'ACCEPT', 'CONDITIONAL', 'DENIED', 'DENIED', 'CONDITIONAL', 'DENIED',
]);
assert.equal(report.records[0].approval_required, false);
assert.ok(report.records[1].missing_constraints.includes('storage_io_permission'));
assert.ok(report.records[2].violations.includes('undeclared_effect_escalation'));
assert.ok(report.records[3].violations.includes('wrong_target_module'));
assert.ok(report.records[4].missing_constraints.includes('architecture_approval'));
assert.ok(report.records[5].violations.includes('missing_constraint:memory_permission'));
assert.deepEqual(report.record_fields, [
  'ambiguity_id', 'proposal_id', 'intent', 'target_module', 'inferred_effects',
  'required_caps', 'architecture_delta', 'decision', 'violations',
  'missing_constraints', 'approval_required', 'proof_status',
  'semantic_hash_before', 'semantic_hash_after',
]);
assert.ok(report.records.every((record) =>
  record.semantic_hash_before === record.semantic_hash_after));

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'clr005_runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"decision": "ACCEPT"/);
assert.match(cli.stdout, /"decision": "CONDITIONAL"/);
assert.match(cli.stdout, /"decision": "DENIED"/);

console.log('ok ain_lb_clr CLR-005');
