import assert from 'node:assert/strict';
import { runMutationCampaign } from '../scripts/bench_linobj_mutation_campaign.mjs';

console.log('=== Running Automated Mutation Testing Suite (240 Automated Vectors) ===\n');

const res = await runMutationCampaign(240);

assert.equal(res.FN, 0, 'Soundness Failure: False Negatives (Under-invalidation) must be strictly 0');
assert.equal(res.underInvalidationRate, 0, 'Under-invalidation rate must be 0.00% across all 140 semantic mutations');
assert.equal(res.recall, 1.0, 'Recall / Soundness must be 100.00%');
assert.ok(res.accuracy >= 0.90, 'Overall statistical accuracy must be >= 90%');

console.log('\n============================================================');
console.log('Automated Mutation Testing Gate PASSED with 100% Soundness (0.00% Under-invalidation).');
console.log('============================================================\n');
