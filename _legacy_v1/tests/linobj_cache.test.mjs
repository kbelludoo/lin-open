import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { buildLinobj, saveLinobjToCache, loadLinobjFromCache, lowerLinobj } from '../src/linobj.mjs';

const testSrc = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=math_utils
~G{?=if #=for ^=ret :else}
!clamp(val,min,max){?(val<min){^min};?(val>max){^max};^val}
=ex{clamp}`;

const tmpCache = path.join(os.tmpdir(), `linobj_test_${Date.now().toString(36)}`);

// 1. Build linobj (Cold)
const linobj = buildLinobj(testSrc);
assert.ok(linobj.semantic_hash, 'semantic_hash must exist');
assert.equal(linobj.format_version, '1.1.0');
assert.equal(linobj.canonical_ir.functions[0].name, 'clamp');
assert.deepEqual(linobj.canonical_ir.functions[0].paramList, ['val', 'min', 'max']);
assert.ok(linobj.invariant_report?.verified !== false, 'invariants must be sound');

// 2. Save & Load from Cache
const filePath = saveLinobjToCache(linobj, tmpCache);
assert.ok(fs.existsSync(filePath), 'cache file must exist on disk');

const loaded = loadLinobjFromCache(linobj.semantic_hash, tmpCache);
assert.ok(loaded, 'must load from cache');
assert.equal(loaded.semantic_hash, linobj.semantic_hash);

// 3. Lowering to multiple targets
const targets = ['ts', 'js', 'py', 'go', 'rust', 'c', 'java'];
for (const t of targets) {
  const res = lowerLinobj(loaded, t);
  assert.ok(res.code, `emitted code for ${t} must not be empty`);
  assert.equal(res.target, t);
  assert.equal(res.semantic_hash, linobj.semantic_hash);
}

// 4. Behavioral execution check
const jsCode = lowerLinobj(loaded, 'js').code;
const evalWrapper = `(function(){\nconst module = { exports: {} };\nconst exports = module.exports;\n${jsCode}\nreturn typeof module.exports === 'function' ? module.exports : module.exports.clamp;\n})()`;
const fn = eval(evalWrapper);
assert.equal(fn(5, 0, 10), 5);
assert.equal(fn(-5, 0, 10), 0);
assert.equal(fn(15, 0, 10), 10);

// Cleanup
fs.rmSync(tmpCache, { recursive: true, force: true });
console.log('ok linobj_cache (.linobj cold/warm + multi-lowering + oracle behavior_eq)');
