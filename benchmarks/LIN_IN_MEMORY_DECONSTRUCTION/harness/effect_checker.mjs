// LIN Static Effect & Capability Checker
// Rejects illegal host/global access in *(Pure) functions

export const FORBIDDEN_PURE_IDENTIFIERS = [
  'process', 'globalThis', 'window', 'document', 'fetch', 'require',
  'eval', 'Function', 'fs', 'net', 'http', 'https', 'child_process',
  'WebSocket', 'XMLHttpRequest', 'localStorage', 'sessionStorage', '__proto__'
];

export class EffectChecker {
  static verifyFunctionPurity(fnName, effect, body) {
    if (effect !== 'Pure') {
      return { valid: true, effect };
    }

    const violations = [];
    for (const forbidden of FORBIDDEN_PURE_IDENTIFIERS) {
      const regex = new RegExp(`\\b${forbidden}\\b`, 'g');
      if (regex.test(body)) {
        violations.push({
          identifier: forbidden,
          reason: `Access to forbidden host capability '${forbidden}' in declared *(Pure) function '${fnName}'`
        });
      }
    }

    return {
      valid: violations.length === 0,
      effect: 'Pure',
      violations
    };
  }

  static verifyModule(ast) {
    const report = { valid: true, auditedFunctions: 0, violations: [] };
    for (const fn of ast.functions || ast.fns || []) {
      report.auditedFunctions++;
      const res = this.verifyFunctionPurity(fn.name, fn.effect || 'Pure', fn.body || '');
      if (!res.valid) {
        report.valid = false;
        report.violations.push(...res.violations);
      }
    }
    return report;
  }
}
