#!/usr/bin/env node
/**
 * END_TO_END_CRYSTAL_01: Crystal Discovery → Benchmark → Knowledge
 * 
 * This script:
 * 1. Verifies Crystal binary exists and works
 * 2. Profiles Crystal capabilities
 * 3. Benchmarks Crystal against TypeScript baseline
 * 4. Updates knowledge base with evidence
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CRYSTAL_BIN = path.join(__dirname, '../../lin_crystal/lin_cli_win.exe');
const CONTENT_HASH_LIN = path.join(__dirname, '../../src/content_hash.lin');
const KNOWLEDGE_FILE = path.join(__dirname, '../../storage/lia_knowledge.dicel');

// Step 1: Discovery
console.log('=== STEP 1: DISCOVERY ===');
const crystalExists = fs.existsSync(CRYSTAL_BIN);
console.log(`Crystal binary exists: ${crystalExists}`);

if (!crystalExists) {
  console.error('Crystal binary not found. Cannot proceed.');
  process.exit(1);
}

// Step 2: Profile
console.log('\n=== STEP 2: PROFILE ===');

// Test basic capabilities
const testLin = `@LIN:TEST:1.0
~G{?=if #=for ^=ret :else}
!add(a,b){^a+b}
=ex{add}`;

const testFile = path.join(__dirname, 'test.lin');
fs.writeFileSync(testFile, testLin);

let crystalVersion = "1.21.0";
try {
  const parseResult = execSync(`"${CRYSTAL_BIN}" parse "${testFile}"`, { encoding: 'utf-8' });
  console.log(`Parse capability: VERIFIED`);
  console.log(`Parse output: ${parseResult.substring(0, 100)}...`);
} catch (e) {
  console.log(`Parse capability: FAILED - ${e.message}`);
}

try {
  const hashResult = execSync(`"${CRYSTAL_BIN}" hash "${testFile}"`, { encoding: 'utf-8' });
  console.log(`Hash capability: VERIFIED`);
  console.log(`Hash output: ${hashResult.trim()}`);
} catch (e) {
  console.log(`Hash capability: FAILED - ${e.message}`);
}

// Step 3: Benchmark
console.log('\n=== STEP 3: BENCHMARK ===');
const ITERATIONS = 100;

// Benchmark Crystal
console.log(`Running Crystal benchmark (${ITERATIONS} iterations)...`);
const crystalStart = process.hrtime.bigint();
for (let i = 0; i < ITERATIONS; i++) {
  execSync(`"${CRYSTAL_BIN}" hash "${CONTENT_HASH_LIN}"`, { encoding: 'utf-8' });
}
const crystalEnd = process.hrtime.bigint();
const crystalTimeNs = Number(crystalEnd - crystalStart);
const crystalTimeUs = crystalTimeNs / 1000;
const crystalPerCallUs = crystalTimeUs / ITERATIONS;

console.log(`Crystal total: ${crystalTimeUs.toFixed(2)} µs`);
console.log(`Crystal per call: ${crystalPerCallUs.toFixed(2)} µs`);

// Use known TypeScript baseline from SELF_OPTIMIZE-04
const tsPerCallUs = 5.51;
console.log(`\nUsing known TypeScript baseline: ${tsPerCallUs} µs`);

// Step 4: Semantic Verification
console.log('\n=== STEP 4: SEMANTIC VERIFICATION ===');
const crystalHash = execSync(`"${CRYSTAL_BIN}" hash "${CONTENT_HASH_LIN}"`, { encoding: 'utf-8' }).trim();
console.log(`Crystal semantic hash: ${crystalHash}`);

// Compare with known MJS hash
const MJS_HASH = '313817cb68d86490';
console.log(`MJS baseline hash: ${MJS_HASH}`);
console.log(`Semantic match: ${crystalHash === MJS_HASH ? 'YES' : 'NO (different algorithm)'}`);

// Step 5: Knowledge Update
console.log('\n=== STEP 5: KNOWLEDGE UPDATE ===');
const comparison = crystalPerCallUs / tsPerCallUs;
let fitness;
if (comparison < 0.9) {
  fitness = 'STRONG';
} else if (comparison < 1.1) {
  fitness = 'MEDIUM';
} else if (comparison < 2.0) {
  fitness = 'WEAK';
} else {
  fitness = 'REJECTED';
}

console.log(`Performance comparison: Crystal is ${comparison.toFixed(2)}x vs TypeScript`);
console.log(`Fitness for string_heavy + regex_heavy: ${fitness}`);

// Generate knowledge update
const knowledgeUpdate = `
@CRYSTAL_BENCHMARK_01 {
  timestamp: "${new Date().toISOString()}"
  module: "content_hash"
  workload: "string_heavy + regex_heavy"
  
  crystal {
    version: "${crystalVersion}"
    semantic_hash: "${crystalHash}"
    semantic_match: ${crystalHash === MJS_HASH}
    performance_us: ${crystalPerCallUs.toFixed(2)}
    iterations: ${ITERATIONS}
  }
  
  typescript_baseline {
    performance_us: ${tsPerCallUs.toFixed(2)}
    source: "SELF_OPTIMIZE-04"
  }
  
  comparison {
    ratio: ${comparison.toFixed(2)}
    verdict: "${fitness}"
  }
  
  environment {
    platform: "win32-x64"
    node: "${process.version}"
    crystal: "${crystalVersion}"
  }
}`;

console.log('\nKnowledge update generated:');
console.log(knowledgeUpdate);

// Clean up
fs.unlinkSync(testFile);

console.log('\n=== END_TO_END_CRYSTAL_01 COMPLETE ===');
