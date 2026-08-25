import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getClr, linPath } from '../../src/lin_ain_lb_clr_load.mjs';
import { runClr006 } from './clr006_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const clr = getClr();

assert.equal(linPath(), 'src/lin_ain_lb_clr.lin');
assert.equal(clr.clr006Id(), 'CLR-006');
assert.equal(clr.clr006Name(), 'autonomous_design_choice');
assert.equal(clr.clr006NoScores(), 1);
assert.equal(clr.clr006AgentUnobserved(), 1);
assert.equal(clr.clr006ModelRuns(), 0);
assert.equal(clr.clr006M006Paused(), 1);
assert.match(clr.clr006Nucleus(), /UNTOUCHED/);

const report = runClr006();
assert.equal(report.module_graph_nodes, 6);
assert.deepEqual(report.records.map((record) => record.proposal_id), [
  'baseline', 'cache_memory', 'index_algorithm', 'parallelism', 'persistent_cache',
]);
assert.deepEqual(report.records.map((record) => record.decision), [
  'ACCEPT', 'ACCEPT', 'ACCEPT', 'CONDITIONAL', 'DENIED',
]);
assert.equal(report.records[0].proof_status, 'verified');
assert.equal(report.records[0].constraints_preserved, true);
assert.equal(report.records[3].approval_required, true);
assert.ok(report.records[4].violations.includes('forbidden_effect:io'));
assert.ok(report.records.every((record) => record.tokens_input === '' && record.time_ms === ''));
assert.ok(report.records.every((record) => record.semantic_distance >= 0));

const external = {
  proposal_id: 'external_unproven',
  hypothesis: 'try a new algorithm',
  affected_modules: ['Transfer'],
  inferred_effects: ['pure'],
  required_caps: [],
  architecture_delta: 'none',
  constraints_preserved: true,
  proof_status: 'unproven',
};
const externalReport = runClr006({ proposal: external });
assert.equal(externalReport.records[0].decision, 'CONDITIONAL');
assert.equal(externalReport.records[0].approval_required, true);

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'clr006_runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"agent_unobserved": true/);
assert.match(cli.stdout, /"model_runs": 0/);
console.log('ok ain_lb_clr CLR-006');
