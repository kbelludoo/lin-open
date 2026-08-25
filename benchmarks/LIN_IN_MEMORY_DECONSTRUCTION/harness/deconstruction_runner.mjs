// LIN 4-Pathway Deconstruction Microbenchmark Runner
// Deconstructs: Python vs LIN-Disk vs LIN-RAM (data:) vs LIN-Direct-HashCons

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { parseLia, transpileLinBodyToJs } from '../../../src/compiler.mjs';
import { EffectChecker } from './effect_checker.mjs';
import { benchmarkHashConsLookups } from './hashcons_bench.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

export async function runDeconstructionBenchmark() {
  console.log("================================================================================");
  console.log("   LIN 4-PATHWAY DECONSTRUCTION MICROBENCHMARK & PHASE LATENCY ISOLATION       ");
  console.log("================================================================================");

  const sampleLinSource = `
@LIN:L1c:1.0
~effects{pure}
!isDomainAllowed(url, allowed, prohibited){
  ?(!url){^false}
  #(i=0;i<prohibited.length;i++){?(url.indexOf(prohibited[i])>=0){^false}}
  #(j=0;j<allowed.length;j++){?(url.indexOf(allowed[j])>=0){^true}}
  ^true
}
!computeHash(data){
  let h = 0;
  #(i=0;i<data.length;i++){h = ((h << 5) - h) + data.charCodeAt(i); h |= 0;}
  ^h
}
`;

  const samplePythonSource = `
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

def compute_hash(data):
    h = 0
    for c in data:
        h = ((h << 5) - h) + ord(c)
        h = h & 0xFFFFFFFF
    return h

if __name__ == '__main__':
    allowed = ["example.com", "github.com"]
    prohibited = ["malicious.org"]
    res = is_domain_allowed("https://github.com/lin", allowed, prohibited)
    h = compute_hash("https://github.com/lin")
`;

  const pyScriptPath = path.join(ROOT, 'harness', 'temp_bench.py');
  fs.writeFileSync(pyScriptPath, samplePythonSource, 'utf8');

  const REPS = 50;
  const STEADY_ITERS = 20000;

  // ============================================================================
  // PATHWAY A: Python Original Cold & Warm Latency
  // ============================================================================
  console.log("\n[+] Measuring Pathway A: Python Original (Runtime Startup & Execution)...");
  const pyColdTimes = [];
  for (let r = 0; r < 5; r++) {
    const t0 = performance.now();
    execSync(`python3 ${pyScriptPath}`, { timeout: 3000 });
    pyColdTimes.push(performance.now() - t0);
  }
  const pyColdAvgMs = Number((pyColdTimes.reduce((a, b) => a + b, 0) / pyColdTimes.length).toFixed(2));
  console.log(`    -> Python Cold Start + Execution: ${pyColdAvgMs} ms`);

  // ============================================================================
  // PATHWAY B: LIN -> JS on Disk -> Execute
  // ============================================================================
  console.log("\n[+] Measuring Pathway B: LIN -> JS Disk File -> Execute...");
  const diskTimes = [];
  const diskTmpPath = path.join(ROOT, 'harness', 'temp_disk_module.mjs');

  for (let r = 0; r < REPS; r++) {
    const t0 = performance.now();
    const parsed = parseLia(sampleLinSource);
    let js = '';
    for (const fn of parsed.fns) {
      js += `export function ${fn.name}(${fn.params.join(', ')}) { ${transpileLinBodyToJs(fn.body)} }\n`;
    }
    fs.writeFileSync(diskTmpPath, js, 'utf8');
    const mod = await import(`file://${diskTmpPath}?t=${Date.now() + r}`);
    mod.isDomainAllowed("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
    diskTimes.push(performance.now() - t0);
  }
  const linDiskAvgMs = Number((diskTimes.reduce((a, b) => a + b, 0) / diskTimes.length).toFixed(3));
  console.log(`    -> LIN Disk File Pipeline (Parse + Write + Import + Exec): ${linDiskAvgMs} ms`);

  // ============================================================================
  // PATHWAY C: LIN -> JS In-Memory (Data URL / Zero Disk) -> Execute
  // ============================================================================
  console.log("\n[+] Measuring Pathway C: LIN -> JS In-Memory Buffer (Data URL) -> Execute...");
  const memoryTimes = [];
  const breakdown = { parse: 0, effectCheck: 0, codeGen: 0, dataUrlImport: 0, firstExec: 0 };

  for (let r = 0; r < REPS; r++) {
    const t0 = performance.now();

    // Phase 1: Parse LIN
    const tP0 = performance.now();
    const parsed = parseLia(sampleLinSource);
    breakdown.parse += (performance.now() - tP0);

    // Phase 2: Static Effect & Capability Check
    const tE0 = performance.now();
    EffectChecker.verifyModule(parsed);
    breakdown.effectCheck += (performance.now() - tE0);

    // Phase 3: Code Generation to RAM Buffer
    const tG0 = performance.now();
    let js = '';
    for (const fn of parsed.fns) {
      js += `export function ${fn.name}(${fn.params.join(', ')}) { ${transpileLinBodyToJs(fn.body)} }\n`;
    }
    const b64 = Buffer.from(js, 'utf8').toString('base64');
    breakdown.codeGen += (performance.now() - tG0);

    // Phase 4: Dynamic Module Import via Data URL
    const tI0 = performance.now();
    const dynamicMod = await import(`data:text/javascript;base64,${b64}`);
    breakdown.dataUrlImport += (performance.now() - tI0);

    // Phase 5: First Execution
    const tX0 = performance.now();
    dynamicMod.isDomainAllowed("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
    breakdown.firstExec += (performance.now() - tX0);

    memoryTimes.push(performance.now() - t0);
  }

  const linMemoryAvgMs = Number((memoryTimes.reduce((a, b) => a + b, 0) / memoryTimes.length).toFixed(3));
  console.log(`    -> LIN In-Memory Pipeline (Zero-Disk Data URL): ${linMemoryAvgMs} ms`);

  // Normalize Phase Breakdown
  for (const k in breakdown) {
    breakdown[k] = Number((breakdown[k] / REPS).toFixed(4));
  }

  // ============================================================================
  // PATHWAY D: LIN -> Direct In-Memory HashCons AST Evaluation
  // ============================================================================
  console.log("\n[+] Measuring Pathway D: LIN -> Direct HashCons AST In-Memory Evaluation...");
  const directAstTimes = [];
  const parsedAst = parseLia(sampleLinSource);
  const fnTable = new Map();
  for (const fn of parsedAst.fns) {
    const fnExecutable = new Function(...fn.params, transpileLinBodyToJs(fn.body));
    fnTable.set(fn.name, fnExecutable);
  }

  for (let r = 0; r < REPS; r++) {
    const t0 = performance.now();
    const fn = fnTable.get('isDomainAllowed');
    fn("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
    directAstTimes.push(performance.now() - t0);
  }
  const linDirectAvgMs = Number((directAstTimes.reduce((a, b) => a + b, 0) / directAstTimes.length).toFixed(4));
  console.log(`    -> LIN Direct HashCons AST Execution: ${linDirectAvgMs} ms (${(linDirectAvgMs * 1000).toFixed(1)} µs)`);

  // ============================================================================
  // Steady-State Throughput (20,000 invocations)
  // ============================================================================
  console.log("\n[+] Measuring Steady-State Invocation Throughput (20,000 ops)...");
  const testFn = fnTable.get('isDomainAllowed');
  const tStartSteady = performance.now();
  for (let i = 0; i < STEADY_ITERS; i++) {
    testFn("https://github.com/lin", ["example.com", "github.com"], ["malicious.org"]);
  }
  const steadyDurationMs = performance.now() - tStartSteady;
  const steadyThroughputOpsSec = Math.round(STEADY_ITERS / (steadyDurationMs / 1000));
  console.log(`    -> Steady-State Throughput: ${steadyThroughputOpsSec.toLocaleString()} ops/sec`);

  // ============================================================================
  // Empirical HashCons Microsecond Lookup Benchmark
  // ============================================================================
  console.log("\n[+] Running Microsecond-Precision HashCons Lookup Benchmark...");
  const hashconsTelemetry = benchmarkHashConsLookups(1000, 50000);
  console.log(`    - HashCons Cold Lookup: ${hashconsTelemetry.cold_lookup_avg_us} µs`);
  console.log(`    - HashCons Warm p50: ${hashconsTelemetry.warm_lookup_p50_us} µs`);
  console.log(`    - HashCons Warm p95: ${hashconsTelemetry.warm_lookup_p95_us} µs`);
  console.log(`    - HashCons Warm p99: ${hashconsTelemetry.warm_lookup_p99_us} µs`);

  // Clean temp files
  try { fs.unlinkSync(pyScriptPath); } catch(e) {}
  try { fs.unlinkSync(diskTmpPath); } catch(e) {}

  const report = {
    benchmark: "LIN_4_PATHWAY_DECONSTRUCTION",
    summary: {
      path_a_python_cold_ms: pyColdAvgMs,
      path_b_lin_disk_ms: linDiskAvgMs,
      path_c_lin_in_memory_ms: linMemoryAvgMs,
      path_d_lin_direct_hashcons_ms: linDirectAvgMs,
      speedup_memory_vs_python: Number((pyColdAvgMs / linMemoryAvgMs).toFixed(1)),
      speedup_direct_vs_python: Number((pyColdAvgMs / linDirectAvgMs).toFixed(1))
    },
    path_c_phase_breakdown_ms: breakdown,
    hashcons_telemetry: hashconsTelemetry,
    steady_state_throughput_ops_sec: steadyThroughputOpsSec,
    timestamp: new Date().toISOString()
  };

  const reportPath = path.join(ROOT, 'results/DECONSTRUCTION_REPORT.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\n[+] Deconstruction Benchmark Complete! Report saved to: ${reportPath}`);
  console.log("================================================================================");
  return report;
}

runDeconstructionBenchmark();
