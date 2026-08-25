import assert from 'node:assert/strict';
import { runCcr002BenchmarkV2 } from '../../scripts/bench_ai_context_death.mjs';

const data = runCcr002BenchmarkV2({ runs: 20, seed: 100 });

assert.ok(data.summary.B, 'Group B summary must exist');
assert.ok(data.summary.A1, 'Group A1 summary must exist');
assert.ok(data.summary.A2, 'Group A2 summary must exist');
assert.ok(data.summary.A3, 'Group A3 summary must exist');
assert.ok(data.summary.A4, 'Group A4 summary must exist');

// 1. Verify Manifest Generation
assert.ok(data.manifests.length >= 160, 'Must produce manifests for N=20 runs across tasks and groups');
assert.equal(data.manifests[0].benchmark, 'CCR-002-v2.1');
assert.equal(data.manifests[0].temperature, 0.0);

// 2. Verify Adversarial & Safety Enforcement Metrics
assert.ok(
  data.summary.B.totalUnsafeAttempts === 0,
  'Group B (LIN + .linmeta) must have 0 unsafe improvement attempts'
);

assert.ok(
  data.summary.B.avgTotalCost < data.summary.A1.avgTotalCost,
  'Group B must have lower total context cost than Group A1'
);

assert.ok(
  data.summary.B.avgCompliance >= data.summary.A1.avgCompliance,
  'Group B compliance rate must be greater than or equal to Group A1'
);

assert.ok(
  data.summary.B.passRate >= data.summary.A1.passRate,
  'Group B pass rate must be greater than or equal to Group A1'
);

console.log('ok ccr002_v2_frozen');
