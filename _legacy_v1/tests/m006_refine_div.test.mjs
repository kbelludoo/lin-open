import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../src/compiler.mjs';
import { compileLia } from '../src/multi_emit.mjs';
import { emitJs } from '../src/emit_js.mjs';

const fx = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'm006');
const unsafe = fs.readFileSync(path.join(fx, 'div_unsafe.lin'), 'utf8');
const refined = fs.readFileSync(path.join(fx, 'div_refined.lin'), 'utf8');
const requireLin = fs.readFileSync(path.join(fx, 'div_require.lin'), 'utf8');

const blocked = /EMIT BLOCKED INV_REFINEMENT_SOUND/;
const nodeDiv = /Node: BinaryExpression \//;
const missing = /Missing: b > 0/;
const repairs = /repairs: refine b:int\{>0\} \| require b>0 \| insert check/;

function expectBlocked(fn) {
  assert.throws(fn, blocked);
  assert.throws(fn, nodeDiv);
  assert.throws(fn, missing);
  assert.throws(fn, repairs);
}

expectBlocked(() => compileLiaToJs(unsafe));
expectBlocked(() => emitJs(unsafe));
expectBlocked(() => compileLia(unsafe, { target: 'ts' }));
expectBlocked(() => compileLia(unsafe, { target: 'js' }));

const ok = compileLiaToJs(refined);
assert.match(ok.js, /function divSafe/);
assert.doesNotMatch(ok.js, /EMIT BLOCKED/);

const okReq = compileLiaToJs(requireLin);
assert.match(okReq.js, /function divReq/);

const ts = compileLia(refined, { target: 'ts' });
assert.ok(ts.code, 'refined ts emit empty');

const add = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=m006_no_div
~G{?=if #=for ^=ret :else}
!add(a,b){^a+b}
=ex{add}`;
assert.match(compileLiaToJs(add).js, /function add/);

console.log('ok m006_refine_div');
