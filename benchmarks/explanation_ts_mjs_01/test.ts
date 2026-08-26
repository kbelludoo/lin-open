#!/usr/bin/env node
import { createHash } from 'crypto';

const ITERATIONS = 10000;
const WARMUP = 1000;

const FN_NAME: string = 'add';
const PARAMS: string = 'a,b';
const BODY: string = '^a+b';
const EXPECTED_CANONICAL: string = '(2)^$0+$1';
const EXPECTED_HASH: string = '8e590c4638786070';

function benchmark(fn: () => unknown, iterations: number = ITERATIONS, warmup: number = WARMUP): number {
  for (let i = 0; i < warmup; i++) fn();
  const start: bigint = process.hrtime.bigint();
  for (let i = 0; i < iterations; i++) fn();
  const end: bigint = process.hrtime.bigint();
  const totalNs: number = Number(end - start);
  const avgUs: number = (totalNs / iterations) / 1000;
  return avgUs;
}

function testStringCreation(): string {
  let canon: string = BODY.trim();
  canon = canon.replace(/\s+/g, ' ');
  return canon;
}

function testRegexExecution(): string {
  const paramList: string[] = PARAMS.split(',');
  const clean: string[] = [];
  for (let i = 0; i < paramList.length; i++) {
    const p: string = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  let canon: string = EXPECTED_CANONICAL;
  for (let j = 0; j < clean.length; j++) {
    const re: RegExp = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  return canon;
}

function testSerialization(): string {
  let canon: string = EXPECTED_CANONICAL;
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  return '(' + 2 + ')' + canon;
}

function testBufferConversion(): Buffer {
  const canonical: string = EXPECTED_CANONICAL;
  const buffer: Buffer = Buffer.from(canonical, 'utf8');
  return buffer;
}

function testCryptoCall(): string {
  const canonical: string = EXPECTED_CANONICAL;
  const hash: string = createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

function testFullPipeline(): string {
  let canon: string = BODY.trim();
  canon = canon.replace(/\s+/g, ' ');
  const paramList: string[] = PARAMS.split(',');
  const clean: string[] = [];
  for (let i = 0; i < paramList.length; i++) {
    const p: string = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  for (let j = 0; j < clean.length; j++) {
    const re: RegExp = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  const canonical: string = '(' + clean.length + ')' + canon;
  const hash: string = createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

console.log('=== EXPLANATION_TS_MJS_V1: TYPESCRIPT VARIANT ===');
console.log(`Iterations: ${ITERATIONS}, Warmup: ${WARMUP}`);
console.log('');

const components: Array<{ name: string; fn: () => unknown }> = [
  { name: 'String creation', fn: testStringCreation },
  { name: 'Regex execution', fn: testRegexExecution },
  { name: 'Serialization', fn: testSerialization },
  { name: 'Buffer conversion', fn: testBufferConversion },
  { name: 'Crypto call', fn: testCryptoCall },
  { name: 'Full pipeline', fn: testFullPipeline },
];

const results: Array<{ name: string; avgUs: number }> = [];

for (const { name, fn } of components) {
  const avgUs: number = benchmark(fn);
  results.push({ name, avgUs });
  console.log(`${name}: ${avgUs.toFixed(2)} µs/call`);
}

const fullPipeline: number = results.find(r => r.name === 'Full pipeline')!.avgUs;
const cryptoCall: number = results.find(r => r.name === 'Crypto call')!.avgUs;

console.log('');
console.log('=== CAUSAL ATTRIBUTION ===');
console.log(`Full pipeline: ${fullPipeline.toFixed(2)} µs`);
console.log(`Crypto call alone: ${cryptoCall.toFixed(2)} µs`);

const result: string = testFullPipeline();
console.log('');
console.log(`Correctness: ${result === EXPECTED_HASH ? 'PASS' : 'FAIL'}`);
console.log(`Expected: ${EXPECTED_HASH}`);
console.log(`Got: ${result}`);
