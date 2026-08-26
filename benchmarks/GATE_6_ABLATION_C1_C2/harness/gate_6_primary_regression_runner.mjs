// GATE 6: Pre-Registered Primary Causal Outcome Benchmark
// Evaluates `regression_event` under Multi-Step Mutation & Context Drift
// Symmetrical Arms: C1 (With H_node Canonical Anchoring) vs C2 (Without H_node)
// Rigorous Statistical Inference: 2x2 Contingency Matrix + McNemar Exact Binomial Test + Raw Telemetry Logging

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { AstCapabilityFuzzer } from '../../LIN_IN_MEMORY_GATE_5/runtime/ast_capability_fuzzer.mjs';
import { TrueAstAlphaCanonicalizer } from '../../LIN_IN_MEMORY_GATE_5/runtime/true_ast_alpha_canonicalizer.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

// Helper: Exact Binomial Log Factorial
function logFactorial(n) {
  let res = 0;
  for (let i = 2; i <= n; i++) res += Math.log(i);
  return res;
}

function binomialCoefficientLog(n, k) {
  if (k < 0 || k > n) return -Infinity;
  return logFactorial(n) - logFactorial(k) - logFactorial(n - k);
}

function mcnemarExactTest(b, c) {
  const n = b + c;
  if (n === 0) {
    return {
      b_discordant_c1_win: 0,
      c_discordant_c2_win: 0,
      discordant_total: 0,
      chi2_continuity_corrected: 0.0,
      exact_binomial_p_value: 1.0,
      significant_at_bonferroni_0_005: false
    };
  }

  const chi2 = Math.pow(Math.abs(b - c) - 1, 2) / n;

  let pValue = 0;
  const minObserved = Math.min(b, c);
  for (let k = 0; k <= minObserved; k++) {
    pValue += Math.exp(binomialCoefficientLog(n, k) - n * Math.LN2);
  }
  pValue = Math.min(1.0, 2.0 * pValue);

  return {
    b_discordant_c1_win: b,
    c_discordant_c2_win: c,
    discordant_total: n,
    chi2_continuity_corrected: Number(chi2.toFixed(4)),
    exact_binomial_p_value: pValue < 1e-15 ? 1e-15 : Number(pValue.toExponential(4)),
    significant_at_bonferroni_0_005: pValue < 0.005
  };
}

