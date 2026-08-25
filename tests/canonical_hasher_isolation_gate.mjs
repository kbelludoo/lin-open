/**
 * LIN Canonical Hasher Isolation Gate (100 Equivalent vs 100 Non-Equivalent Pairs)
 * Spec: spec/LIN_SEMANTIC_MERKLE_DAG.rulel
 */

import assert from 'node:assert/strict';
import { hashJsFunctionSource } from '../src/semantic_merkle_hasher.mjs';

console.log('================================================================================');
console.log('   LIN CANONICAL HASHER ISOLATION GATE: 100 EQUIV VS 100 NON-EQUIV PAIRS        ');
console.log('================================================================================\n');

let equivPassed = 0;
let equivFailed = 0;
let nonEquivPassed = 0;
let nonEquivFailed = 0;

// ---------------------------------------------------------------------------------
// 1. 100 EQUIVALENT PAIRS (H_left == H_right)
// ---------------------------------------------------------------------------------
console.log('▶ [PHASE 1: 100 EQUIVALENT PAIRS VERIFICATION]');

const equivalentPairs = [];

// Category A: Local variable and parameter renamings (20 pairs)
const varSets = [
  ['a', 'b', 'c'], ['x', 'y', 'z'], ['u', 'v', 'w'], ['p1', 'p2', 'p3'],
  ['first', 'second', 'third'], ['foo', 'bar', 'baz'], ['val1', 'val2', 'val3'],
  ['m', 'n', 'k'], ['alpha', 'beta', 'gamma'], ['left', 'right', 'temp']
];

for (let i = 0; i < 20; i++) {
  const [p1, p2, p3] = varSets[i % varSets.length];
  const [q1, q2, q3] = varSets[(i + 3) % varSets.length];
  equivalentPairs.push({
    category: 'Alpha-Renaming',
    left: `function fnA_${i}(${p1}, ${p2}) { let ${p3} = ${p1} * ${p2}; return ${p3} + 10; }`,
    right: `function fnB_${i}(${q1}, ${q2}) { let ${q3} = ${q1} * ${q2}; return ${q3} + 10; }`
  });
}

// Category B: Function Declarations vs Arrow Functions (20 pairs)
for (let i = 0; i < 20; i++) {
  const op = ['+', '-', '*', '%'][i % 4];
  equivalentPairs.push({
    category: 'Function vs Arrow',
    left: `function calc_${i}(x, y) { return (x ${op} y) + ${i}; }`,
    right: `const calc_${i} = (a, b) => (a ${op} b) + ${i};`
  });
}

// Category C: Redundant Parentheses, Whitespace, Comments, and Bracing (20 pairs)
for (let i = 0; i < 20; i++) {
  equivalentPairs.push({
    category: 'Syntax Formatting & Parens',
    left: `function clean_${i}(x) { if (x > ${i}) { return true; } else { return false; } }`,
    right: `function clean_${i}(val) { /* comment */ if (((val > ${i}))) return true; else return false; }`
  });
}

// Category D: Nested Closures with Captured Variables (20 pairs)
for (let i = 0; i < 20; i++) {
  equivalentPairs.push({
    category: 'Closure & Capture Isolation',
    left: `function outerA_${i}(base) { const inner = (x) => x + base + ${i}; return inner(10); }`,
    right: `function outerB_${i}(root) { const sub = (delta) => delta + root + ${i}; return sub(10); }`
  });
}

// Category E: Let vs Var vs Const and Destructuring (20 pairs)
for (let i = 0; i < 20; i++) {
  equivalentPairs.push({
    category: 'Declaration & Destructuring Equivalence',
    left: `function destA_${i}(pair) { let [a, b] = pair; return (a * ${i}) + b; }`,
    right: `function destB_${i}(tuple) { const [x, y] = tuple; return (x * ${i}) + y; }`
  });
}

assert.equal(equivalentPairs.length, 100, 'Must have exactly 100 equivalent test pairs');

for (let i = 0; i < equivalentPairs.length; i++) {
  const { category, left, right } = equivalentPairs[i];
  const hL = hashJsFunctionSource(left).hash;
  const hR = hashJsFunctionSource(right).hash;

  if (hL === hR) {
    equivPassed++;
  } else {
    equivFailed++;
    console.log(`  ❌ Equiv Pair #${i + 1} [${category}] MISMATCH:`);
    console.log(`     Left:  ${hL} -> ${left}`);
    console.log(`     Right: ${hR} -> ${right}`);
  }
}

console.log(`  -> Equivalent Pairs Result: ${equivPassed}/100 PASSED\n`);

// ---------------------------------------------------------------------------------
// 2. 100 NON-EQUIVALENT PAIRS (H_left != H_right)
// ---------------------------------------------------------------------------------
console.log('▶ [PHASE 2: 100 NON-EQUIVALENT PAIRS VERIFICATION]');

const nonEquivalentPairs = [];

// Category 1: Evaluation Order Preservation (a + b vs b + a, a / b vs b / a) (15 pairs)
for (let i = 0; i < 15; i++) {
  const op = ['+', '-', '*', '/', '%'][i % 5];
  nonEquivalentPairs.push({
    category: 'Evaluation Order Preservation',
    left: `function ordA_${i}(a, b) { return a ${op} b; }`,
    right: `function ordB_${i}(a, b) { return b ${op} a; }`
  });
}

