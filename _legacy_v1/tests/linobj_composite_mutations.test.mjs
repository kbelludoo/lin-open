import assert from 'node:assert/strict';
import { runCompositeBenchmark } from '../scripts/bench_linobj_composite_mutations.mjs';

console.log('=== Running Composite Combinatorial Mutation Gate ===\n');

const res = await runCompositeBenchmark();

assert.equal(res.passed, res.total, 'All composite mutation scenarios must pass with 100% precision');

console.log('\n============================================================');
console.log('Composite Combinatorial Mutation Gate PASSED (100%).');
console.log('============================================================\n');
