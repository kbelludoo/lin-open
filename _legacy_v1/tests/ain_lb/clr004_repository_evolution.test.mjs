import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getClr, linPath } from '../../src/lin_ain_lb_clr_load.mjs';
import { runClr004 } from './clr004_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const clr = getClr();

assert.equal(linPath(), 'src/lin_ain_lb_clr.lin');
assert.equal(clr.clr004Id(), 'CLR-004');
assert.equal(clr.clr004Name(), 'real_repository_evolution');
assert.equal(clr.clr004Status(), 'ACTIVE_DETERMINISTIC_CONTEXT_LOSS_PROTOCOL');
assert.match(clr.clr004GraphSource(), /real_lin_files/);
assert.match(clr.clr004AnalyzerScope(), /not_global_ast_or_compiler_effect_inference/);
assert.match(clr.clr004Limitation(), /metadata_and_body_patterns/);
assert.equal(clr.clr004NoModelScores(), 1);
assert.equal(clr.clr004NoDicel(), 1);
assert.match(clr.clr004Nucleus(), /UNTOUCHED/);

const report = runClr004();
assert.equal(report.module_graph_nodes, 6);
assert.deepEqual(report.module_graph.map((node) => node.module_ref).sort(), [
  'Audit', 'Auth', 'CountryLimits', 'FX', 'Storage', 'Transfer',
]);
assert.equal(report.context_loss.recovered, true);
assert.equal(report.wrong_mutation.gate.status, 'DENIED');
assert.ok(report.wrong_mutation.gate.violations.includes('missing_causal_dependency:CountryLimits'));
assert.equal(report.correct_mutation.gate.status, 'CONDITIONAL');
assert.equal(report.approval.before_apply, true);
assert.equal(report.result, 'ACCEPT');
assert.equal(report.module_refs_verified, true);
assert.equal(report.semantic_hashes_verified, true);
assert.deepEqual(report.unexpected_changes, []);
assert.equal(report.metrics.model, '');
assert.equal(report.metrics.tokens_input, '');
assert.equal(report.metrics.tokens_output, '');
assert.equal(report.metrics.time_to_accept, '');
assert.equal(report.metrics.attempts, 1);
assert.ok(Array.isArray(report.metrics.violations));

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'clr004_runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"result": "ACCEPT"/);
assert.match(cli.stdout, /"module_refs_verified": true/);

console.log('ok ain_lb_clr CLR-004');
