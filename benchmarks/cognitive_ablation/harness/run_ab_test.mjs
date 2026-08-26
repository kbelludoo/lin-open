/**
 * run_ab_test.mjs — Execução A/B/C: Zero-shot vs Few-shot vs Constrained
 *
 * Mesmo modelo, mesmas 30 tarefas, mesmas configurações.
 * Única variável: prompt (condição).
 *
 * Saída:
 *   - results/AB_TEST_<timestamp>/
 *     ├── condition_A/  (zero-shot)
 *     │   ├── config.json
 *     │   ├── task_results.json
 *     │   └── metrics.json
 *     ├── condition_B/  (few-shot)
 *     │   └── ...
 *     ├── condition_C/  (constrained)
 *     │   └── ...
 *     └── COMPARISON.json
 */

import fs from 'fs';
import path from 'path';
import { createHash } from 'crypto';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_DIR = path.join(__dirname, '..');
const MANIFEST_PATH = path.join(BASE_DIR, 'MANIFEST.json');
const RUNS_DIR = path.join(BASE_DIR, 'results');

import { FewShotAdapter } from './fewshot_adapter.mjs';
import { LinVerifierAdapter } from './lin_verifier_adapter.mjs';
import { classifyFailure, countByClass, deriveRates } from './failure_classes.mjs';

const EXPECTED_MANIFEST_SHA256 = 'd3951769e4f9d210657a93659deee8b3ccc611e2f0f309373bc8fa358bec3061';

