// GATE IN-MEMORY-4: Comprehensive Empirical Benchmark
// 1. Adversarial AST Capability Enforcement
// 2. True Semantic HashCons Structural Sharing & Microsecond Lookups
// 3. 4-Pathway Deconstruction Matrix (Python vs LIN-Disk vs LIN-RAM vs LIN-HashCons)

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { parseLia, transpileLinBodyToJs } from '../../../src/compiler.mjs';
import { AstCapabilityChecker } from '../runtime/ast_capability_checker.mjs';
import { SemanticHashCons } from '../runtime/semantic_hashcons.mjs';
import { runAdversarialEffectSuite } from './adversarial_effect_suite.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

export async function runGateInMemory4() {
  console.log("================================================================================");
  console.log("   GATE IN-MEMORY-4 : REPLICABLE MULTI-PATHWAY EMPIRICAL SUITE                 ");
  console.log("================================================================================");

  // ----------------------------------------------------------------------------
  // SECTION 1: Adversarial AST Capability Enforcement
  // ----------------------------------------------------------------------------
  const adversarialReport = runAdversarialEffectSuite();

  // ----------------------------------------------------------------------------
  // SECTION 2: True Semantic HashCons Structural Sharing & Microsecond Telemetry
  // ----------------------------------------------------------------------------
  console.log("\n================================================================================");
  console.log("   SEMANTIC HASHCONS STRUCTURAL SHARING & CANONICAL POINTER IDENTITY           ");
  console.log("================================================================================");

  const hashcons = new SemanticHashCons();

  // Module Alpha and Module Beta define the exact same AST logic
  const fnLogic = {
    kind: "FUNCTION",
    name: "computeChecksum",
    params: ["data"],
    effect: "Pure",
    contracts: ["data !== undefined"],
    body: "let h=0; for (let i=0;i<data.length;i++){h=((h<<5)-h)+data.charCodeAt(i);h|=0;} return h;"
  };

  const nodeAlpha = hashcons.internNode("mod_alpha", fnLogic);
  const nodeBeta = hashcons.internNode("mod_beta", fnLogic);

  const isHashIdentical = nodeAlpha.hash === nodeBeta.hash;
  const isPointerIdentical = nodeAlpha === nodeBeta;

  console.log(`[+] Cross-Module Canonicalization Test:`);
  console.log(`    - Module Alpha SHA256: ${nodeAlpha.hash}`);
  console.log(`    - Module Beta  SHA256: ${nodeBeta.hash}`);
  console.log(`    - Hash Identity Match: ${isHashIdentical ? "YES" : "NO"}`);
  console.log(`    - Canonical Pointer Identity (nodeAlpha === nodeBeta): ${isPointerIdentical ? "YES (Shared Resident Memory Instance)" : "NO"}`);

  // Measure HashCons Interning & Resolution Latencies (50,000 queries)
  const TOTAL_QUERIES = 50000;
  const symResolutionTimesNs = [];
  const nodeExecutionTimesNs = [];

  for (let i = 0; i < TOTAL_QUERIES; i++) {
    const t0 = process.hrtime.bigint();
    const resolved = hashcons.resolveSymbol("mod_alpha", "computeChecksum");
    const t1 = process.hrtime.bigint();
    symResolutionTimesNs.push(Number(t1 - t0));

    const tX0 = process.hrtime.bigint();
    hashcons.executeCanonicalNode(resolved, "https://github.com/lin");
    const tX1 = process.hrtime.bigint();
    nodeExecutionTimesNs.push(Number(tX1 - tX0));
  }

  symResolutionTimesNs.sort((a, b) => a - b);
  const p50_us = Number((symResolutionTimesNs[Math.floor(TOTAL_QUERIES * 0.50)] / 1000).toFixed(3));
  const p95_us = Number((symResolutionTimesNs[Math.floor(TOTAL_QUERIES * 0.95)] / 1000).toFixed(3));
  const p99_us = Number((symResolutionTimesNs[Math.floor(TOTAL_QUERIES * 0.99)] / 1000).toFixed(3));
  const avg_us = Number((symResolutionTimesNs.reduce((a, b) => a + b, 0) / TOTAL_QUERIES / 1000).toFixed(3));
  const exec_avg_us = Number((nodeExecutionTimesNs.reduce((a, b) => a + b, 0) / TOTAL_QUERIES / 1000).toFixed(3));

  console.log(`\n[+] HashCons Resolution Telemetry (${TOTAL_QUERIES.toLocaleString()} lookups):`);
  console.log(`    - Symbol Resolution p50: ${p50_us} µs`);
  console.log(`    - Symbol Resolution p95: ${p95_us} µs`);
  console.log(`    - Symbol Resolution p99: ${p99_us} µs`);
  console.log(`    - Symbol Resolution Avg: ${avg_us} µs`);
  console.log(`    - Canonical Node Execution Avg: ${exec_avg_us} µs`);

  // ----------------------------------------------------------------------------
  // SECTION 3: 4-Pathway Deconstruction Microbenchmark
  // ----------------------------------------------------------------------------
  console.log("\n================================================================================");
  console.log("   4-PATHWAY DECONSTRUCTION (PYTHON vs DISK vs RAM vs HASHCONS)                ");
  console.log("================================================================================");

  const sampleLin = `
@LIN:L1c:1.0
~effects{pure}
!isDomainAllowed(url, allowed, prohibited){
  ?(!url){^false}
  #(i=0;i<prohibited.length;i++){?(url.indexOf(prohibited[i])>=0){^false}}
  #(j=0;j<allowed.length;j++){?(url.indexOf(allowed[j])>=0){^true}}
  ^true
}
`;

  const samplePy = `
def is_domain_allowed(url, allowed, prohibited):
    if not url:
        return False
    for p in prohibited:
        if p in url:
            return False
    for a in allowed:
        if a in url:
            return True
    return True

if __name__ == '__main__':
    is_domain_allowed("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"])
`;

  const pyPath = path.join(ROOT, 'harness', 'temp_bench.py');
  fs.writeFileSync(pyPath, samplePy, 'utf8');

  // Pathway A: Python Subprocess
  const pyTimes = [];
  for (let r = 0; r < 5; r++) {
    const t0 = performance.now();
    execSync(`python3 ${pyPath}`, { timeout: 3000 });
    pyTimes.push(performance.now() - t0);
  }
  const pyColdMs = Number((pyTimes.reduce((a, b) => a + b, 0) / pyTimes.length).toFixed(2));

  // Pathway B: LIN Disk File
  const diskTimes = [];
  const diskTmpPath = path.join(ROOT, 'harness', 'temp_disk_mod.mjs');
  const REPS = 50;

  for (let r = 0; r < REPS; r++) {
    const t0 = performance.now();
    const parsed = parseLia(sampleLin);
    let js = '';
    for (const fn of parsed.fns) {
      js += `export function ${fn.name}(${fn.params.join(', ')}) { ${transpileLinBodyToJs(fn.body)} }\n`;
    }
    fs.writeFileSync(diskTmpPath, js, 'utf8');
    const mod = await import(`file://${diskTmpPath}?t=${Date.now() + r}`);
    mod.isDomainAllowed("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
    diskTimes.push(performance.now() - t0);
  }
  const linDiskMs = Number((diskTimes.reduce((a, b) => a + b, 0) / diskTimes.length).toFixed(3));

  // Pathway C: LIN In-Memory (Data URL)
  const ramTimes = [];
  for (let r = 0; r < REPS; r++) {
    const t0 = performance.now();
    const parsed = parseLia(sampleLin);
    AstCapabilityChecker.auditModule(parsed);
    let js = '';
    for (const fn of parsed.fns) {
      js += `export function ${fn.name}(${fn.params.join(', ')}) { ${transpileLinBodyToJs(fn.body)} }\n`;
    }
    const b64 = Buffer.from(js, 'utf8').toString('base64');
    const dynamicMod = await import(`data:text/javascript;base64,${b64}`);
    dynamicMod.isDomainAllowed("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
    ramTimes.push(performance.now() - t0);
  }
  const linRamMs = Number((ramTimes.reduce((a, b) => a + b, 0) / ramTimes.length).toFixed(3));

  // Pathway D: LIN Semantic HashCons
  const parsedForHashCons = parseLia(sampleLin);
  for (const fn of parsedForHashCons.fns) {
    hashcons.internNode("bench_mod", {
      name: fn.name,
      params: fn.params,
      effect: "Pure",
      body: transpileLinBodyToJs(fn.body)
    });
  }

  const hashConsTimes = [];
  for (let r = 0; r < REPS; r++) {
    const t0 = performance.now();
    const node = hashcons.resolveSymbol("bench_mod", "isDomainAllowed");
    hashcons.executeCanonicalNode(node, "https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
    hashConsTimes.push(performance.now() - t0);
  }
  const linHashConsMs = Number((hashConsTimes.reduce((a, b) => a + b, 0) / hashConsTimes.length).toFixed(4));

  console.log("--------------------------------------------------------------------------------");
  console.log("PATHWAY".padEnd(32), "TIME".padEnd(16), "SPEEDUP VS PYTHON");
  console.log("--------------------------------------------------------------------------------");
  console.log("Path A: Python Subprocess".padEnd(32), (pyColdMs + " ms").padEnd(16), "1.00x (Baseline)");
  console.log("Path B: LIN -> JS Disk File".padEnd(32), (linDiskMs + " ms").padEnd(16), (pyColdMs / linDiskMs).toFixed(1) + "x faster");
  console.log("Path C: LIN -> JS In-Memory (data:)".padEnd(32), (linRamMs + " ms").padEnd(16), (pyColdMs / linRamMs).toFixed(1) + "x faster");
  console.log("Path D: LIN -> Semantic HashCons".padEnd(32), (linHashConsMs + " ms (" + (linHashConsMs * 1000).toFixed(1) + " µs)").padEnd(16), (pyColdMs / linHashConsMs).toFixed(0) + "x faster");
  console.log("--------------------------------------------------------------------------------");

  try { fs.unlinkSync(pyPath); } catch(e) {}
  try { fs.unlinkSync(diskTmpPath); } catch(e) {}

  const finalReport = {
    gate: "GATE_IN_MEMORY_4",
    adversarial_capability_enforcement: adversarialReport,
    semantic_hashcons_verification: {
      hash_identity_match: isHashIdentical,
      canonical_pointer_identity: isPointerIdentical,
      telemetry: {
        total_queries: TOTAL_QUERIES,
        p50_us,
        p95_us,
        p99_us,
        avg_us,
        execution_avg_us: exec_avg_us
      }
    },
    pathway_comparison: {
      path_a_python_cold_ms: pyColdMs,
      path_b_lin_disk_ms: linDiskMs,
      path_c_lin_in_memory_ms: linRamMs,
      path_d_lin_semantic_hashcons_ms: linHashConsMs,
      disk_elimination_speedup: Number((linDiskMs / linRamMs).toFixed(2))
    },
    timestamp: new Date().toISOString()
  };

  const reportPath = path.join(ROOT, 'results/GATE_IN_MEMORY_4_REPORT.json');
  fs.writeFileSync(reportPath, JSON.stringify(finalReport, null, 2));
  console.log(`\n[+] GATE IN-MEMORY-4 Complete! Final Report saved to: ${reportPath}`);
  console.log("================================================================================");
  return finalReport;
}

runGateInMemory4();
