import assert from 'node:assert/strict';
import { runCcr002Benchmark } from '../../scripts/bench_ai_context_death.mjs';

const data = runCcr002Benchmark({ seed: 42 });

assert.ok(data.summary.B, 'Group B summary must exist');
assert.ok(data.summary.A1, 'Group A1 summary must exist');
assert.ok(data.summary.A2, 'Group A2 summary must exist');
assert.ok(data.summary.A3, 'Group A3 summary must exist');
assert.ok(data.summary.A4, 'Group A4 summary must exist');

// Verify that Group B (LIN + .linmeta) outperforms traditional representations on cognitive efficiency & human inquiries
assert.ok(
  data.summary.B.avgTotalCost < data.summary.A1.avgTotalCost,
  'Group B must have lower total context cost than Group A1'
);
assert.ok(
  data.summary.B.totalHumanInquiries <= data.summary.A1.totalHumanInquiries,
  'Group B must require fewer human inquiries than Group A1'
);
assert.ok(
  data.summary.B.passRate >= data.summary.A1.passRate,
  'Group B pass rate must be greater or equal to Group A1'
);

console.log('ok ccr002_context_death');
