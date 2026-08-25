import assert from 'node:assert/strict';
import { runRealWorldMutationBenchmark } from '../scripts/bench_linobj_real_world_mutation_oracle.mjs';

console.log('=== Running Real-World Multi-Repository Mutation Benchmark with Deep Oracle ===\n');

const res = await runRealWorldMutationBenchmark();

assert.equal(res.totalFN, 0, 'Zero Under-invalidation required across real-world production corpus (FN == 0)');
assert.equal(res.grandUnderInvalidation, 0.0, 'Under-invalidation rate against deep adversarial oracle must be 0.00%');
assert.equal(res.grandRecall, 1.0, 'Soundness / Recall against deep adversarial oracle must be 100.00%');
assert.equal(res.totalTP, res.grandSemantic, 'All ground-truth semantic mutations must be correctly rebuilt');

console.log('\n============================================================');
console.log('Real-World Production Corpus Mutation Gate PASSED (100% Soundness).');
console.log('============================================================\n');
