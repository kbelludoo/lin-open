import assert from 'node:assert/strict';
import { getCcr002Signal, linPath } from '../../src/lin_ccr002_signal_load.mjs';
import { runCcr002BenchmarkV2 } from '../../scripts/bench_ai_context_death.mjs';

const proto = getCcr002Signal();
assert.equal(linPath(), 'src/lin_ccr002_signal.lin');
assert.equal(proto.ccr002Id(), 'CCR-002');
assert.equal(proto.ccr002Version(), '2.1.0');
assert.equal(proto.ccr002Status(), 'ACTIVE_CLAIM_BRAKE');
assert.equal(proto.questionOld(), 'Is LIN a better language?');
assert.match(proto.questionNow(), /verifiable memory/);
assert.equal(proto.thesisOld(), 'LIN is a language for AI');
assert.match(proto.thesisNow(), /verifiable cognitive continuity layer/);
assert.match(proto.softwareEq(), /decision_memory/);
assert.equal(proto.syntaxMayChange(), 1);
assert.equal(proto.linmetaAdvance(), 1);
assert.match(proto.mockProves(), /represent and apply/);
assert.match(proto.mockDoesNotProve(), /real models/);
assert.equal(proto.noMockConclusion(), 1);
assert.equal(proto.signalName(), 'ignored_semantic_signal');
assert.equal(proto.isIgnoredSignal(1, 0), 1);
assert.equal(proto.isIgnoredSignal(1, 1), 0);
assert.equal(proto.isIgnoredSignal(0, 0), 0);
assert.equal(proto.fakeScores(), 0);
assert.equal(proto.modelUnobserved(), 1);
assert.match(proto.nucleus(), /UNTOUCHED/);
assert.match(proto.groupA4(), /schema/);
assert.match(proto.groupBDiff(), /semantic_hash/);

const data = runCcr002BenchmarkV2({ runs: 20, seed: 100 });
assert.ok(data.summary.A4, 'Group A4 (just metadata) must exist');
assert.ok(data.summary.B, 'Group B must exist');
assert.equal(data.manifests[0].benchmark, 'CCR-002-v2.1');
assert.equal(data.claimBrake.noMockConclusion, true);
assert.match(data.claimBrake.thesis, /continuity/);
assert.equal(data.claimBrake.modelUnobserved, true);

assert.equal(data.summary.B.totalUnsafeAttempts, 0, 'LIN must keep unsafe_improvement_attempts at 0');
assert.equal(data.summary.B.totalIgnoredSignal, 0, 'LIN must not ignore a rule it understood');
assert.ok(
  data.summary.A4.totalIgnoredSignal > 0,
  'A4 must produce ignored_semantic_signal: understood=true compliance=false'
);
assert.ok(
  data.summary.A4.totalUnsafeAttempts > 0,
  'A4 still attempts unsafe improvement because schema is not a compiler gate'
);
assert.ok(
  data.summary.A1.totalIgnoredSignal < data.summary.A4.totalIgnoredSignal,
  'A1 mostly fails to reconstruct the rule; A4 knew and ignored it'
);

console.log('ok ccr002_v21_signal');
