/**
 * Canonical Merkle DAG Oracle & Differential Gate Suite
 * Spec: spec/LIN_SEMANTIC_MERKLE_DAG.rulel
 */

import assert from 'node:assert/strict';
import { hashJsFunctionSource, hashAppMerkleRoot } from '../src/semantic_merkle_hasher.mjs';
import { SemanticMerkleDagStore } from '../src/semantic_merkle_dag.mjs';

console.log('================================================================================');
console.log('   LIN SEMANTIC MERKLE DAG ORACLE & DIFFERENTIAL GATE TEST SUITE               ');
console.log('================================================================================\n');

let totalChecks = 0;
let passedChecks = 0;

function check(desc, condition) {
  totalChecks++;
  if (condition) {
    passedChecks++;
    console.log(`  ✔ [PASS] ${desc}`);
  } else {
    console.log(`  ❌ [FAIL] ${desc}`);
  }
}

// ---------------------------------------------------------------------------------
// GATE 1: CANONICAL COLLAPSE (Semantic Equivalences MUST produce identical hashes)
// ---------------------------------------------------------------------------------
console.log('▶ [GATE 1: CANONICAL COLLAPSE TEST - Identical Observational Semantics]');

// Equivalence Class A: Simple addition (renaming, function vs arrow, redundant parens)
const addVariants = [
  'function add(a, b) { return a + b; }',
  'function sum(x, y) { return x + y; }',
  'function plus(p1, p2) { return (p1 + p2); }',
  'const add = (a, b) => a + b;',
  'const calc = (first, second) => { return first + second; };',
  'function doAdd(numA, numB) { /* comment */ return ((((numA + numB)))); }'
];

const baseAddHash = hashJsFunctionSource(addVariants[0]).hash;
console.log(`  -> Equivalence Class A (Add) Canonical Hash: ${baseAddHash}`);

for (let i = 1; i < addVariants.length; i++) {
  const vHash = hashJsFunctionSource(addVariants[i]).hash;
  check(`Add variant #${i + 1} (${addVariants[i].slice(0, 35)}...) matches base hash`, vHash === baseAddHash);
}

// Equivalence Class B: Conditional statement branches
const condVariants = [
  'function isPositive(n) { if (n > 0) { return true; } else { return false; } }',
  'function checkSign(val) { if (val > 0) return true; else return false; }',
  'const isPos = x => { if (x > 0) { return true; } else { return false; } };',
  'function testNum(item) { if ((item > 0)) { return true; } else { return false; } }'
];

const baseCondHash = hashJsFunctionSource(condVariants[0]).hash;
console.log(`\n  -> Equivalence Class B (If/Else Statements) Canonical Hash: ${baseCondHash}`);

for (let i = 1; i < condVariants.length; i++) {
  const vHash = hashJsFunctionSource(condVariants[i]).hash;
  check(`Cond variant #${i + 1} (${condVariants[i].slice(0, 35)}...) matches base hash`, vHash === baseCondHash);
}

// Equivalence Class C: Ternary Expressions
const ternaryVariants = [
  'function isPositive(n) { return n > 0 ? true : false; }',
  'const isPos = x => (x > 0 ? true : false);',
  'const check = (val) => { return ((val > 0) ? true : false); };'
];

const baseTernaryHash = hashJsFunctionSource(ternaryVariants[0]).hash;
console.log(`\n  -> Equivalence Class C (Ternary Expressions) Canonical Hash: ${baseTernaryHash}`);

for (let i = 1; i < ternaryVariants.length; i++) {
  const vHash = hashJsFunctionSource(ternaryVariants[i]).hash;
  check(`Ternary variant #${i + 1} (${ternaryVariants[i].slice(0, 35)}...) matches base hash`, vHash === baseTernaryHash);
}

// Combinatorial 100-Variant Equivalence Sweep
console.log('\n  -> Running 100-Variant Combinatorial Equivalence Sweep...');
const varNames = ['a', 'b', 'c', 'd', 'e', 'x', 'y', 'z', 'u', 'v', 'val1', 'val2', 'left', 'right'];
let sweepCollapses = 0;
for (let i = 0; i < 100; i++) {
  const p1 = varNames[i % varNames.length];
  const p2 = varNames[(i + 1) % varNames.length];
  const src = `function fn_${i}(${p1}, ${p2}) { return (${p1} * 2) + (${p2} * 3); }`;
  const h = hashJsFunctionSource(src).hash;
  const canonicalH = hashJsFunctionSource('function base(arg0, arg1) { return (arg0 * 2) + (arg1 * 3); }').hash;
  if (h === canonicalH) sweepCollapses++;
}
check(`100/100 combinatorial variable renaming variations collapsed to canonical hash`, sweepCollapses === 100);

// ---------------------------------------------------------------------------------
// GATE 2: OBSERVATIONAL DISTINCTION (Semantically distinct programs MUST NOT collide)
// ---------------------------------------------------------------------------------
console.log('\n▶ [GATE 2: OBSERVATIONAL DISTINCTION TEST - Distinct Observational Semantics]');

