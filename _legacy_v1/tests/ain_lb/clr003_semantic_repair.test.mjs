import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getClr, linPath } from '../../src/lin_ain_lb_clr_load.mjs';
import { runClr003 } from './clr003_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const clr = getClr();

assert.equal(linPath(), 'src/lin_ain_lb_clr.lin');
assert.equal(clr.clr003Id(), 'CLR-003');
assert.equal(clr.clr003Name(), 'semantic_repair_real_module_graph');
assert.equal(clr.clr003Status(), 'ACTIVE_DETERMINISTIC_FIXTURE_GRAPH');
assert.equal(clr.clr003GraphSource(), 'real_lin_files_module_metadata_and_source_body');
assert.match(clr.clr003AnalyzerScope(), /not_global_compiler_effect_inference/);
assert.match(clr.clr003Limitation(), /fixture_metadata_and_body_patterns/);
assert.match(clr.clr003CausalGraph(), /proof->approval->ACCEPT/);
assert.equal(clr.clr003NoLlm(), 1);
assert.equal(clr.clr003NoDicel(), 1);
assert.equal(clr.clr003Nucleus(), 'UNTOUCHED_existing_semantic_hash');

const report = runClr003();
assert.equal(report.module_graph_nodes, 3);
assert.equal(report.module_graph.map((node) => node.module_ref).join('|'), 'Auth|Storage|Transfer');
assert.equal(report.wrong_mutation.gate.status, 'DENIED');
assert.equal(report.wrong_mutation.gate.observed_target, 'Storage.write');
assert.deepEqual(report.violations, [
  'target_mismatch', 'undeclared_effect:io', 'missing_capability:io',
]);
assert.equal(report.repair_loop_length, 1);
assert.deepEqual(report.proof_before_apply, [
  'target_exists', 'effect_declared_by_target', 'contract_preserved', 'semantic_hash_before/after',
]);
assert.equal(report.approval_required, 1);
assert.equal(report.approval.explicit, true);
assert.equal(report.apply.decision_before_approval, 'CONDITIONAL');
assert.equal(report.apply.result, 'ACCEPT');
assert.equal(report.result, 'ACCEPT');
assert.equal(report.original_target_not_mutated, true);
assert.ok(report.semantic_hash_before);
assert.equal(report.semantic_hash_before, report.semantic_hash_after);
assert.equal(report.identity_recorded.original_module_ref, 'Transfer');
assert.equal(report.identity_recorded.repaired_module_ref, 'Transfer');

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'clr003_runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"result": "ACCEPT"/);
assert.match(cli.stdout, /"original_target_not_mutated": true/);

console.log('ok ain_lb_clr CLR-003');
