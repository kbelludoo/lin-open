import assert from 'node:assert/strict';
import { runMutationCampaignV3 } from '../scripts/bench_linobj_mutation_v3_oracle.mjs';

console.log('=== Running Mutation Campaign V3 with Independent V8 Runtime Oracle ===\n');

const res = await runMutationCampaignV3(200);

assert.equal(res.FN, 0, 'Zero Under-invalidation required (FN must be strictly 0)');
assert.equal(res.underInvalidationRate, 0.0, 'Under-invalidation rate against independent oracle must be 0.00%');
assert.equal(res.recall, 1.0, 'Soundness / Recall against independent oracle must be 100.00%');
assert.equal(res.TP, res.totalSemantic, 'All ground-truth semantic mutations must be correctly rebuilt');

console.log('\n============================================================');
console.log('Mutation Campaign V3 (Independent Oracle) PASSED (100% Soundness).');
console.log('============================================================\n');
