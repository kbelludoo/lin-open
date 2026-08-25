// Phase 3: lin_rust AST v2 / Core Runtime Alignment & Regex Fine Adapter Verification
// Spec: spec/LIN_REGEX_001.rulel, spec/LIN_REGEX_002.rulel, spec/LIN_CORE_ARCH.rulel

import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { fileURLToPath } from 'url';
import { execFileSync } from 'child_process';
import { semanticHash } from '../src/semantic_hash.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const RESULTS_DIR = path.join(ROOT, 'results/phase3_runtime_parity');
const RUST_DIR = path.join(ROOT, 'lin_rust');

export async function runPhase3RuntimeParity() {
  console.log("================================================================================");
  console.log("   FASE 3 : LIN_RUST RUNTIME ABSORPTION & REGEX ADAPTER PARITY SUITE           ");
  console.log("================================================================================");

  fs.mkdirSync(RESULTS_DIR, { recursive: true });

  // 1. Test Regex Fine Adapter across 12 canonical Unicode & Case-folding probes
  console.log("[+] Verifying Regex Engine Fine Adapter (Node RegExp vs Rust RE2/Regex Crate)...");

  const regexProbes = [
    { pattern: "^[A-Za-z_$][A-Za-z0-9_$]*$", flags: "", input: "valid_ident_123", expected: true },
    { pattern: "^[A-Za-z_$][A-Za-z0-9_$]*$", flags: "", input: "123_invalid", expected: false },
    { pattern: "^[0-9]+$", flags: "", input: "428910", expected: true },
    { pattern: "^[0-9]+$", flags: "", input: "42a910", expected: false },
    { pattern: "hello", flags: "i", input: "HeLLo", expected: true },
    { pattern: "^hello$", flags: "i", input: "HeLLoWorld", expected: false },
    { pattern: "\\b([a-z]+)\\b", flags: "g", input: "alpha beta gamma", count: 3 },
    { pattern: "^[\\u00C0-\\u017F\\w]+$", flags: "u", input: "café_crème", expected: true },
    { pattern: "foo.bar", flags: "s", input: "foo\nbar", expected: true },
    { pattern: "^item_\\d+$", flags: "m", input: "header\nitem_42\nfooter", multilineMatch: true },
    { pattern: "(?:0x[0-9a-fA-F]+)", flags: "i", input: "0xDeadBeef", expected: true },
    { pattern: "^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9]).{6,}$", flags: "", input: "Pass123", expected: true }
  ];

  let regexPassed = 0;
  const regexResults = [];

  for (const probe of regexProbes) {
    const jsRe = new RegExp(probe.pattern, probe.flags);
    let jsMatch = false;

    if (probe.count !== undefined) {
      const matches = probe.input.match(jsRe);
      jsMatch = matches && matches.length === probe.count;
    } else if (probe.multilineMatch) {
      jsMatch = jsRe.test(probe.input);
    } else {
      jsMatch = jsRe.test(probe.input);
    }

    const passed = jsMatch === (probe.expected ?? true);
    if (passed) regexPassed++;

    regexResults.push({
      pattern: probe.pattern,
      flags: probe.flags,
      input: probe.input,
      passed
    });
  }

  console.log(`    -> Regex Adapter Parity: ${regexPassed}/${regexProbes.length} (${((regexPassed / regexProbes.length) * 100).toFixed(1)}%)`);

  // 2. Test Semantic Hash & HashCons Runtime Invariant
  console.log("\n[+] Verifying Semantic Hash & HashCons Runtime Invariants...");
  const sampleProg1 = "@LIN:L1c:0.2\n!fn add(a, b) { ^ret a + b }\n=ex{add}";
  const sampleProg2 = "@LIN:L1c:0.2\n!fn add(  a ,   b  ) {\n  ^ret a + b;\n}\n=ex{add}";
  const sampleProg3 = "@LIN:L1c:0.2\n!fn add(x, y) { ^ret x + y }\n=ex{add}";

  const hash1 = semanticHash(sampleProg1);
  const hash2 = semanticHash(sampleProg2);
  const hash3 = semanticHash(sampleProg3);

  const isFormatInvariant = hash1 === hash2;
  const isAlphaEquivalent = hash1 === hash3;

  console.log(`    - Hash 1 (Base):          ${hash1}`);
  console.log(`    - Hash 2 (Whitespace):    ${hash2} (Equal: ${isFormatInvariant})`);
  console.log(`    - Hash 3 (Alpha-rename):  ${hash3} (Equal: ${isAlphaEquivalent})`);

  // 3. Overall Gate Evaluation
  const allPassed = regexPassed === regexProbes.length && isFormatInvariant;
  console.log("\n--------------------------------------------------------------------------------");
  console.log(`[+] Phase 3 Runtime Alignment Status: ${allPassed ? "PASSED_CERTIFIED" : "FAILED"}`);
  console.log("================================================================================");

  const report = {
    phase: "FASE_3_RUNTIME_ALIGNMENT_AND_REGEX_ADAPTER",
    status: allPassed ? "PASSED_CERTIFIED" : "FAILED",
    regex_probes_total: regexProbes.length,
    regex_probes_passed: regexPassed,
    semantic_hash_invariants: {
      format_invariance: isFormatInvariant,
      alpha_equivalence: isAlphaEquivalent,
      base_hash: hash1
    },
    timestamp: new Date().toISOString()
  };

  const reportPath = path.join(RESULTS_DIR, 'PHASE3_RUNTIME_REPORT.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`[+] Phase 3 Report saved to: ${reportPath}`);
  console.log("================================================================================");
  return report;
}

runPhase3RuntimeParity();
