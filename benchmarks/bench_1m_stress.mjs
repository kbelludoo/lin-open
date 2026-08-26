#!/usr/bin/env node
/**
 * 1 Million Lines Stress Benchmark for LIN & Polyglot Multi-Target Engine.
 * Tests:
 * - Parsing & compilation of 1,000,000 lines equivalent
 * - Memory footprint (Heap Used / Total)
 * - Compilation throughput (lines/sec & MB/sec)
 * - Token density vs Raw Source
 */
import { compileLia } from '../src/multi_emit.mjs';

console.log('================ 1 MILLION LINES LIN BENCHMARK ================');

const TARGET_LINES = 1_000_000;
const LINES_PER_FN = 10;
const TOTAL_FNS = TARGET_LINES / LINES_PER_FN;

console.log(`Gerando código sintético em LIN correspondente a ${TARGET_LINES.toLocaleString()} linhas (${TOTAL_FNS.toLocaleString()} funções)...`);

const tGen0 = process.hrtime.bigint();

// Build 1M lines equivalent LIN module
const chunks = [
  '@LIN:L1c:0.2',
  '^schema_once ^lossy=true ^ops=stress_1m',
  '~G{?=if #=for ^=ret :else}',
];

for (let i = 0; i < TOTAL_FNS; i++) {
  chunks.push(`!calc_${i}(x,y){a=x+${i};b=y*2;?(a>b){^a-b}:else{^b-a}}`);
}

const linCode = chunks.join('\n');
const tGen1 = process.hrtime.bigint();
const genDurationMs = Number(tGen1 - tGen0) / 1_000_000;

const linBytes = Buffer.byteLength(linCode, 'utf8');
const linMb = (linBytes / (1024 * 1024)).toFixed(2);
const estTokens = Math.ceil(linCode.length / 4);

console.log(`LIN gerado em ${genDurationMs.toFixed(1)} ms | Tamanho: ${linMb} MB (${linBytes.toLocaleString()} bytes) | ~${estTokens.toLocaleString()} tokens\n`);

const testTargets = ['js', 'ts', 'c', 'rust', 'lua', 'julia'];

console.log('| Target | Compilação (s) | Vazão (linhas/s) | Vazão (MB/s) | Memória Heap (MB) | Status |');
console.log('|--------|----------------|------------------|--------------|-------------------|--------|');

for (const target of testTargets) {
  if (global.gc) global.gc();
  const memBefore = process.memoryUsage().heapUsed;
  const t0 = process.hrtime.bigint();

  let status = 'PASS';
  let emittedCode = '';
  try {
    const res = compileLia(linCode, { target, stubRuntime: false });
    emittedCode = res.code || '';
  } catch (err) {
    status = 'FAIL';
  }

  const t1 = process.hrtime.bigint();
  const memAfter = process.memoryUsage().heapUsed;
  const durSec = Number(t1 - t0) / 1_000_000_000;
  const linesPerSec = Math.round(TARGET_LINES / durSec);
  const mbPerSec = (Number(linMb) / durSec).toFixed(1);
  const heapDiffMb = ((memAfter - memBefore) / (1024 * 1024)).toFixed(1);

  console.log(
    `| ${target.padEnd(6)} | ${durSec.toFixed(3).padStart(14)} | ${linesPerSec.toLocaleString().padStart(16)} | ${(mbPerSec + ' MB/s').padStart(12)} | ${(heapDiffMb + ' MB').padStart(17)} | ${status.padEnd(6)} |`
  );
}

console.log('================================================================');
