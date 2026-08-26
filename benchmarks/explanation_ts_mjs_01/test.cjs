#!/usr/bin/env node
// EXPLANATION_TS_MJS_V1: Causal Attribution Test
// Decomposes content_hash workload to isolate TS vs MJS performance difference

const crypto = require('crypto');

// Test parameters
const ITERATIONS = 10000;
const WARMUP = 1000;

// Input data
const FN_NAME = 'add';
const PARAMS = 'a,b';
const BODY = '^a+b';
const EXPECTED_CANONICAL = '(2)^$0+$1';
const EXPECTED_HASH = '8e590c4638786070';

// Helper: measure average time per call
function benchmark(fn, iterations = ITERATIONS, warmup = WARMUP) {
  // Warmup
  for (let i = 0; i < warmup; i++) fn();
  
  // Measure
  const start = process.hrtime.bigint();
  for (let i = 0; i < iterations; i++) fn();
  const end = process.hrtime.bigint();
  
  const totalNs = Number(end - start);
  const avgUs = (totalNs / iterations) / 1000;
  return avgUs;
}

// Component 1: String creation and manipulation
function testStringCreation() {
  let canon = BODY.trim();
  canon = canon.replace(/\s+/g, ' ');
  return canon;
}

// Component 2: Regex execution
function testRegexExecution() {
  const paramList = PARAMS.split(',');
  const clean = [];
  for (let i = 0; i < paramList.length; i++) {
    const p = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  
  let canon = EXPECTED_CANONICAL;
  for (let j = 0; j < clean.length; j++) {
    const re = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  return canon;
}

// Component 3: Serialization (string replacement)
function testSerialization() {
  let canon = EXPECTED_CANONICAL;
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  return '(' + 2 + ')' + canon;
}

// Component 4: Buffer conversion
function testBufferConversion() {
  const canonical = EXPECTED_CANONICAL;
  const buffer = Buffer.from(canonical, 'utf8');
  return buffer;
}

// Component 5: Crypto call
function testCryptoCall() {
  const canonical = EXPECTED_CANONICAL;
  const hash = crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

// Component 6: Full pipeline (combined)
function testFullPipeline() {
  // String creation
  let canon = BODY.trim();
  canon = canon.replace(/\s+/g, ' ');
  
  // Regex execution
  const paramList = PARAMS.split(',');
  const clean = [];
  for (let i = 0; i < paramList.length; i++) {
    const p = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  
  for (let j = 0; j < clean.length; j++) {
    const re = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  
  // Serialization
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  const canonical = '(' + clean.length + ')' + canon;
  
  // Buffer conversion + Crypto call
  const hash = crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

// Run tests
console.log('=== EXPLANATION_TS_MJS_V1: CAUSAL ATTRIBUTION ===');
console.log(`Iterations: ${ITERATIONS}, Warmup: ${WARMUP}`);
console.log('');

const components = [
  { name: 'String creation', fn: testStringCreation },
  { name: 'Regex execution', fn: testRegexExecution },
  { name: 'Serialization', fn: testSerialization },
  { name: 'Buffer conversion', fn: testBufferConversion },
  { name: 'Crypto call', fn: testCryptoCall },
  { name: 'Full pipeline', fn: testFullPipeline },
];

const results = [];

for (const { name, fn } of components) {
  const avgUs = benchmark(fn);
  results.push({ name, avgUs });
  console.log(`${name}: ${avgUs.toFixed(2)} µs/call`);
}

// Find the dominant component
const fullPipeline = results.find(r => r.name === 'Full pipeline').avgUs;
const cryptoCall = results.find(r => r.name === 'Crypto call').avgUs;
const bufferConversion = results.find(r => r.name === 'Buffer conversion').avgUs;

console.log('');
console.log('=== CAUSAL ATTRIBUTION ===');
console.log(`Full pipeline: ${fullPipeline.toFixed(2)} µs`);
console.log(`Crypto call alone: ${cryptoCall.toFixed(2)} µs`);
console.log(`Buffer conversion alone: ${bufferConversion.toFixed(2)} µs`);
console.log('');

// Check if crypto dominates
if (cryptoCall > fullPipeline * 0.5) {
  console.log('DOMINANT_FACTOR: crypto_call');
} else if (bufferConversion > fullPipeline * 0.3) {
  console.log('DOMINANT_FACTOR: buffer_conversion');
} else {
  // Sum of non-crypto components
  const sumNonCrypto = results
    .filter(r => r.name !== 'Crypto call' && r.name !== 'Full pipeline')
    .reduce((sum, r) => sum + r.avgUs, 0);
  
  if (sumNonCrypto > fullPipeline * 0.5) {
    console.log('DOMINANT_FACTOR: string_processing');
  } else {
    console.log('DOMINANT_FACTOR: distributed');
  }
}

// Verify correctness
const result = testFullPipeline();
console.log('');
console.log(`Correctness: ${result === EXPECTED_HASH ? 'PASS' : 'FAIL'}`);
console.log(`Expected: ${EXPECTED_HASH}`);
console.log(`Got: ${result}`);
