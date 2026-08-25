import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { compileLia } from '../src/multi_emit.mjs';
import { emitOneTarget } from '../scripts/clone_lin_multi.mjs';

const lin = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!leftPad(str,len,ch){str=str+'';ch=ch||' ';pad='';#(i=0;i<len;i++){pad=pad+ch}^pad+str}
=ex{leftPad}`;

const work = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_leftpad_'));
const def = compileLia(lin, { exportMode: 'single', withMain: false, package: 'clonefn', className: 'LeftPad' });
assert.equal(def.target, 'ts', 'compileLia without --target must emit ts');

const targets = ['ts', 'js', 'py', 'go', 'rust', 'c', 'java'];
const rows = {};
for (const t of targets) {
  const emitted = compileLia(lin, {
    target: t, exportMode: 'single', withMain: false, package: 'clonefn', className: 'LeftPad',
  });
  assert.ok(emitted.code, `empty emit ${t}`);
  const row = emitOneTarget(lin, 'leftPad', t, work);
  rows[t] = row;
  console.log(t, row.status, (row.reason || '').slice(0, 160));
}
for (const t of ['ts', 'js', 'py', 'go', 'rust', 'java']) {
  assert.equal(rows[t].status, 'PASS', `${t}: ${rows[t].reason}`);
}
assert.notEqual(rows.c.status, 'FAIL', `c: ${rows.c.reason}`);
if (rows.c.status === 'SKIP') {
  assert.match(String(rows.c.reason || ''), /gcc_absent/, 'c SKIP only if gcc missing after retry');
}
console.log('ok emit_leftpad_all');