// Distinct 1: Operand Order (a + b vs b + a)
const h_ab = hashJsFunctionSource('function f(a, b) { return a + b; }').hash;
const h_ba = hashJsFunctionSource('function f(a, b) { return b + a; }').hash;
check('a + b vs b + a produce DISTINCT hashes (preserves operand evaluation order)', h_ab !== h_ba);

// Distinct 2: Update Prefix vs Postfix (x++ vs ++x)
const h_post = hashJsFunctionSource('function f(x) { return x++; }').hash;
const h_pre = hashJsFunctionSource('function f(x) { return ++x; }').hash;
check('x++ vs ++x produce DISTINCT hashes (preserves update semantics)', h_post !== h_pre);

// Distinct 3: Side Effect vs Pure (console.log vs pure identity)
const h_pure = hashJsFunctionSource('function f(x) { return x; }');
const h_io = hashJsFunctionSource('function f(x) { console.log(x); return x; }');
check('Pure identity vs IO console.log produce DISTINCT hashes and effect signatures', h_pure.hash !== h_io.hash && h_pure.effect === 'Pure' && h_io.effect === 'IO');

// Distinct 4: Comparison Operators (< vs <= vs > vs >= vs == vs !=)
const ops = ['<', '<=', '>', '>=', '==', '!=', '+', '-', '*', '/', '%'];
const opHashes = new Set();
for (const op of ops) {
  const h = hashJsFunctionSource(`function f(a, b) { return a ${op} b; }`).hash;
  opHashes.add(h);
}
check(`All ${ops.length} operators produced pairwise distinct hashes (100% collision-free)`, opHashes.size === ops.length);

// Combinatorial 100-Pair Distinction Sweep
console.log('  -> Running 100-Pair Distinction Sweep across distinct computational shapes...');
let distinctPasses = 0;
for (let i = 0; i < 100; i++) {
  const srcA = `function opA_${i}(x, y) { return (x + ${i}) * y; }`;
  const srcB = `function opB_${i}(x, y) { return (x + ${i + 1}) * y; }`;
  const hA = hashJsFunctionSource(srcA).hash;
  const hB = hashJsFunctionSource(srcB).hash;
  if (hA !== hB) distinctPasses++;
}
check(`100/100 distinct computations produced distinct hashes`, distinctPasses === 100);

// ---------------------------------------------------------------------------------
// GATE 3: STRUCTURAL MERKLE DEDUPLICATION
// ---------------------------------------------------------------------------------
console.log('\n▶ [GATE 3: STRUCTURAL MERKLE DEDUPLICATION TEST]');

const store = new SemanticMerkleDagStore();

// Simulate 5 modules each declaring their own utility functions (some identical, some distinct)
const moduleCode = [
  'function clamp(x, min, max) { if (x < min) return min; if (x > max) return max; return x; }',
  'function clamp(val, low, high) { if (val < low) return low; if (val > high) return high; return val; }',
  'function clamp(n, a, b) { if (n < a) return a; if (n > b) return b; return n; }',
  'function add(a, b) { return a + b; }',
  'function sum(x, y) { return x + y; }',
  'function multiply(a, b) { return a * b; }'
];

for (const code of moduleCode) {
  const { ir } = hashJsFunctionSource(code);
  store.insert(ir);
}

const ratio = store.getDeduplicationRatio();
console.log(`  - Total nodes inserted: ${store.totalEncountered}`);
console.log(`  - Unique nodes in Merkle DAG: ${store.nodes.size}`);
console.log(`  - Deduplication ratio: ${ratio}x`);

check('Merkle DAG store achieved structural deduplication (> 1.0x ratio)', ratio > 1.0);
check('All 3 clamp variations collapsed to 1 unique Merkle node', store.nodes.size === 3); // clamp, add, multiply

// ---------------------------------------------------------------------------------
// GATE 4: CRYPTOGRAPHIC PROOF LEDGER VALIDATION
// ---------------------------------------------------------------------------------
console.log('\n▶ [GATE 4: PROOF LEDGER CERTIFICATE VALIDATION]');

const provenHash = hashJsFunctionSource('function clamp(x, min, max) { if (x < min) return min; if (x > max) return max; return x; }').hash;

const cert = store.registerProofCertificate({
  semantic_hash: provenHash,
  source_language: 'javascript',
  target: 'lin',
  oracle: 'node_v24_js_oracle',
  test_suite_hash: 'abc123suite',
  behavior_eq: 1.0
});

check('Certificate successfully registered with behavior_eq: 1.0', cert && cert.behavior_eq === 1.0);

const verifyResult = store.verifyCertificate(provenHash);
check('Certificate verification passes for valid hash and version', verifyResult.valid === true);

const mismatchVerify = store.verifyCertificate(provenHash, '2.0-incompatible');
check('Certificate verification correctly rejects incompatible canonicalization version', mismatchVerify.valid === false);

// Summary
console.log('\n================================================================================');
console.log(`   CANONICAL MERKLE DAG GATE SUMMARY: ${passedChecks}/${totalChecks} CHECKS PASSED     `);
console.log('================================================================================\n');

if (passedChecks === totalChecks) {
  process.exit(0);
} else {
  process.exit(1);
}
