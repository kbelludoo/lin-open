/**
 * metrics.mjs — Cálculo independente de métricas conforme SPEC_V1.md
 * 
 * Nenhuma dependência com os modelos ou adaptadores.
 * Processa apenas uma lista de resultados de tarefas com desfechos e eventos.
 */

export function calculateMetrics(taskResults) {
  const N = taskResults.length;
  if (N === 0) {
    throw new Error('Não é possível calcular métricas sobre um conjunto vazio de tarefas.');
  }

  let P1 = 0;
  let PR = 0;
  let FF = 0;
  let F1 = 0;

  let totalTokensSuccess = 0;
  let totalAttemptsSuccess = 0;
  let successCount = 0;

  let repeatedErrorCount = 0;
  let totalRetryFailures = 0;

  for (const res of taskResults) {
    const attempts = res.attempts || [];
    const k1 = attempts[0];
    const initialPassed = k1 && k1.oracle_passed === true && k1.verifier_passed === true;

    if (initialPassed) {
      P1++;
    } else {
      F1++;
    }

    if (res.outcome === 'P1') {
      successCount++;
      totalTokensSuccess += res.total_tokens || 0;
      totalAttemptsSuccess += res.attempts_count || 1;
    } else if (res.outcome === 'PR') {
      PR++;
      successCount++;
      totalTokensSuccess += res.total_tokens || 0;
      totalAttemptsSuccess += res.attempts_count || attempts.length;
    } else if (res.outcome === 'FF') {
      FF++;
    } else {
      throw new Error(`Desfecho desconhecido: ${res.outcome}`);
    }

    // Cálculo do ERR: repetição da mesma classe de violação em retries consecutivos com falha
    for (let i = 1; i < attempts.length; i++) {
      const prev = attempts[i - 1];
      const curr = attempts[i];
      if (prev && !prev.verifier_passed && curr && !curr.verifier_passed) {
        totalRetryFailures++;
        if (
          prev.violation_class &&
          curr.violation_class &&
          prev.violation_class === curr.violation_class
        ) {
          repeatedErrorCount++;
        }
      }
    }
  }

  // Invariante de contagem
  if (P1 + PR + FF !== N) {
    throw new Error(`Invariante violada: P1 (${P1}) + PR (${PR}) + FF (${FF}) !== N (${N})`);
  }

  const pass_at_1 = P1 / N;
  const pass_at_k = (P1 + PR) / N;
  const recovery_success_rate = F1 > 0 ? PR / F1 : null;
  const avg_tokens_per_pass = successCount > 0 ? totalTokensSuccess / successCount : 0;
  const avg_attempts_per_pass = successCount > 0 ? totalAttemptsSuccess / successCount : 0;
  const error_repetition_rate = totalRetryFailures > 0 ? repeatedErrorCount / totalRetryFailures : 0;

  return {
    total_tasks: N,
    initial_pass_p1: P1,
    initial_fail_f1: F1,
    recovered_pass_pr: PR,
    final_fail_ff: FF,
    pass_at_1: Number(pass_at_1.toFixed(6)),
    pass_at_k: Number(pass_at_k.toFixed(6)),
    recovery_success_rate: recovery_success_rate !== null ? Number(recovery_success_rate.toFixed(6)) : null,
    avg_tokens_per_pass: Number(avg_tokens_per_pass.toFixed(2)),
    avg_attempts_per_pass: Number(avg_attempts_per_pass.toFixed(4)),
    error_repetition_rate: Number(error_repetition_rate.toFixed(6)),
    counters: {
      repeated_error_count: repeatedErrorCount,
      total_retry_failures: totalRetryFailures
    }
  };
}
