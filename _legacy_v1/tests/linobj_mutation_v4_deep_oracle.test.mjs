import assert from 'node:assert/strict';
import { runMutationCampaignV4 } from '../scripts/bench_linobj_mutation_v4_deep_oracle.mjs';

console.log('=== Running Mutation Campaign V4 with Deep Adversarial Oracle ===\n');

const res = await runMutationCampaignV4(200);

assert.equal(res.FN, 0, 'Zero Under-invalidation required (FN must be strictly 0)');
assert.equal(res.underInvalidationRate, 0.0, 'Under-invalidation rate against deep adversarial oracle must be 0.00%');
assert.equal(res.recall, 1.0, 'Soundness / Recall against deep adversarial oracle must be 100.00%');
assert.equal(res.TP, res.totalSemantic, 'All ground-truth semantic mutations must be correctly rebuilt');

console.log('\n============================================================');
console.log('Mutation Campaign V4 (Deep Adversarial Oracle) PASSED (100% Soundness).');
console.log('============================================================\n');