// Category 2: Prefix vs Postfix Updates (x++ vs ++x, x-- vs --x) (15 pairs)
for (let i = 0; i < 15; i++) {
  const op = i % 2 === 0 ? '++' : '--';
  nonEquivalentPairs.push({
    category: 'Prefix vs Postfix Semantics',
    left: `function updA_${i}(x) { return x${op}; }`,
    right: `function updB_${i}(x) { return ${op}x; }`
  });
}

// Category 3: Side Effect vs Pure (console.log, IO vs Pure) (15 pairs)
for (let i = 0; i < 15; i++) {
  nonEquivalentPairs.push({
    category: 'Effect & Purity Signature',
    left: `function effectA_${i}(x) { return x + ${i}; }`,
    right: `function effectB_${i}(x) { console.log(x); return x + ${i}; }`
  });
}

// Category 4: Distinct Literal Types (string "10" vs number 10, null vs false vs 0) (15 pairs)
const litPairs = [
  ['"10"', '10'], ['"true"', 'true'], ['null', 'false'], ['null', '0'],
  ['false', '0'], ['""', '0'], ['"undefined"', 'null'], ['1', 'true'],
  ['"0"', '0'], ['-0', '0'], ['100', '"100"'], ['false', '""'],
  ['null', 'undefined'], ['true', '"1"'], ['10', '10.5']
];
for (let i = 0; i < 15; i++) {
  const [vL, vR] = litPairs[i];
  nonEquivalentPairs.push({
    category: 'Literal Type Distinction',
    left: `function litA_${i}() { return ${vL}; }`,
    right: `function litB_${i}() { return ${vR}; }`
  });
}

// Category 5: Distinct Comparison & Arithmetic Operators (15 pairs)
const opPairs = [
  ['<', '<='], ['>', '>='], ['===', '!=='], ['==', '!='],
  ['+', '-'], ['*', '/'], ['&&', '||'], ['&', '|'],
  ['<<', '>>'], ['>>>', '>>'], ['<', '>'], ['<=', '>='],
  ['+', '*'], ['-', '%'], ['^', '&']
];
for (let i = 0; i < 15; i++) {
  const [opL, opR] = opPairs[i];
  nonEquivalentPairs.push({
    category: 'Operator Distinction',
    left: `function opA_${i}(a, b) { return a ${opL} b; }`,
    right: `function opB_${i}(a, b) { return a ${opR} b; }`
  });
}

// Category 6: Host Capability Boundary vs Local Function (15 pairs)
const hostFns = ['Math.floor', 'Math.ceil', 'Math.abs', 'Math.round', 'Date.now'];
for (let i = 0; i < 15; i++) {
  const host = hostFns[i % hostFns.length];
  const local = host.split('.')[1] || 'localFn';
  nonEquivalentPairs.push({
    category: 'Host Capability Boundary',
    left: `function capA_${i}(x) { return ${host}(x); }`,
    right: `function capB_${i}(x) { return ${local}(x); }`
  });
}

// Category 7: Distinct Parameter Arity or Positions in Call Sites (10 pairs)
for (let i = 0; i < 10; i++) {
  nonEquivalentPairs.push({
    category: 'Call Argument Order / Arity',
    left: `function callA_${i}(a, b) { return customFn(a, b, ${i}); }`,
    right: `function callB_${i}(a, b) { return customFn(b, a, ${i}); }`
  });
}

assert.equal(nonEquivalentPairs.length, 100, 'Must have exactly 100 non-equivalent test pairs');

for (let i = 0; i < nonEquivalentPairs.length; i++) {
  const { category, left, right } = nonEquivalentPairs[i];
  const hL = hashJsFunctionSource(left).hash;
  const hR = hashJsFunctionSource(right).hash;

  if (hL !== hR) {
    nonEquivPassed++;
  } else {
    nonEquivFailed++;
    console.log(`  ❌ Non-Equiv Pair #${i + 1} [${category}] COLLISION (Should be distinct):`);
    console.log(`     Left:  ${hL} -> ${left}`);
    console.log(`     Right: ${hR} -> ${right}`);
  }
}

console.log(`  -> Non-Equivalent Pairs Result: ${nonEquivPassed}/100 PASSED\n`);

// ---------------------------------------------------------------------------------
// SUMMARY
// ---------------------------------------------------------------------------------
console.log('================================================================================');
console.log(`   CANONICAL HASHER ISOLATION SUMMARY:                                          `);
console.log(`   - 100 Equivalent Pairs:     ${equivPassed}/100 PASSED (${equivPassed}%)     `);
console.log(`   - 100 Non-Equivalent Pairs: ${nonEquivPassed}/100 PASSED (${nonEquivPassed}%) `);
console.log(`   - TOTAL GATE SCORE:         ${equivPassed + nonEquivPassed}/200 PASSED (${((equivPassed + nonEquivPassed)/2).toFixed(1)}%) `);
console.log('================================================================================\n');

if (equivPassed === 100 && nonEquivPassed === 100) {
  console.log('🎉 CANONICAL HASHER ISOLATION GATE: 100% VERIFIED AND PASS!\n');
  process.exit(0);
} else {
  console.log('❌ CANONICAL HASHER ISOLATION GATE FAILED!\n');
  process.exit(1);
}
