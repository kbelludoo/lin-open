/**
 * mock_model_adapter.mjs — Adaptador de modelo determinístico para validação do harness
 * 
 * Modela trajetórias pré-determinadas (M01..M05) sem depender de rede neural.
 */

import { createHash } from 'crypto';

export class MockModelAdapter {
  constructor(trajectoryMap = {}, solutionsMap = {}) {
    this.trajectoryMap = trajectoryMap;
    this.solutionsMap = solutionsMap;
  }

  setTrajectory(taskId, trajectoryType) {
    this.trajectoryMap[taskId] = trajectoryType;
  }

  async generateCandidate(task, attempt, traumaHistory = []) {
    const trajectory = this.trajectoryMap[task.id] || 'M01';
    const tokens = 100 + attempt * 25;
    const latency_ms = 40 + attempt * 10;
    const correctCode = this.solutionsMap[task.id] || `!solve(x){ ^x * 2 }`;

    let candidateCode = '';
    let intendedError = null;

    switch (trajectory) {
      case 'M01': // Passa na tentativa 1 (P1)
        candidateCode = correctCode;
        break;

      case 'M02': // Falha tentativa 1 (PARSE_ERR), passa tentativa 2 (PR)
        if (attempt === 1) {
          candidateCode = `!solve(x){ invalid syntax`;
          intendedError = {
            stage: 'PARSE',
            violation_class: 'SYNTAX_ERROR',
            invariant: 'MATCHING_BRACES',
            hint: 'close the brace with }'
          };
        } else {
          candidateCode = correctCode;
        }
        break;

      case 'M03': // Falha t1 (EFFECT), falha t2 (TYPE), passa t3 (PR)
        if (attempt === 1) {
          candidateCode = `!solve(x){ globalState.mut = true; ^x }`;
          intendedError = {
            stage: 'EFFECT_CHECK',
            violation_class: 'FORBIDDEN_MUTATION',
            invariant: 'PURE_FUNCTION',
            hint: 'remove global mutation'
          };
        } else if (attempt === 2) {
          candidateCode = `!solve(x){ ^"wrong_string_type" }`;
          intendedError = {
            stage: 'BEHAVIOR_GATE',
            violation_class: 'TYPE_MISMATCH',
            invariant: 'RETURN_VALID',
            hint: 'return valid calculation'
          };
        } else {
          candidateCode = correctCode;
        }
        break;

      case 'M04': // Falha em todas as 3 tentativas (FF)
        candidateCode = `!solve(x){ ^-999999 }`;
        intendedError = null; // Cai no Oracle e falha deterministicamente
        break;

      case 'M05': // Falha t1 (EFFECT), repete t2 (EFFECT), passa t3 (PR) -> Testa ERR
        if (attempt === 1) {
          candidateCode = `!solve(x){ db.write(x); ^x }`;
          intendedError = {
            stage: 'EFFECT_CHECK',
            violation_class: 'FORBIDDEN_MUTATION',
            invariant: 'NO_IO',
            hint: 'remove db.write'
          };
        } else if (attempt === 2) {
          // Repete a mesma classe de erro para disparar o contador ERR
          candidateCode = `!solve(x){ file.write(x); ^x }`;
          intendedError = {
            stage: 'EFFECT_CHECK',
            violation_class: 'FORBIDDEN_MUTATION',
            invariant: 'NO_IO',
            hint: 'remove file.write'
          };
        } else {
          candidateCode = correctCode;
        }
        break;

      default:
        candidateCode = correctCode;
    }

    const candidate_hash = createHash('sha256').update(candidateCode).digest('hex').slice(0, 16);

    return {
      candidate_code: candidateCode,
      candidate_hash,
      tokens,
      latency_ms,
      intended_error: intendedError
    };
  }
}
