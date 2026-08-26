import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from '../src/compiler.mjs';
import { runInMemory } from '../src/vm.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

describe('LIN Self-Hosting Test Suite (LIN Compiles LIN)', () => {
  it('Generation 1 compiler should compile simple functions', () => {
    const linSrc = fs.readFileSync(path.join(ROOT, 'src/lin_selfhost.lin'), 'utf8');
    const gen1 = runInMemory(compile(linSrc, { target: 'js' }).code);

    const prog = `@LIN:L1c:0.2
!add(a, b){ ^a + b; }
=ex{add}`;
    const res = gen1.compile(prog);
    const mod = runInMemory(res.js);
    assert.equal(mod.add(20, 22), 42);
  });

  it('Generation 2: LIN compiles its own compiler and runs self-hosted', () => {
    const linSrc = fs.readFileSync(path.join(ROOT, 'src/lin_selfhost.lin'), 'utf8');
    const gen1 = runInMemory(compile(linSrc, { target: 'js' }).code);
    
    // Gen 1 compiles compiler source to produce Gen 2
    const gen2Output = gen1.compile(linSrc);
    const gen2 = runInMemory(gen2Output.js);

    // Gen 2 compiles user code
    const testCode = `@LIN:L1c:0.2
!calc(x){
  if (x > 10) { ^x * 2; }
  ^x + 100;
}
=ex{calc}`;
    const userRes = gen2.compile(testCode);
    const userMod = runInMemory(userRes.js);

    assert.equal(userMod.calc(15), 30);
    assert.equal(userMod.calc(5), 105);
  });
});
