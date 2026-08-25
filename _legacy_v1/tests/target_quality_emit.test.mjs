import assert from 'node:assert/strict';
import fs from 'node:fs';
import { compileLia } from '../src/multi_emit.mjs';

const lin = fs.readFileSync('tests/target_quality.lin', 'utf8');
const opts = { stubRuntime: false };

const rust = compileLia(lin, { ...opts, target: 'rust' });
assert.match(rust.code, /fn main\(\)/);
assert.doesNotMatch(rust.code, /factorial\("ab"/);
assert.doesNotMatch(rust.code, /JS-runtime-only/);
assert.match(rust.code, /-> i64/);
assert.match(rust.code, /let mut (res|total): i64 = 0/);
assert.doesNotMatch(rust.code, /_lia_cat\(&\(\(total\)/);
assert.match(rust.code, /for i in 2\.\.=n/);
assert.equal(rust.stub, false);

const go = compileLia(lin, { ...opts, target: 'go' });
assert.match(go.code, /func main\(\)/);
assert.doesNotMatch(go.code, /factorial\("ab"/);
assert.match(go.code, /_lia_num\(n\)%\s*2/);
assert.doesNotMatch(go.code, /_lia_num_lia_cat|_lia_cat\(total/);
assert.match(go.code, /_lia_num\(total\)\+_lia_num\(i\)|_lia_num\(n\)\+_lia_num\(n\)/);

const java = compileLia(lin, { ...opts, target: 'java' });
assert.match(java.code, /public static void main\(String\[\] args\)/);
assert.match(java.code, /factorial\(10\)/);

const c = compileLia(lin, { ...opts, target: 'c' });
assert.match(c.code, /int main\(void\)/);
assert.doesNotMatch(c.code, /_lia_cat_c\(total/);
assert.match(c.code, /factorial\(10\)/);

const ts = compileLia(lin, { ...opts, target: 'ts' });
assert.match(ts.code, /export function factorial|function factorial/);

console.log('ok target_quality_emit');