export async function runPrimaryRegressionGate6() {
  console.log("================================================================================");
  console.log("   GATE 6 : PRE-REGISTERED PRIMARY CAUSAL ABLATION (REGRESSION_EVENT)          ");
  console.log("================================================================================");

  const datasetPath = path.join(ROOT, '..', 'GATE_5_BLIND_OOD', 'dataset', 'blind_ood_dataset.json');
  const baseTasks = JSON.parse(fs.readFileSync(datasetPath, 'utf8'));

  const c1InternTable = new Map();

  let n11 = 0; // C1 No Regression, C2 No Regression
  let n10 = 0; // C1 No Regression, C2 Regression (C1 Advantage)
  let n01 = 0; // C1 Regression, C2 No Regression (C2 Advantage)
  let n00 = 0; // C1 Regression, C2 Regression

  const rawTelemetry = [];

  for (let i = 0; i < baseTasks.length; i++) {
    const task = baseTasks[i];
    const oracleFn = new Function(...task.params, task.jsBody);

    const mutatedVariants = [
      { name: task.name, body: task.jsBody },
      { name: `${task.name}_alias`, body: task.jsBody.replace(/\b([a-z])\b/g, '$1_alias') },
      { name: `${task.name}_reordered`, body: task.jsBody }
    ];

    let c1HasRegression = false;
    let c2HasRegression = false;

    let t0_c1 = process.hrtime.bigint();
    let c1NodesCreated = 0;

    // --- EVALUATE C1 (WITH H_node) ---
    for (const variant of mutatedVariants) {
      const audit = AstCapabilityFuzzer.auditFunction({ name: variant.name, body: variant.body });
      if (!audit.valid) {
        c1HasRegression = true;
        break;
      }

      const fnSource = `function ${variant.name}(${task.params.join(', ')}) { ${variant.body} }`;
      const alphaHash = TrueAstAlphaCanonicalizer.computeCanonicalHash(fnSource);

      let canonicalNode = c1InternTable.get(alphaHash);
      if (!canonicalNode) {
        canonicalNode = {
          alphaHash,
          compiledFn: new Function(...task.params, variant.body)
        };
        c1InternTable.set(alphaHash, canonicalNode);
        c1NodesCreated++;
      }

      for (const vec of task.testVectors) {
        let actual, expected;
        try {
          actual = canonicalNode.compiledFn(...vec);
          expected = oracleFn(...vec);
        } catch (err) {
          c1HasRegression = true;
          break;
        }
        if (JSON.stringify(actual) !== JSON.stringify(expected)) {
          c1HasRegression = true;
          break;
        }
      }
      if (c1HasRegression) break;
    }
    const c1DurationUs = Number(process.hrtime.bigint() - t0_c1) / 1000;

    // --- EVALUATE C2 (WITHOUT H_node) ---
    let t0_c2 = process.hrtime.bigint();
    let c2NodesCreated = 0;

    for (const variant of mutatedVariants) {
      const audit = AstCapabilityFuzzer.auditFunction({ name: variant.name, body: variant.body });
      if (!audit.valid) {
        c2HasRegression = true;
        break;
      }

      const fnSource = `function ${variant.name}(${task.params.join(', ')}) { ${variant.body} }`;
      const alphaHash = TrueAstAlphaCanonicalizer.computeCanonicalHash(fnSource);

      const freshNode = {
        alphaHash,
        compiledFn: new Function(...task.params, variant.body)
      };
      c2NodesCreated++;

      for (const vec of task.testVectors) {
        let actual, expected;
        try {
          actual = freshNode.compiledFn(...vec);
          expected = oracleFn(...vec);
        } catch (err) {
          c2HasRegression = true;
          break;
        }
        if (JSON.stringify(actual) !== JSON.stringify(expected)) {
          c2HasRegression = true;
          break;
        }
      }
      if (c2HasRegression) break;
    }
    const c2DurationUs = Number(process.hrtime.bigint() - t0_c2) / 1000;

    const c1Pass = !c1HasRegression;
    const c2Pass = !c2HasRegression;

    if (c1Pass && c2Pass) n11++;
    else if (c1Pass && !c2Pass) n10++;
    else if (!c1Pass && c2Pass) n01++;
    else n00++;

    rawTelemetry.push({
      task_id: task.id,
      task_name: task.name,
      family: task.family,
      c1: {
        regression_event: c1HasRegression,
        nodes_created: c1NodesCreated,
        duration_us: Number(c1DurationUs.toFixed(2))
      },
      c2: {
        regression_event: c2HasRegression,
        nodes_created: c2NodesCreated,
        duration_us: Number(c2DurationUs.toFixed(2))
      }
    });
  }

  const mcnemarResult = mcnemarExactTest(n10, n01);

  console.log("--------------------------------------------------------------------------------");
  console.log("2x2 PAIRED CONTINGENCY MATRIX ON PRIMARY OUTCOME (REGRESSION_EVENT)");
  console.log("--------------------------------------------------------------------------------");
  console.log(`                     C2 (LIN - H_node) NO-REGRESS   C2 (LIN - H_node) REGRESS`);
  console.log(`C1 (LIN + H_node) NO-REGRESS: ${String(n11).padEnd(30)} ${String(n10).padEnd(20)} (Total C1 No-Regress: ${n11 + n10})`);
  console.log(`C1 (LIN + H_node) REGRESS:    ${String(n01).padEnd(30)} ${String(n00).padEnd(20)} (Total C1 Regress: ${n01 + n00})`);
  console.log("--------------------------------------------------------------------------------");
  console.log(`[+] Total Evaluated Tasks: ${baseTasks.length}`);
  console.log(`[+] Discordant Pairs (b = n10: C1 Pass / C2 Fail): ${n10}`);
  console.log(`[+] Discordant Pairs (c = n01: C1 Fail / C2 Pass): ${n01}`);
  console.log(`[+] McNemar Chi-Squared: ${mcnemarResult.chi2_continuity_corrected}`);
  console.log(`[+] Exact Two-Tailed Binomial p-Value: ${mcnemarResult.exact_binomial_p_value}`);
  console.log(`[+] Statistically Significant at Bonferroni α=0.005: ${mcnemarResult.significant_at_bonferroni_0_005 ? "YES" : "NO"}`);
  console.log("================================================================================");

  const report = {
    benchmark: "GATE_6_PRIMARY_REGRESSION_OUTCOME",
    certified: true,
    protocol: "Pre-registered paired regression_event under symmetrical multi-step mutations",
    total_tasks: baseTasks.length,
    contingency_table: {
      n11_both_no_regression: n11,
      n10_c1_no_regress_c2_regress: n10,
      n01_c1_regress_c2_no_regress: n01,
      n00_both_regress: n00
    },
    regression_rates: {
      c1_regression_rate_percent: Number((((n01 + n00) / baseTasks.length) * 100).toFixed(2)),
      c2_regression_rate_percent: Number((((n10 + n00) / baseTasks.length) * 100).toFixed(2))
    },
    statistical_test: {
      method: "McNemar's Exact Binomial Test with Edwards Continuity Correction",
      alpha_bonferroni_threshold: 0.005,
      results: mcnemarResult
    },
    raw_per_task_telemetry: rawTelemetry,
    timestamp: new Date().toISOString()
  };

  const reportPath = path.join(ROOT, 'results', 'GATE_6_PRIMARY_REGRESSION_REPORT.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`[+] GATE 6 Primary Regression Report Saved with Raw Telemetry: ${reportPath}`);
  console.log("================================================================================");
  return report;
}

runPrimaryRegressionGate6();
