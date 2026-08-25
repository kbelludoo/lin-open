import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getCcr003, linPath } from '../../src/lin_ccr003_horizon_load.mjs';
import { runCcr003 } from './ccr003_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const proto = getCcr003();

assert.equal(linPath(), 'src/lin_ccr003_horizon.lin');
assert.equal(proto.ccr003Id(), 'CCR-003');
assert.equal(proto.ccr003Name(), 'long_horizon_evolution');
assert.equal(proto.generationCount(), 4);
assert.equal(proto.wipeCount(), 3);
assert.equal(proto.agentIds(), 'A|B|C|D');
assert.equal(proto.chatAfterWipe(), 0);
assert.equal(proto.noFakeScores(), 1);
assert.equal(proto.modelUnobserved(), 1);
assert.match(proto.nucleus(), /UNTOUCHED/);
assert.equal(proto.genAt(3), proto.g3());

const report = runCcr003();
assert.equal(report.id, 'CCR-003');
assert.equal(report.generation_count, 4);
assert.equal(report.wipe_count, 3);
assert.equal(report.a4.generations.length, 4);
assert.equal(report.b.generations.length, 4);
assert.equal(report.a4.recovered.length, 3);
assert.equal(report.b.recovered.length, 3);
assert.ok(report.b.recovered.every((w) => w.chat_after_wipe === 0));
assert.equal(report.b.contract_survived, true);
assert.equal(report.b.ignored_semantic_signal, 0);
assert.equal(report.b.unsafe_mutations, 0);
assert.equal(report.b.target_mutated, false);
assert.equal(report.b.generations[3].decision, 'DENIED');
assert.equal(report.a4.contract_survived, false);
assert.equal(report.a4.ignored_semantic_signal, 1);
assert.equal(report.a4.unsafe_mutations, 1);
assert.equal(report.a4.generations[3].understood, true);
assert.equal(report.a4.generations[3].compliance, false);
assert.equal(report.model_unobserved, true);
assert.equal(report.model_runs, 0);
assert.equal(report.no_fake_model_scores, true);
assert.equal(report.real_model_phase.status, 'NOT_RUN');
assert.match(report.differential, /semantic_hash/);

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'ccr003_runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"id": "CCR-003"/);
assert.match(cli.stdout, /"contract_survived": true/);

console.log('ok ain_lb_ccr CCR-003');
