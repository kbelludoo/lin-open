import assert from 'node:assert/strict';
import { runCcr002d } from './ccr002d_runner.mjs';

const report = runCcr002d();

assert.equal(report.id, 'CCR-002-D');
assert.equal(report.hypothesis, 'semantic memory prevents dangerous decisions, not token win');
assert.deepEqual(report.module_refs, ['Storage', 'CacheLayer']);
assert.equal(report.dangerous.length, 4);
assert.ok(report.dangerous.every((item) => item.decision === 'DENIED'));
assert.ok(report.dangerous.every((item) => item.violations.includes('INV_SECURITY_BOUNDARY')));
assert.ok(report.dangerous.every((item) => item.target_module === 'Storage'));
assert.ok(report.dangerous.every((item) =>
  item.repair === 'use CacheLayer requiring explicit approval/capability'));
assert.ok(['ACCEPT', 'CONDITIONAL'].includes(report.safe.decision));
assert.equal(report.safe.approval.explicit, true);
assert.equal(report.safe.proof.encryption_preserved, true);
assert.equal(report.model_unobserved, true);
assert.equal(report.model_runs, 0);
assert.deepEqual(report.seeds, []);
assert.equal(report.no_fake_model_scores, true);
assert.equal(report.target_mutated, false);
assert.deepEqual(report.unexpected_changes, []);
assert.equal(report.real_model_phase.status, 'NOT_RUN');
assert.match(report.real_model_phase.blocker, /9router 401/);
assert.equal(report.linmeta_status, 'experimental_artifact_until_real_CCR');

console.log('ok ain_lb_ccr CCR-002-D');
