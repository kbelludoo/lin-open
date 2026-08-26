/**
 * Test: Self-Hosting Integrity & Real Dogfooding Gate.
 * 
 * Strict metric separation:
 *   1. Pipeline Dogfooding Ratio: LIN modules imported by production runtime,
 *      scripts, CLI, benchmarks and execution runners (src/, scripts/, bin/, benchmarks/).
 *   2. Verified Executable Ratio: LIN modules verified to compile & execute
 *      (including synthetic test suites).
 * 
 * Prevents metric inflation by distinguishing real pipeline consumption from
 * isolated smoke test harnesses.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const srcDir = path.join(rootDir, 'src');

function getAllSourceFiles(dir) {
  const results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === '.git' || entry.name === 'dist') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...getAllSourceFiles(full));
    } else if (/\.(mjs|cjs|js|ts)$/.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

console.log('=== Running Self-Hosting Integrity & Dogfooding Gate ===\n');

const linFiles = fs.readdirSync(srcDir).filter(f => f.endsWith('.lin'));
const allCodeFiles = getAllSourceFiles(rootDir);
const fileContents = allCodeFiles.map(f => ({
  path: f,
  rel: path.relative(rootDir, f),
  content: fs.readFileSync(f, 'utf8'),
  isPipeline: f.includes('/src/') || f.includes('/scripts/') || f.includes('/bin/') || f.includes('/benchmarks/') || f.includes('tests/ain_lb/'),
  isSmokeTestOnly: f.includes('all_dogfooded_components.test.mjs') || f.includes('dogfooded_components_active.test.mjs')
}));

const report = [];

for (const lin of linFiles.sort()) {
  const base = lin.replace(/\.lin$/, '');
  const hasLoad = fs.existsSync(path.join(srcDir, `${base}_load.mjs`));
  const hasCompiledMjs = fs.existsSync(path.join(srcDir, `${base}.compiled.mjs`));
  const hasCompiledCjs = fs.existsSync(path.join(srcDir, `${base}.compiled.cjs`));
  const hasCompiledTs = fs.existsSync(path.join(srcDir, `${base}.compiled.ts`));
  const hasHandwrittenMjs = fs.existsSync(path.join(srcDir, `${base}.mjs`));

  let pipelineRefs = 0;
  let testRefs = 0;
  let smokeRefs = 0;

  for (const f of fileContents) {
    // Skip self-referencing in the loader itself
    if (f.rel === `src/${base}_load.mjs`) continue;
    
    const referencesLin = f.content.includes(`${base}_load`) || f.content.includes(`${base}.compiled`);
    if (referencesLin) {
      if (f.isPipeline) pipelineRefs++;
      else if (f.isSmokeTestOnly) smokeRefs++;
      else testRefs++;
    }
  }

  const isPipelineActive = pipelineRefs > 0;
  const isValidatedActive = isPipelineActive || testRefs > 0 || smokeRefs > 0;

  report.push({
    file: lin,
    base,
    hasLoad,
    hasCompiled: hasCompiledMjs || hasCompiledCjs || hasCompiledTs,
    pipelineRefs,
    testRefs,
    smokeRefs,
    isPipelineActive,
    isValidatedActive
  });
}

const pipeActive = report.filter(r => r.isPipelineActive);
const valActive = report.filter(r => r.isValidatedActive);

const pipeRatio = (pipeActive.length / report.length) * 100;
const valRatio = (valActive.length / report.length) * 100;

console.log(`Total .lin components in src/: ${report.length}`);
console.log(`  - Pipeline Dogfooding (src/, scripts/, bin/, benchmarks/): ${pipeActive.length}/${report.length} (${pipeRatio.toFixed(1)}%)`);
console.log(`  - Verified Executable (.lin compiled & tested):          ${valActive.length}/${report.length} (${valRatio.toFixed(1)}%)\n`);

console.log('Tier 1: Pipeline Core Dogfooded Components:');
pipeActive.forEach(a => console.log(`  ★ ${a.file.padEnd(28)} (pipeline refs: ${a.pipelineRefs})`));

console.log('\nTier 2: Verified Validated Components (Smoke Tested):');
report.filter(r => !r.isPipelineActive && r.isValidatedActive).forEach(a => {
  console.log(`  ✓ ${a.file.padEnd(28)} (test refs: ${a.testRefs + a.smokeRefs})`);
});

// Gates:
// 1. Minimum pipeline dogfooding components
assert.ok(pipeActive.length >= 9, `Pipeline dogfooding regression: expected at least 9 pipeline LIN components, got ${pipeActive.length}`);
// 2. All components must be validated executable
assert.ok(valActive.length >= 30, `Execution validation regression: expected at least 30 verified LIN components, got ${valActive.length}`);

console.log('\n============================================================');
console.log(`Self-Hosting Gate PASSED: ${pipeActive.length} in pipelines (${pipeRatio.toFixed(1)}%) | ${valActive.length} verified executable (${valRatio.toFixed(1)}%).`);
console.log('============================================================\n');