function shuffleWithSeed(arr, seed) {
  const a = [...arr];
  // Mulberry32 PRNG — deterministic, same seed = same shuffle
  let s = seed | 0;
  for (let i = a.length - 1; i > 0; i--) {
    s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    const j = ((t ^ (t >>> 14)) >>> 0) % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const CONDITIONS = [
  {
    id: 'A',
    name: 'LIN Zero-Shot',
    mode: 'ZERO_SHOT',
  },
  {
    id: 'B',
    name: 'LIN Few-Shot (5 examples)',
    mode: 'FEW_SHOT',
  },
  {
    id: 'C',
    name: 'LIN Constrained (5 examples + grammar rules)',
    mode: 'CONSTRAINED',
  },
];

async function loadTasks() {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf-8'));
  if (manifest.global_sha256 !== EXPECTED_MANIFEST_SHA256) {
    throw new Error('MANIFEST INTEGRITY VIOLATION');
  }

  const tasks = [];
  const oracles = {};

  for (const entry of manifest.tasks) {
    const taskPath = path.join(BASE_DIR, 'tasks', `${entry.id}.json`);
    const task = JSON.parse(fs.readFileSync(taskPath, 'utf-8'));
    tasks.push(task);

    const oraclePath = path.join(BASE_DIR, entry.oracle_entrypoint);
    const mod = await import(`file://${oraclePath}`);
    oracles[entry.id] = mod.oracle;
  }

  return { manifest, tasks, oracles };
}

function classifyAttempt({
  modelError,
  modelTimeout,
  rawOutput,
  candidateCode,
  verifierPassed,
  oracleExecuted,
  oraclePassed,
}) {
  return classifyFailure({
    modelError,
    modelTimeout,
    rawOutput,
    candidateCode,
    verifierPassed,
    oracleExecuted,
    oraclePassed,
  });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getRuntimeState(baseUrl) {
  try {
    const res = await fetch(`${baseUrl}/api/ps`);
    if (res.ok) {
      const data = await res.json();
      return {
        loaded_models: (data.models || []).map(m => ({
          name: m.name,
          size: m.size,
          size_vram: m.size_vram,
        })),
        model_count: (data.models || []).length,
      };
    }
  } catch (e) { /* ignore */ }
  return { loaded_models: [], model_count: -1, error: 'unreachable' };
}

async function unloadAllModels(baseUrl, modelName) {
  try {
    await fetch(`${baseUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelName, keep_alive: 0 }),
    });
    await sleep(1500);
  } catch (e) { /* best effort */ }
}

async function runCondition({ condition, tasks, oracles, verifierAdapter, manifestSha256, modelConfig, maxAttempts = 1 }) {
  const adapter = new FewShotAdapter({
    baseUrl: modelConfig.baseUrl,
    provider: modelConfig.provider,
    model: modelConfig.model,
    temperature: modelConfig.temperature,
    seed: modelConfig.seed,
    mode: condition.mode,
  });

  // Shuffle tasks deterministically per condition to prevent order bias.
  // Each condition gets a DIFFERENT shuffle seed derived from the global seed + condition id,
  // so task order varies but is reproducible.
  const conditionSeed = modelConfig.seed + condition.id.charCodeAt(0);
  const shuffledTasks = shuffleWithSeed(tasks, conditionSeed);

  const taskResults = [];
  const timestamp = new Date().toISOString();

  for (const task of shuffledTasks) {
    const oracleFn = oracles[task.id];
    const attempts = [];
    let finalFailureClass = 'MODEL_FAILURE';

    // Run up to maxAttempts (default: 1 for single-shot)
    for (let k = 1; k <= maxAttempts; k++) {
      const candidateRes = await adapter.generateCandidate(task, k, []);

      const verifierRes = await verifierAdapter.verify(task, candidateRes, k);
      let oraclePassed = false;
      let oracleExecuted = false;

      if (verifierRes.passed) {
        oracleExecuted = true;
        try {
          const oracleRes = await oracleFn(task, candidateRes);
          oraclePassed = oracleRes.passed;
        } catch (e) {
          oraclePassed = false;
        }
      }

      finalFailureClass = classifyAttempt({
        modelError: candidateRes.model_error,
        modelTimeout: candidateRes.model_timeout,
        rawOutput: candidateRes.raw_output,
        candidateCode: candidateRes.candidate_code,
        verifierPassed: verifierRes.passed,
        oracleExecuted,
        oraclePassed,
      });

      attempts.push({
        attempt: k,
        candidate_hash: candidateRes.candidate_hash,
        candidate_code: candidateRes.candidate_code,
        prompt_tokens: candidateRes.prompt_tokens || 0,
        completion_tokens: candidateRes.completion_tokens || 0,
        tokens: candidateRes.tokens,
        latency_ms: candidateRes.latency_ms,
        verifier_passed: verifierRes.passed,
        oracle_executed: oracleExecuted,
        oracle_passed: oraclePassed,
        failure_class: finalFailureClass,
        condition: condition.mode,
      });

      // If passed, stop early
      if (oraclePassed) break;
    }

    taskResults.push({
      task_id: task.id,
      family: task.family,
      difficulty: task.difficulty,
      failure_class: finalFailureClass,
      compile_pass: attempts[attempts.length - 1]?.verifier_passed ?? false,
      oracle_pass: attempts[attempts.length - 1]?.oracle_passed ?? false,
      prompt_tokens: attempts.reduce((s, a) => s + (a.prompt_tokens || 0), 0),
      completion_tokens: attempts.reduce((s, a) => s + (a.completion_tokens || 0), 0),
      total_tokens: attempts.reduce((s, a) => s + a.tokens, 0),
      total_latency_ms: attempts.reduce((s, a) => s + a.latency_ms, 0),
      attempts,
    });
  }

  // Calcular métricas
  const counts = countByClass(taskResults);
  const rates = deriveRates(counts, tasks.length);

  const totalTokens = taskResults.reduce((s, r) => s + r.total_tokens, 0);
  const totalLatency = taskResults.reduce((s, r) => s + r.total_latency_ms, 0);
  const successResults = taskResults.filter(r => r.failure_class === 'PASS');

  const totalPromptTokens = taskResults.reduce((s, r) => s + r.prompt_tokens, 0);
  const totalCompletionTokens = taskResults.reduce((s, r) => s + r.completion_tokens, 0);

  const summary = {
    ...rates,
    counts,
    total_tasks: tasks.length,
    total_tokens: totalTokens,
    total_prompt_tokens: totalPromptTokens,
    total_completion_tokens: totalCompletionTokens,
    total_latency_ms: totalLatency,
    avg_tokens_per_task: totalTokens / tasks.length,
    avg_prompt_tokens_per_task: totalPromptTokens / tasks.length,
    avg_completion_tokens_per_task: totalCompletionTokens / tasks.length,
    avg_latency_per_task: totalLatency / tasks.length,
    avg_tokens_per_pass: successResults.length > 0
      ? successResults.reduce((s, r) => s + r.total_tokens, 0) / successResults.length
      : null,
  };

  return {
    condition_id: condition.id,
    condition_name: condition.name,
    mode: condition.mode,
    timestamp,
    manifest_sha256: manifestSha256,
    model_config: modelConfig,
    summary,
    task_results: taskResults,
  };
}

function buildComparison(results) {
  // Build per-task comparison matrix
  const taskMatrix = {};
  for (const result of results) {
    for (const tr of result.task_results) {
      if (!taskMatrix[tr.task_id]) {
        taskMatrix[tr.task_id] = {
          task_id: tr.task_id,
          family: tr.family,
          difficulty: tr.difficulty,
          conditions: {},
        };
      }
      taskMatrix[tr.task_id].conditions[result.condition_id] = {
        failure_class: tr.failure_class,
        compile_pass: tr.compile_pass,
        oracle_pass: tr.oracle_pass,
        oracle_executed: tr.attempts.some(a => a.oracle_executed),
        prompt_tokens: tr.prompt_tokens,
        completion_tokens: tr.completion_tokens,
        total_tokens: tr.total_tokens,
        total_latency_ms: tr.total_latency_ms,
        attempts_count: tr.attempts.length,
      };
    }
  }

  const perTask = Object.values(taskMatrix).sort((a, b) => a.task_id.localeCompare(b.task_id));

  const comparison = {
    experiment: 'LIN_ABLATION_A_B_C',
    version: '1.0.0',
    protocol_version: 'PHASE0_SMOKE',
    timestamp: new Date().toISOString(),
    status: 'PRELIMINARY / NOT A FINAL DENSITY BENCHMARK',
    per_task: perTask,
    conditions: results.map(r => ({
      id: r.condition_id,
      name: r.condition_name,
      mode: r.mode,
      compile_pass_rate: r.summary.compile_pass_rate,
      oracle_pass_rate: r.summary.oracle_pass_rate,
      invalid_lin_rate: r.summary.invalid_lin_rate,
      model_failure_rate: r.summary.model_failure_rate,
      timeout_rate: r.summary.timeout_rate,
      avg_tokens_per_task: r.summary.avg_tokens_per_task,
      avg_latency_per_task: r.summary.avg_latency_per_task,
      avg_tokens_per_pass: r.summary.avg_tokens_per_pass,
      counts: r.summary.counts,
    })),
    deltas: {},
    efficiency: {},
  };

  // Calcular deltas entre condições
  const conditions = comparison.conditions;
  for (let i = 0; i < conditions.length; i++) {
    for (let j = i + 1; j < conditions.length; j++) {
      const a = conditions[i];
      const b = conditions[j];
      const key = `${a.id}_vs_${b.id}`;
      comparison.deltas[key] = {
        compile_pass_rate_delta: b.compile_pass_rate - a.compile_pass_rate,
        oracle_pass_rate_delta: b.oracle_pass_rate - a.oracle_pass_rate,
        tokens_delta: b.avg_tokens_per_task - a.avg_tokens_per_task,
        latency_delta: b.avg_latency_per_task - a.avg_latency_per_task,
        invalid_lin_rate_delta: b.invalid_lin_rate - a.invalid_lin_rate,
      };

      // EfficiencyGain = (PassRate_B / Tokens_B) / (PassRate_A / Tokens_A)
      // TokenSavings = 1 - (Tokens_B / Tokens_A)
      const tokensA = a.avg_tokens_per_task || 1;
      const tokensB = b.avg_tokens_per_task || 1;
      const passA = a.oracle_pass_rate || 0;
      const passB = b.oracle_pass_rate || 0;

      const efficiencyA = passA / tokensA;
      const efficiencyB = passB / tokensB;

      let efficiencyGain = null;
      let efficiencyGainReason = null;
      if (passA === 0 && passB === 0) {
        efficiencyGainReason = 'NO_PASS_EITHER';
      } else if (passA === 0) {
        efficiencyGain = Infinity;
        efficiencyGainReason = 'NO_PASS_BASELINE';
      } else if (passB === 0) {
        efficiencyGain = 0;
        efficiencyGainReason = 'NO_PASS_TARGET';
      } else {
        efficiencyGain = efficiencyB / efficiencyA;
      }

      const tokenSavings = 1 - (tokensB / tokensA);

      comparison.efficiency[key] = {
        efficiency_gain: efficiencyGain !== null && isFinite(efficiencyGain) ? Number(efficiencyGain.toFixed(4)) : efficiencyGain,
        efficiency_gain_reason: efficiencyGainReason,
        token_savings: Number(tokenSavings.toFixed(4)),
        efficiency_a: Number(efficiencyA.toFixed(8)),
        efficiency_b: Number(efficiencyB.toFixed(8)),
      };
    }
  }

  return comparison;
}

function verifyInvariants(allResults, comparison) {
  const checks = [];

  // 1. Per-task counts sum to aggregate counts
  for (const result of allResults) {
    const cid = result.condition_id;
    const counts = result.summary.counts;
    const perTaskCounts = { PASS: 0, INVALID_LIN: 0, COMPILATION_FAILURE: 0, ORACLE_FAILURE: 0, MODEL_FAILURE: 0, TIMEOUT: 0 };
    for (const tr of result.task_results) {
      perTaskCounts[tr.failure_class] = (perTaskCounts[tr.failure_class] || 0) + 1;
    }
    const match = Object.keys(counts).every(k => counts[k] === perTaskCounts[k]);
    checks.push({
      name: `reconcile_${cid}: per_task sums == aggregate counts`,
      passed: match,
      detail: match ? null : `aggregate=${JSON.stringify(counts)} per_task=${JSON.stringify(perTaskCounts)}`,
    });
  }

  // 2. Per-task oracle_pass counts match aggregate
  for (const result of allResults) {
    const cid = result.condition_id;
    const aggregateOraclePass = result.summary.counts.PASS;
    const perTaskOraclePass = result.task_results.filter(r => r.oracle_pass).length;
    const match = aggregateOraclePass === perTaskOraclePass;
    checks.push({
      name: `oracle_pass_reconcile_${cid}: PASS count == per_task oracle_pass`,
      passed: match,
      detail: match ? null : `aggregate=${aggregateOraclePass} per_task=${perTaskOraclePass}`,
    });
  }

  // 3. Taxonomy invariants per task result
  for (const result of allResults) {
    const cid = result.condition_id;
    for (const tr of result.task_results) {
      const fc = tr.failure_class;
      const lastAttempt = tr.attempts[tr.attempts.length - 1];
      const oracleExecuted = lastAttempt?.oracle_executed ?? false;
      const verifierPassed = lastAttempt?.verifier_passed ?? false;
      const oraclePassed = lastAttempt?.oracle_passed ?? false;

      let expected = null;
      let invName = null;

      if (fc === 'PASS') {
        expected = verifierPassed && oracleExecuted && oraclePassed;
        invName = `invariant_PASS_${cid}_${tr.task_id}`;
      } else if (fc === 'ORACLE_FAILURE') {
        expected = verifierPassed && oracleExecuted && !oraclePassed;
        invName = `invariant_ORACLE_FAILURE_${cid}_${tr.task_id}`;
      } else if (fc === 'INVALID_LIN') {
        expected = !verifierPassed && !oracleExecuted;
        invName = `invariant_INVALID_LIN_${cid}_${tr.task_id}`;
      } else if (fc === 'MODEL_FAILURE') {
        expected = !oracleExecuted;
        invName = `invariant_MODEL_FAILURE_${cid}_${tr.task_id}`;
      } else if (fc === 'TIMEOUT') {
        expected = !oracleExecuted;
        invName = `invariant_TIMEOUT_${cid}_${tr.task_id}`;
      }

      if (invName) {
        checks.push({
          name: invName,
          passed: expected === true,
          detail: expected !== true ? `fc=${fc} verifier=${verifierPassed} oracle_exec=${oracleExecuted} oracle_pass=${oraclePassed}` : null,
        });
      }
    }
  }

  // 4. All task_ids present in all conditions
  const taskIds = allResults[0]?.task_results.map(r => r.task_id) || [];
  for (const result of allResults) {
    const presentIds = result.task_results.map(r => r.task_id);
    const missing = taskIds.filter(id => !presentIds.includes(id));
    checks.push({
      name: `complete_${result.condition_id}: all ${taskIds.length} tasks present`,
      passed: missing.length === 0,
      detail: missing.length > 0 ? `missing: ${missing.join(', ')}` : null,
    });
  }

  // 5. No unexpected MODEL_FAILURE/TIMEOUT (warn, don't fail — could be infra)
  for (const result of allResults) {
    const mfCount = result.summary.counts.MODEL_FAILURE + result.summary.counts.TIMEOUT;
    checks.push({
      name: `infra_health_${result.condition_id}: MODEL_FAILURE+TIMEOUT count`,
      passed: true, // informational only
      detail: `${mfCount} (informational, not a protocol violation)`,
    });
  }

  return checks;
}

async function main() {
  // CLI flags for smoke test mode
  const args = process.argv.slice(2);
  const taskFlagIdx = args.indexOf('--tasks');
  const attemptFlagIdx = args.indexOf('--attempts');
  const filterTaskIds = taskFlagIdx >= 0 ? args[taskFlagIdx + 1]?.split(',') : null;
  const maxAttempts = attemptFlagIdx >= 0 ? parseInt(args[attemptFlagIdx + 1], 10) : 1;

  console.log('🧪 LIN A/B/C Ablation Test: Zero-shot vs Few-shot vs Constrained');
  console.log('==============================================================\n');

  const modelConfig = {
    baseUrl: process.env.OLLAMA_URL || 'http://localhost:11434',
    provider: 'ollama',
    model: process.env.MODEL_NAME || 'qwen2.5-coder:7b',
    temperature: 0.0,
    seed: 42,
  };

  console.log(`Model: ${modelConfig.model}`);
  console.log(`Endpoint: ${modelConfig.baseUrl}`);
  console.log(`Conditions: ${CONDITIONS.map(c => c.id).join(', ')}\n`);

  // Carregar dataset congelado
  const { manifest, tasks: allTasks, oracles } = await loadTasks();

  // Filter tasks for smoke test mode
  const tasks = filterTaskIds
    ? allTasks.filter(t => filterTaskIds.includes(t.id))
    : allTasks;

  console.log(`Dataset: ${tasks.length} of ${manifest.total_tasks} tasks (SHA-256 verified)`);
  if (filterTaskIds) console.log(`  Filtered: ${filterTaskIds.join(', ')}`);
  if (maxAttempts > 1) console.log(`  Max attempts: ${maxAttempts}`);
  console.log('');

  const verifierAdapter = new LinVerifierAdapter();

  // Create run directory once, use for all conditions
  const runId = `AB_TEST_${Date.now()}`;
  const currentRunDir = runId;
  fs.mkdirSync(path.join(RUNS_DIR, currentRunDir), { recursive: true });

  // Executar cada condição
  const allResults = [];

  for (let i = 0; i < CONDITIONS.length; i++) {
    const condition = CONDITIONS[i];

    // Inter-condition barrier: explicit unload + state snapshot
    if (i > 0) {
      console.log(`\n⏳ Inter-condition barrier before Condition ${condition.id}...`);

      // Log runtime state BEFORE unload
      const stateBefore = await getRuntimeState(modelConfig.baseUrl);
      console.log(`  Runtime before unload: ${stateBefore.model_count} model(s) loaded`);

      // Force unload model from VRAM
      await unloadAllModels(modelConfig.baseUrl, modelConfig.model);

      // Log runtime state AFTER unload
      const stateAfter = await getRuntimeState(modelConfig.baseUrl);
      console.log(`  Runtime after unload: ${stateAfter.model_count} model(s) loaded`);

      // Save barrier log
      const barrierLog = {
        between_conditions: [CONDITIONS[i - 1].id, condition.id],
        timestamp: new Date().toISOString(),
        state_before: stateBefore,
        state_after: stateAfter,
        unload_attempted: true,
      };
      const barrierPath = path.join(RUNS_DIR, currentRunDir, `barrier_${CONDITIONS[i - 1].id}_to_${condition.id}.json`);
      fs.writeFileSync(barrierPath, JSON.stringify(barrierLog, null, 2));
    }

    console.log(`\n▶ Condition ${condition.id}: ${condition.name}`);
    console.log(`  Mode: ${condition.mode}`);

    const result = await runCondition({
      condition,
      tasks,
      oracles,
      verifierAdapter,
      manifestSha256: manifest.global_sha256,
      modelConfig,
      maxAttempts,
    });

    allResults.push(result);

    // Salvar resultados da condição
    const condDir = path.join(RUNS_DIR, currentRunDir, `condition_${condition.id}`);
    fs.mkdirSync(condDir, { recursive: true });

    fs.writeFileSync(
      path.join(condDir, 'config.json'),
      JSON.stringify({
        condition_id: condition.id,
        condition_name: condition.name,
        mode: condition.mode,
        model_config: modelConfig,
        manifest_sha256: manifest.global_sha256,
      }, null, 2)
    );

    fs.writeFileSync(
      path.join(condDir, 'task_results.json'),
      JSON.stringify(result.task_results, null, 2)
    );

    fs.writeFileSync(
      path.join(condDir, 'metrics.json'),
      JSON.stringify(result.summary, null, 2)
    );

    // Print summary
    console.log(`  compile_pass_rate: ${(result.summary.compile_pass_rate * 100).toFixed(1)}%`);
    console.log(`  oracle_pass_rate:  ${(result.summary.oracle_pass_rate * 100).toFixed(1)}%`);
    console.log(`  invalid_lin_rate:  ${(result.summary.invalid_lin_rate * 100).toFixed(1)}%`);
    console.log(`  avg_tokens:        ${result.summary.avg_tokens_per_task.toFixed(0)}`);
    console.log(`  counts:`, result.summary.counts);
  }

  // Comparação
  const comparison = buildComparison(allResults);

  const runDir = path.join(RUNS_DIR, currentRunDir);
  fs.mkdirSync(runDir, { recursive: true });
  fs.writeFileSync(
    path.join(runDir, 'COMPARISON.json'),
    JSON.stringify(comparison, null, 2)
  );

  // Print comparativo
  console.log('\n\n📊 COMPARISON');
  console.log('==============================================================');
  console.table(comparison.conditions.map(c => ({
    'Condition': c.id,
    'Compile%': (c.compile_pass_rate * 100).toFixed(1),
    'Oracle%': (c.oracle_pass_rate * 100).toFixed(1),
    'Invalid%': (c.invalid_lin_rate * 100).toFixed(1),
    'Avg Prompt': c.avg_prompt_tokens_per_task?.toFixed(0) ?? '-',
    'Avg Comp': c.avg_completion_tokens_per_task?.toFixed(0) ?? '-',
    'Avg Total': c.avg_tokens_per_task.toFixed(0),
    'Avg Latency': c.avg_latency_per_task.toFixed(0) + 'ms',
  })));

  console.log('\nDeltas & Efficiency:');
  for (const [key, delta] of Object.entries(comparison.deltas)) {
    const eff = comparison.efficiency[key];
    console.log(`  ${key}:`);
    console.log(`    compile Δ=${(delta.compile_pass_rate_delta * 100).toFixed(1)}%  oracle Δ=${(delta.oracle_pass_rate_delta * 100).toFixed(1)}%  tokens Δ=${delta.tokens_delta.toFixed(0)}`);
    const effStr = eff.efficiency_gain_reason
      ? `${eff.efficiency_gain ?? eff.efficiency_gain} (${eff.efficiency_gain_reason})`
      : `${eff.efficiency_gain}`;
    console.log(`    token_savings=${(eff.token_savings * 100).toFixed(1)}%  efficiency_gain=${effStr}`);
  }

  console.log(`\nStatus: ${comparison.status}`);

  // Per-task comparison matrix
  console.log('\n\n📋 PER-TASK RESULTS');
  console.log('==============================================================');
  const condIds = comparison.conditions.map(c => c.id);
  const header = ['Task', 'Family', 'Diff',
    ...condIds.flatMap(c => [`${c}_pass`, `${c}_prompt`, `${c}_comp`, `${c}_total`, `${c}_class`])];
  const rows = comparison.per_task.map(t => {
    const row = [t.task_id, t.family, t.difficulty];
    for (const cid of condIds) {
      const c = t.conditions[cid];
      row.push(c ? (c.oracle_pass ? 'PASS' : 'FAIL') : '-');
      row.push(c ? String(c.prompt_tokens) : '-');
      row.push(c ? String(c.completion_tokens) : '-');
      row.push(c ? String(c.total_tokens) : '-');
      row.push(c ? c.failure_class : '-');
    }
    return row;
  });
  console.table([header, ...rows]);

  // Invariant verification
  console.log('\n\n🔬 INVARIANT VERIFICATION');
  console.log('==============================================================');
  const invariantResults = verifyInvariants(allResults, comparison);
  for (const inv of invariantResults) {
    const status = inv.passed ? '✅' : '❌';
    console.log(`  ${status} ${inv.name}${inv.detail ? ` — ${inv.detail}` : ''}`);
  }

  const allPassed = invariantResults.every(r => r.passed);
  console.log(`\n  Overall: ${allPassed ? '✅ ALL INVARIANTS SATISFIED' : '❌ INVARIANT VIOLATION(S) DETECTED'}`);

  // Save invariant results to run directory
  fs.writeFileSync(
    path.join(RUNS_DIR, currentRunDir, 'INVARIANTS.json'),
    JSON.stringify({ timestamp: new Date().toISOString(), all_passed: allPassed, checks: invariantResults }, null, 2)
  );

  console.log(`\n💾 All artifacts written to: ${RUNS_DIR}`);
}

main().catch(err => {
  console.error('❌ FATAL:', err);
  process.exit(1);
});
