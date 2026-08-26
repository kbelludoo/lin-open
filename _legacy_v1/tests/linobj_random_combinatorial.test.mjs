import assert from 'node:assert/strict';
import { runRandomCombinatorialCampaign } from '../scripts/bench_linobj_random_combinatorial.mjs';

console.log('=== Running Random Combinatorial Mutation Gate (200 N-Way Vectors) ===\n');

const res = await runRandomCombinatorialCampaign(200);

assert.equal(res.FN, 0, 'Zero Under-invalidation required (FN must be strictly 0)');
assert.equal(res.FP, 0, 'Zero Over-invalidation achieved on random compositions');
assert.equal(res.underInvalidationRate, 0.0, 'Under-invalidation rate must be 0.00%');
assert.equal(res.recall, 1.0, 'Soundness / Recall must be 100.00%');
assert.equal(res.accuracy, 1.0, 'Global Accuracy must be 100.00%');

console.log('\n============================================================');
console.log('Random Combinatorial Mutation Gate PASSED with 100% Soundness & Precision.');
console.log('============================================================\n');
