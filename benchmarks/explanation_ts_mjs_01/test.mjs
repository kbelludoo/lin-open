// EXPLANATION_TS_MJS_V1: MJS variant for comparison
import { createHash } from 'crypto';

const ITERATIONS = 10000;
const WARMUP = 1000;

const FN_NAME = 'add';
const PARAMS = 'a,b';
const BODY = '^a+b';
const EXPECTED_CANONICAL = '(2)^$0+$1';
const EXPECTED_HASH = '8e590c4638786070';

function benchmark(fn, iterations = ITERATIONS, warmup = WARMUP) {
  for (let i = 0; i < warmup; i++) fn();
  const start = process.hrtime.bigint();
  for (let i = 0; i < iterations; i++) fn();
  const end = process.hrtime.bigint();
  const totalNs = Number(end - start);
  const avgUs = (totalNs / iterations) / 1000;
  return avgUs;
}

function testStringCreation() {
  let canon = BODY.trim();
  canon = canon.replace(/\s+/g, ' ');
  return canon;
}

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

function testSerialization() {
  let canon = EXPECTED_CANONICAL;
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  return '(' + 2 + ')' + canon;
}

function testBufferConversion() {
  const canonical = EXPECTED_CANONICAL;
  const buffer = Buffer.from(canonical, 'utf8');
  return buffer;
}

function testCryptoCall() {
  const canonical = EXPECTED_CANONICAL;
  const hash = createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

function testFullPipeline() {
  let canon = BODY.trim();
  canon = canon.replace(/\s+/g, ' ');
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
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  const canonical = '(' + clean.length + ')' + canon;
  const hash = createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

console.log('=== EXPLANATION_TS_MJS_V1: MJS VARIANT ===');
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

const fullPipeline = results.find(r => r.name === 'Full pipeline').avgUs;
const cryptoCall = results.find(r => r.name === 'Crypto call').avgUs;

console.log('');
console.log('=== CAUSAL ATTRIBUTION ===');
console.log(`Full pipeline: ${fullPipeline.toFixed(2)} µs`);
console.log(`Crypto call alone: ${cryptoCall.toFixed(2)} µs`);

const result = testFullPipeline();
console.log('');
console.log(`Correctness: ${result === EXPECTED_HASH ? 'PASS' : 'FAIL'}`);
console.log(`Expected: ${EXPECTED_HASH}`);
console.log(`Got: ${result}`);
