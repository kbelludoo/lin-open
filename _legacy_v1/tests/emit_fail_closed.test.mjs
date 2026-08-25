import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs, compileLiaFile, parseLia } from '../src/compiler.mjs';
import { emitJs } from '../src/emit_js.mjs';
import { assertJsParse, jsSyntaxCheck } from '../src/js_syntax_check.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fx = path.join(root, 'tests', 'fixtures', 'fail_closed');

function load(name) {
  return fs.readFileSync(path.join(fx, name), 'utf8');
}

function mustParse(js) {
  const { ok, detail } = jsSyntaxCheck(js);
  assert.equal(ok, true, detail);
}

assert.equal(jsSyntaxCheck('return ({ok:true})for(i=0;i<1;i++){}').ok, false);
assert.throws(() => assertJsParse('return ({ok:true})for(i=0;i<1;i++){}'), /LIN_EMIT_JS_SYNTAX/);

const objJs = compileLiaToJs(load('object_return.lin')).js;
assert.match(objJs, /return \(\{ok:true,n:n\}\)/);
assert.doesNotMatch(objJs, /else\{/);
mustParse(objJs);

const walkJs = compileLiaToJs(load('object_then_for.lin')).js;
assert.match(walkJs, /return \(\{ok:true\}\);for\(/);
assert.doesNotMatch(walkJs, /return \(\{ok:true\}\)for\(/);
mustParse(walkJs);

const progK = parseLia(load('multi_k.lin'));
assert.deepEqual(progK.consts, { a: '1', b: '2', c: '3', d: '4' });
const kJs = compileLiaToJs(load('multi_k.lin')).js;
assert.match(kJs, /"a":1/);
assert.match(kJs, /"c":3/);
mustParse(kJs);

const nestJs = compileLiaToJs(load('nested_object.lin')).js;
assert.match(nestJs, /\{k:\{a:1\},url:\(1\+2\)\}/);
assert.doesNotMatch(nestJs, /else\{|else if\(/);
mustParse(nestJs);

const strJs = compileLiaToJs(load('string_colon.lin')).js;
assert.match(strJs, /'a:\{b\}'/);
assert.doesNotMatch(strJs, /aelse/);
mustParse(strJs);

const elseJs = compileLiaToJs(load('if_else_object.lin')).js;
assert.match(elseJs, /else\{return \(\{a:0\}\);\}/);
mustParse(elseJs);

assert.throws(() => compileLiaToJs(load('export_missing.lin')), /LIN_EXPORT_NO_FN:\s*ghost/);
assert.throws(() => emitJs(load('export_missing.lin')), /LIN_EXPORT_NO_FN/);

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_fail_closed_'));
const dest = path.join(tmp, 'out.cjs');
const missingPath = path.join(fx, 'export_missing.lin');
assert.throws(() => compileLiaFile(missingPath, dest), /LIN_EXPORT_NO_FN/);
assert.equal(fs.existsSync(dest), false);

const okDest = path.join(tmp, 'pack.cjs');
compileLiaFile(path.join(fx, 'object_return.lin'), okDest);
assert.equal(fs.existsSync(okDest), true);
mustParse(fs.readFileSync(okDest, 'utf8'));

console.log('ok emit_fail_closed');
