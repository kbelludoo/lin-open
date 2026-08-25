// Test: Polyglot Multi-Language Transpiler into LIN (Py, Rust, Go, C, Zig, JS)
// Spec: spec/LIN_IR_CROSS_BACKEND.rulel

import assert from 'node:assert/strict';
import { transpileToLin, transpileToLinWithManifest } from '../src/transpiler_to_lin.mjs';
import { compile } from '../src/compiler.mjs';
import { runInMemory } from '../src/vm.mjs';

function getFn(mod, name) {
  if (typeof mod === 'function') return mod;
  return mod[name] || mod[name.replace(/_([a-z])/g, (_, c) => c.toUpperCase())];
}

console.log("================================================================================");
console.log("   TEST SUITE: POLYGLOT COMPILER TO LIN (Py, Rust, Go, C, Zig, JS)            ");
console.log("================================================================================");

// 1. Python -> LIN -> JS execution
console.log("\n[+] 1. Python -> LIN Transpilation & In-Memory Execution...");
const pyCode = `
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

def is_positive(x):
    if x > 0:
        return True
    else:
        return False
`;
const linFromPy = transpileToLin(pyCode, { filename: 'algo.py' });
assert.ok(linFromPy.includes('!fib(n){'));
assert.ok(linFromPy.includes('=ex{fib, is_positive}'));

const jsModPy = runInMemory(compile(linFromPy, { target: 'js' }).code);
const fibFn = getFn(jsModPy, 'fib');
const isPosFn = getFn(jsModPy, 'is_positive');
assert.equal(fibFn(7), 13);
assert.equal(isPosFn(42), true);
assert.equal(isPosFn(-5), false);
console.log("    -> JS in-memory execution: fib(7)=13, is_positive(42)=true, is_positive(-5)=false [PASS]");

// 2. Rust -> LIN -> JS execution
console.log("\n[+] 2. Rust -> LIN Transpilation & In-Memory Execution...");
const rustCode = `
pub fn mul_add(a: i64, b: i64, c: i64) -> i64 {
    let mut res = a * b;
    res = res + c;
    return res;
}
`;
const linFromRust = transpileToLin(rustCode, { filename: 'math.rs' });
assert.ok(linFromRust.includes('!mul_add(a,b,c){'));
const jsModRs = runInMemory(compile(linFromRust, { target: 'js' }).code);
const mulAddFn = getFn(jsModRs, 'mul_add');
assert.equal(mulAddFn(3, 4, 5), 17);
console.log("    -> JS in-memory execution: mul_add(3, 4, 5)=17 [PASS]");

// 3. Go -> LIN -> JS execution
console.log("\n[+] 3. Go -> LIN Transpilation & In-Memory Execution...");
const goCode = `
func clamp(val int, min int, max int) int {
    if val < min {
        return min;
    } else if val > max {
        return max;
    }
    return val;
}
`;
const linFromGo = transpileToLin(goCode, { filename: 'util.go' });
assert.ok(linFromGo.includes('!clamp(val,min,max){'));
const jsModGo = runInMemory(compile(linFromGo, { target: 'js' }).code);
const clampFn = getFn(jsModGo, 'clamp');
assert.equal(clampFn(5, 10, 20), 10);
assert.equal(clampFn(25, 10, 20), 20);
assert.equal(clampFn(15, 10, 20), 15);
console.log("    -> JS in-memory execution: clamp(5,10,20)=10, clamp(25,10,20)=20 [PASS]");

// 4. C -> LIN -> JS execution
console.log("\n[+] 4. C -> LIN Transpilation & In-Memory Execution...");
const cCode = `
int gcd(int a, int b) {
    while (b != 0) {
        int t = b;
        b = a % b;
        a = t;
    }
    return a;
}
`;
const linFromC = transpileToLin(cCode, { filename: 'math.c' });
assert.ok(linFromC.includes('!gcd(a,b){'));
const jsModC = runInMemory(compile(linFromC, { target: 'js' }).code);
const gcdFn = getFn(jsModC, 'gcd');
assert.equal(gcdFn(48, 18), 6);
console.log("    -> JS in-memory execution: gcd(48, 18)=6 [PASS]");

// 5. Zig -> LIN -> JS execution
console.log("\n[+] 5. Zig -> LIN Transpilation & In-Memory Execution...");
const zigCode = `
pub fn square_sum(a: i64, b: i64) i64 {
    return (a * a) + (b * b);
}
`;
const linFromZig = transpileToLin(zigCode, { filename: 'geo.zig' });
assert.ok(linFromZig.includes('!square_sum(a,b){'));
const jsModZig = runInMemory(compile(linFromZig, { target: 'js' }).code);
const squareSumFn = getFn(jsModZig, 'square_sum');
assert.equal(squareSumFn(3, 4), 25);
console.log("    -> JS in-memory execution: square_sum(3, 4)=25 [PASS]");

console.log("\n================================================================================");
console.log("   POLYGLOT MULTI-LANGUAGE TRANSPILER: ALL 5 LANGUAGES PASSED 100%             ");
console.log("================================================================================");

// 6. JS/TS -> Semantic Closure -> Specialized LIN -> JS execution
console.log("\n[+] 6. JS/TS -> Semantic Closure Pipeline & Capability Manifest...");
const jsPipelineCode = `
function processItems(numbers) {
    return numbers.filter(x => x > 10).map(x => x * 2).join(",");
}
`;
const { lin: linFromPipeline, manifest, coverage } = transpileToLinWithManifest(jsPipelineCode, { filename: 'pipeline.js' });
assert.ok(linFromPipeline.includes('!processItems(numbers){'));
assert.equal(coverage, 1.0);
assert.equal(manifest.unresolved.length, 0);

const jsModPipeline = runInMemory(compile(linFromPipeline, { target: 'js' }).code);
const pipelineFn = getFn(jsModPipeline, 'processItems');
assert.equal(pipelineFn([5, 12, 8, 20, 3]), "24,40");
assert.equal(pipelineFn([1, 2]), "");
console.log("    -> JS in-memory execution: processItems([5, 12, 8, 20, 3])='24,40' [PASS]");
console.log("    -> Capability Manifest: ClosureCoverage=100.0%, host_required=[] [PASS]");
