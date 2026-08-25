import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  failClass, isStubLin, gateFrom, wrapCandidate, proposeCandidate,
  autoGenerateFromFails,
} from '../scripts/lin_auto_generate.mjs';
import { improveLinFromClone } from '../scripts/clone_lin_improve.mjs';

assert.equal(failClass('async_gen:Unexpected token \':\''), 'ASYNC_GEN');
assert.equal(failClass('holdout_mismatch'), 'HOLDOUT');
assert.equal(failClass('extract_missed'), 'EXTRACT_MISSED');
assert.equal(isStubLin(wrapCandidate('foo', 'x', '^null')), true);
assert.equal(gateFrom(true, 1, true), 'STUB_NOT_PASS');
assert.equal(gateFrom(true, null, true), 'STUB_NOT_PASS');
assert.equal(gateFrom(true, 1, false), 'BEHAVIOR_EQ_PASS');
assert.equal(gateFrom(false, null, false), 'COMPILE_FAIL');
assert.equal(gateFrom(true, 0, false), 'BEHAVIOR_EQ_FAIL');
assert.equal(gateFrom(true, null, false), 'COMPILE_OK_NO_ORACLE');

const stub = proposeCandidate({ name: 'randomUuid', lia: null });
assert.equal(isStubLin(stub), true);

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_autogen_'));
const storage = path.join(dir, 'storage');
const cand = path.join(dir, 'candidates');
const fails = [
  { status: 'fail', name: 'createArtifactParser', reason: 'async_gen:Unexpected token \':\'' },
  { status: 'fail', name: 'randomUuid', reason: 'holdout_mismatch', behavior_eq: 0 },
  { status: 'fail', name: 'createTerminalService', reason: 'extract_missed' },
];
const gen = autoGenerateFromFails(dir, cand, fails, 'open-design');
assert.equal(gen.n, 3);
assert.equal(gen.rows.every((r) => r.gate !== 'BEHAVIOR_EQ_PASS'), true);
assert.equal(gen.rows.every((r) => r.stub === true || r.gate === 'BEHAVIOR_EQ_FAIL' || r.gate === 'COMPILE_FAIL' || r.gate === 'STUB_NOT_PASS' || r.gate === 'COMPILE_OK_NO_ORACLE'), true);
for (const r of gen.rows) {
  assert.equal(fs.existsSync(r.path), true);
  assert.equal(fs.existsSync(r.path.replace(/\.lin$/, '.rulel')), true);
  assert.doesNotMatch(fs.readFileSync(r.path.replace(/\.lin$/, '.rulel'), 'utf8'), /gate=BEHAVIOR_EQ_PASS/);
}
assert.match(gen.summary, /createArtifactParser:/);
assert.match(gen.summary, /randomUuid:/);

const improved = improveLinFromClone(dir, storage, cand, fails, 'open-design');
assert.match(improved.candidate, /\.rulel$/);
assert.match(improved.summary, /autogen=/);
assert.doesNotMatch(improved.summary, /BEHAVIOR_EQ_PASS/);

fs.rmSync(dir, { recursive: true, force: true });
console.log('ok lin_auto_generate');
