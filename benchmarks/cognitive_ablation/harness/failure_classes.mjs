/**
 * failure_classes.mjs — Classificação formal de desfechos de execução
 *
 * 6 categorias mutuamente exclusivas:
 *   PASS              — Oráculo independente aprovou
 *   INVALID_LIN       — Candidato não é sintaxe LIN válida (nem transpilável)
 *   COMPILATION_FAILURE — Sintaxe válida mas transpilador/parser rejeitou
 *   ORACLE_FAILURE    — Passou no verificador intermediário E oráculo foi executado E falhou
 *   MODEL_FAILURE     — Modelo não retornou texto utilizável (vazio, timeout, erro de API)
 *   TIMEOUT           — Inferência excedeu o limite de tempo sem produzir resposta
 *
 * Invariante: ORACLE_FAILURE implica que o oráculo FOI chamado.
 * Se o verificador rejeitou, o oráculo NÃO é chamado → INVALID_LIN.
 *
 * Cada desfecho é atômico: um candidato recebe exatamente UMA classe.
 */

export const FailureClass = Object.freeze({
  PASS:                'PASS',
  INVALID_LIN:         'INVALID_LIN',
  COMPILATION_FAILURE: 'COMPILATION_FAILURE',
  ORACLE_FAILURE:      'ORACLE_FAILURE',
  MODEL_FAILURE:       'MODEL_FAILURE',
  TIMEOUT:             'TIMEOUT',
});

/**
 * Determina a classe de falha a partir do resultado bruto do modelo
 * e dos estágios subsequentes (verificador, oráculo).
 *
 * @param {object} params
 * @param {boolean} params.modelError      — houve erro de API/timeout no modelo
 * @param {boolean} params.modelTimeout    — inferência excedeu timeout
 * @param {string}  params.rawOutput       — texto bruto retornado pelo modelo
 * @param {string}  params.candidateCode   — código extraído (pós-sanitização)
 * @param {boolean} params.verifierPassed  — verificador intermediário LIN aprovou
 * @param {boolean} params.oracleExecuted  — oráculo foi efetivamente chamado
 * @param {boolean} params.oraclePassed    — oráculo independente aprovou
 * @returns {string} Uma das 6 classes de FailureClass
 */
export function classifyFailure({
  modelError      = false,
  modelTimeout    = false,
  rawOutput       = '',
  candidateCode   = '',
  verifierPassed  = false,
  oracleExecuted  = false,
  oraclePassed    = false,
} = {}) {

  // 1. Timeout do modelo
  if (modelTimeout) return FailureClass.TIMEOUT;

  // 2. Erro de API / resposta vazia / modelo indisponível
  if (modelError) return FailureClass.MODEL_FAILURE;

  // 3. Não produziu nada utilizável
  if (!rawOutput || !rawOutput.trim()) return FailureClass.MODEL_FAILURE;
  if (!candidateCode || !candidateCode.trim()) return FailureClass.MODEL_FAILURE;

  // 4. Verificador LIN rejeitou → oráculo NÃO executado
  if (!verifierPassed) return FailureClass.INVALID_LIN;

  // 5. Verificador passou, oráculo executado e rejeitou
  //    Invariante: oracleExecuted deve ser true aqui
  if (!oraclePassed) return FailureClass.ORACLE_FAILURE;

  // 6. Tudo passou
  return FailureClass.PASS;
}

/**
 * Gera o contagem de ocorrências de cada classe a partir de um array de resultados.
 *
 * @param {Array<{failure_class: string}>} results
 * @returns {Record<string, number>}
 */
export function countByClass(results) {
  const counts = {};
  for (const key of Object.values(FailureClass)) {
    counts[key] = 0;
  }
  for (const r of results) {
    const cls = r.failure_class || 'MODEL_FAILURE';
    counts[cls] = (counts[cls] || 0) + 1;
  }
  return counts;
}

/**
 * Calcula taxas derivadas das contagens.
 *
 * @param {Record<string, number>} counts
 * @param {number} totalTasks
 * @returns {object}
 */
export function deriveRates(counts, totalTasks) {
  const N = totalTasks || 1;
  return {
    compile_pass_rate:  (counts.PASS + counts.ORACLE_FAILURE) / N,
    oracle_pass_rate:   counts.PASS / N,
    invalid_lin_rate:   counts.INVALID_LIN / N,
    model_failure_rate: counts.MODEL_FAILURE / N,
    timeout_rate:       counts.TIMEOUT / N,
  };
}
