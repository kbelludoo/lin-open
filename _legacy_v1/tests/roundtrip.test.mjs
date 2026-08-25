import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs, parseLia } from '../src/compiler.ts';
import { LIN_HEADER, LIA_HEADER } from '../src/emitter.mjs';
import { parseRulel, validateComms } from '../src/rulel_parser.mjs';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = fs.readFileSync(path.join(root, 'examples', 'safe-compare.lia'), 'utf8');

assert.ok(src.startsWith('@LIN:'), 'example must use @LIN header');
assert.equal(LIN_HEADER, '@LIN:L1c:0.2');
assert.equal(LIA_HEADER, LIN_HEADER);

const { js, program } = compileLiaToJs(src, { exportMode: 'single' });
assert.equal(program.fns[0].name, 'safeCompare');

function runJsInMemory(jsCode) {
  const m = { exports: {} };
  const fn = new Function('module', 'exports', 'require', 'Buffer', jsCode + '\nreturn module.exports;');
  return fn(m, m.exports, createRequire(import.meta.url), Buffer);
}
const fn = runJsInMemory(js);

assert.equal(fn('ab', 'ab'), true);
assert.equal(fn('a', 'b'), false);
assert.equal(fn('prefix', 'pre'), false);
assert.equal(fn('', ''), true);

// Dual-read legacy @LIA and @AIL
for (const [tag, hdr] of [['@LIA:', '@LIA:L1c:0.2'], ['@AIL:', '@AIL:L1c:0.2']]) {
  const legacy = src.replace('@LIN:', tag);
  const prog = parseLia(legacy);
  assert.equal(prog.header, hdr);
  const { js: jsL } = compileLiaToJs(legacy, { exportMode: 'single' });
  assert.equal(runJsInMemory(jsL)('ab', 'ab'), true);
}

// Closure roundtrip: nested function must capture outer variable.
const closureLia = `${LIN_HEADER}
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!makeAdd(n){add=~(x){^n+x};^add}
=ex{makeAdd}`;
const { js: closureJs } = compileLiaToJs(closureLia, { exportMode: 'single' });
const add5 = runJsInMemory(closureJs)(5);
assert.equal(typeof add5, 'function');
assert.equal(add5(10), 15);
assert.equal(add5(3), 8);

// Effect inference smoke: each fn gets expected effect annotation.
const effectLia = `${LIN_HEADER}
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!pureAdd(a,b){^a+b}
!nativeLen(s){^String(s).length}
!throwIfNeg(x){?(x<0){throw new Error('neg')};^x}
=ex{pureAdd,nativeLen,throwIfNeg}`;
const effectResult = compileLiaToJs(effectLia, { exportMode: 'multiple' });
const effects = Object.fromEntries(effectResult.program.fns.map((f) => [f.name, f.effect]));
assert.equal(effects.pureAdd, 'Pure');
assert.equal(effects.nativeLen, 'Native');
assert.equal(effects.throwIfNeg, 'Throw');
assert.ok(effectResult.js.includes('/* effect:Pure */'));
assert.ok(effectResult.js.includes('/* effect:Native */'));

// Sandbox smoke: Native fn blocked when only Pure allowed.
const sandboxResult = compileLiaToJs(effectLia, { exportMode: 'multiple', sandbox: ['Pure'] });
const sandboxMod = runJsInMemory(sandboxResult.js);
assert.equal(sandboxMod.pureAdd(2, 3), 5);
assert.throws(() => sandboxMod.nativeLen('x'), /LIN_SANDBOX.*Native/);

// RULEL parser smoke
const rulelText = fs.readFileSync(path.join(root, 'spec', 'COMMS_PROTOCOL.rulel'), 'utf8');
const rulelParsed = parseRulel(rulelText);
assert.equal(rulelParsed.header.id, 'COMMS_PROTOCOL');
assert.equal(rulelParsed.header.semver, '1.4.0');
assert.ok(rulelParsed.blocks.m);
assert.ok(rulelParsed.blocks.r);
const rulelValidation = validateComms(rulelParsed);
assert.equal(rulelValidation.ok, true);

console.log('ok roundtrip safe-compare (+ @LIN/@LIA/@AIL dual-read) + closure capture + effects + sandbox + rulel');
