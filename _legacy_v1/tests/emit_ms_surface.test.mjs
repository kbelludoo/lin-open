import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { emitAilFromSource, harvestTopNumConsts } from '../src/emitter.mjs';
import { emitOneTarget } from '../scripts/clone_lin_multi.mjs';
import { parseStmts } from '../src/body_ast.mjs';

const harvested = harvestTopNumConsts('const s=1000; const m=s*60; const y=d*365.25; const d=86400000;');
assert.equal(harvested.s, 1000);
assert.equal(harvested.m, 60000);
const innerLet = harvestTopNumConsts('function f(){ let from = 0; const inner = 3; }\nconst s = 1000;');
assert.equal(innerLet.from, undefined);
assert.equal(innerLet.inner, undefined);
assert.equal(innerLet.s, 1000);

const asiSrc = `function fillRandom(buffer){
  let from = 0;
  while (from < buffer.length) {
    let to = Math.min(from + 65536, buffer.length);
    crypto.getRandomValues(buffer.subarray(from, to));
    from = to
  }
}
function error(msg){
  process.stderr.write(msg + '\\n');
  process.exit(1)
}`;
const asiLin = emitAilFromSource(asiSrc, { shortenLocals: false });
assert.match(asiLin, /getRandomValues/);
assert.match(asiLin, /process\.stderr/);
assert.doesNotMatch(asiLin, /\)\s*crypto\./);
assert.doesNotMatch(asiLin, /\)\s*process\.exit/);

const retArrow = emitAilFromSource(
  'function customAlphabet(alphabet, defaultSize){ if (!alphabet) return customRandom(alphabet);\nreturn (size = defaultSize) => { if (!size) return ""; return size; }; }',
  { shortenLocals: false },
);
assert.match(retArrow, /~\(size=defaultSize\)/);
assert.doesNotMatch(retArrow, /\^\(size=defaultSize\)=>/);
assert.doesNotMatch(retArrow, /\|\|;/);
assert.doesNotMatch(retArrow, /\|\=\s*0\s+if\b/);

const throwLin = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!boom(value){?(typeof value!='string'){throw new Error( ("must be a string or number. value="+(JSON.stringify(value))),)}^value}
=ex{boom}`;

const work = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_ms_surf_'));
for (const t of ['py', 'go', 'rust', 'java']) {
  const row = emitOneTarget(throwLin, 'boom', t, work);
  assert.equal(row.status, 'PASS', `${t} throw: ${row.reason}`);
}

const sw = parseStmts("switch (u){case 'y': case 'year':;^n*y;default: throw new Error('bad')}");
assert.equal(sw[0].type, 'if');
assert.match(sw[0].cond, /u=='y'/);

const src = `
const s = 1000;
const m = s * 60;
function fmtShort(ms){ const msAbs = Math.abs(ms); if (msAbs >= m) return Math.round(ms / m) + 'm'; return ms + 'ms'; }
`;
const fileLia = emitAilFromSource(src, { shortenLocals: false });
assert.match(fileLia, /\$K\{/);
assert.match(fileLia, /\bm=/);
const fileRow = emitOneTarget(fileLia.replace(/^@LIA:/, '@LIN:').replace(/^@AIL:/, '@LIN:'), 'FmtShort', 'py', work);
assert.equal(fileRow.status, 'PASS', `file py: ${fileRow.reason}`);

const defLin = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!nanoid(size=21){^size}
=ex{nanoid}`;
for (const t of ['go', 'rust', 'java', 'ts', 'py']) {
  const row = emitOneTarget(defLin, 'nanoid', t, work);
  assert.equal(row.status, 'PASS', `${t} defaults: ${row.reason}`);
}

console.log('ok emit_ms_surface');
