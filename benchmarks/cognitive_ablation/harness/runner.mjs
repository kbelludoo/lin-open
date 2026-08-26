/**
 * runner.mjs — Orquestrador do Benchmark de Ablação Cognitiva
 * 
 * Executa o ciclo formal: Propose -> Verify -> Trauma -> Oracle -> Metrics.
 */

import { calculateMetrics } from './metrics.mjs';
import { createHash } from 'crypto';

export class CognitiveBenchmarkRunner {
  constructor({ modelAdapter, verifierAdapter, defaultOracle, options = {} }) {
    this.modelAdapter = modelAdapter;
    this.verifierAdapter = verifierAdapter;
    this.defaultOracle = defaultOracle;
    this.maxAttempts = options.maxAttempts || 3;
    this.feedbackMode = options.feedbackMode || 'TRAUMA'; // 'NONE', 'UNSTRUCTURED', 'TRAUMA'
  }

  async runTask(task, oracleFn = null) {
    const activeOracle = oracleFn || this.defaultOracle || (async () => ({ passed: true }));
    const attempts = [];
    let outcome = 'FF';
    let traumaHistory = [];
    let totalTokens = 0;
    let totalLatency = 0;

    for (let k = 1; k <= this.maxAttempts; k++) {
      // 1. Geração do candidato pelo modelo
      const candidateRes = await this.modelAdapter.generateCandidate(task, k, traumaHistory);
      totalTokens += candidateRes.tokens || 0;
      totalLatency += candidateRes.latency_ms || 0;

      // 2. Verificação intermediária LIN
      const verifierRes = await this.verifierAdapter.verify(task, candidateRes, k);

      const attemptLog = {
        attempt: k,
        candidate_hash: candidateRes.candidate_hash,
        candidate_code: candidateRes.candidate_code,
        tokens: candidateRes.tokens,
        latency_ms: candidateRes.latency_ms,
        verifier_passed: verifierRes.passed,
        verifier_stage: verifierRes.stage,
        violation_class: verifierRes.violation_class,
        oracle_passed: false
      };

      if (!verifierRes.passed) {
        // Falha no verificador intermediário
        const trauma = {
          trauma_id: verifierRes.trauma_id,
          candidate_hash: candidateRes.candidate_hash,
          attempt: k,
          stage: verifierRes.stage,
          violation_class: verifierRes.violation_class,
          location: verifierRes.location,
          constraint_rule: verifierRes.constraint_rule,
          invariant_broken: verifierRes.invariant_broken,
          remedy_hint: verifierRes.remedy_hint
        };

        if (this.feedbackMode === 'TRAUMA') {
          traumaHistory.push(trauma);
        } else if (this.feedbackMode === 'UNSTRUCTURED') {
          traumaHistory.push({ error_message: `Error in ${verifierRes.stage}: ${verifierRes.violation_class}` });
        }
        attemptLog.trauma = trauma;
        attempts.push(attemptLog);
        continue;
      }

      // 3. Verificador passou -> Executa o Oracle Independente
      const oracleRes = await activeOracle(task, candidateRes);
      attemptLog.oracle_passed = oracleRes.passed;

      if (oracleRes.passed) {
        outcome = k === 1 ? 'P1' : 'PR';
        attempts.push(attemptLog);
        break; // Sucesso -> interrompe o loop
      } else {
        // Falha no Oracle
        const trauma = {
          trauma_id: `TR_ORACLE_${createHash('sha256').update(candidateRes.candidate_code + k).digest('hex').slice(0, 8)}`,
          candidate_hash: candidateRes.candidate_hash,
          attempt: k,
          stage: 'RUNTIME_ERROR',
          violation_class: 'ORACLE_ASSERTION_FAIL',
          location: 'oracle',
          constraint_rule: 'RULE_ORACLE_PASS',
          invariant_broken: 'ORACLE_SPEC_MISMATCH',
          remedy_hint: oracleRes.hint || 'Oracle assertion failed'
        };

        if (this.feedbackMode === 'TRAUMA') {
          traumaHistory.push(trauma);
        } else if (this.feedbackMode === 'UNSTRUCTURED') {
          traumaHistory.push({ error_message: 'Oracle test failed' });
        }
        attemptLog.trauma = trauma;
        attempts.push(attemptLog);
      }
    }

    return {
      task_id: task.id,
      outcome,
      attempts_count: attempts.length,
      total_tokens: totalTokens,
      total_latency_ms: totalLatency,
      attempts
    };
  }

  async runBenchmark({ tasks, oracles = {}, manifestSha256 = 'unknown', systemId = 'E', modelId = 'mock-v1' }) {
    const taskResults = [];
    const timestamp = new Date().toISOString();

    for (const task of tasks) {
      const oracleFn = oracles[task.id] || null;
      const res = await this.runTask(task, oracleFn);
      taskResults.push(res);
    }

    const summary = calculateMetrics(taskResults);

    return {
      run_id: `run_${systemId}_${Date.now()}`,
      system_id: systemId,
      model_id: modelId,
      timestamp,
      manifest_sha256: manifestSha256,
      summary,
      task_results: taskResults
    };
  }
}
