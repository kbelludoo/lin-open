/**
 * lin_verifier_adapter.mjs — Interface intermediária de verificação LIN
 * 
 * Executa checagem de sintaxe, efeitos proibidos e portão de comportamento.
 */

import { createHash } from 'crypto';

export class LinVerifierAdapter {
  constructor(options = {}) {
    this.options = options;
  }

  async verify(task, candidateResult, attempt) {
    const code = candidateResult.candidate_code;

    // Se o mock adapter sinalizou erro intencional
    if (candidateResult.intended_error) {
      const err = candidateResult.intended_error;
      const traumaId = `TR_${err.violation_class}_${createHash('sha256').update(code + attempt).digest('hex').slice(0, 8)}`;
      return {
        passed: false,
        stage: err.stage,
        violation_class: err.violation_class,
        location: 'line 1',
        constraint_rule: `RULE_${err.invariant}`,
        invariant_broken: err.invariant,
        remedy_hint: err.hint,
        trauma_id: traumaId
      };
    }

    // Checagem básica determinística de sintaxe (ex: parênteses/chaves)
    if (code.includes('invalid syntax') || (code.match(/\{/g) || []).length !== (code.match(/\}/g) || []).length) {
      return {
        passed: false,
        stage: 'PARSE',
        violation_class: 'SYNTAX_ERROR',
        location: 'syntax',
        constraint_rule: 'RULE_SYNTAX_WELL_FORMED',
        invariant_broken: 'BALANCED_DELIMITERS',
        remedy_hint: 'Ensure all braces and parenthesis are closed',
        trauma_id: `TR_SYNTAX_${createHash('sha256').update(code).digest('hex').slice(0, 8)}`
      };
    }

    // Checagem de efeitos proibidos
    const forbidden = task.forbidden_effects || [];
    for (const eff of forbidden) {
      if (code.includes(eff)) {
        return {
          passed: false,
          stage: 'EFFECT_CHECK',
          violation_class: 'FORBIDDEN_MUTATION',
          location: eff,
          constraint_rule: `FORBID_${eff.toUpperCase()}`,
          invariant_broken: `PURITY_VIOLATION_${eff}`,
          remedy_hint: `Remove usage of forbidden effect: ${eff}`,
          trauma_id: `TR_EFFECT_${createHash('sha256').update(eff + attempt).digest('hex').slice(0, 8)}`
        };
      }
    }

    // Passou no verificador intermediário
    return {
      passed: true,
      stage: 'VERIFY_OK',
      violation_class: null,
      trauma_id: null
    };
  }
}
