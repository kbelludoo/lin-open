// LIN AST Capability & Escape Analysis Checker with CompileCapabilityError

export const HOST_CAPABILITIES = [
  'process', 'globalThis', 'window', 'document', 'fetch', 'require',
  'eval', 'Function', 'fs', 'net', 'http', 'https', 'child_process',
  'WebSocket', 'XMLHttpRequest', 'localStorage', 'sessionStorage',
  'Reflect', 'Proxy', 'importScripts', 'Deno', 'Bun'
];

export class CompileCapabilityError extends Error {
  constructor(fnName, effect, violations) {
    super(`[CAPABILITY_VIOLATION] Function '${fnName}' declared as *(${effect}) violated effect boundaries: ${violations.map(v => v.detail).join('; ')}`);
    this.name = 'CompileCapabilityError';
    this.fnName = fnName;
    this.effect = effect;
    this.violations = violations;
  }
}

export class AstCapabilityChecker {
  static auditFunctionSemantics(fn) {
    const effect = fn.effect || 'Pure';
    const body = String(fn.body || '');

    if (effect !== 'Pure') {
      return { valid: true, effect, violations: [] };
    }

    const violations = [];

    // 1. Direct host identifier access
    for (const cap of HOST_CAPABILITIES) {
      const directRegex = new RegExp(`\\b${cap}\\b`, 'g');
      if (directRegex.test(body)) {
        violations.push({
          type: 'DIRECT_HOST_ACCESS',
          capability: cap,
          detail: `Direct reference to host capability '${cap}' in *(Pure) function '${fn.name}'`
        });
      }
    }

    // 2. Computed / Dynamic Index Access
    const computedIndexRegex = /(?:globalThis|window|self|this|global)\s*\[\s*['"`]([a-zA-Z0-9_$]+)['"`]\s*\]/g;
    let match;
    while ((match = computedIndexRegex.exec(body)) !== null) {
      const accessed = match[1];
      if (HOST_CAPABILITIES.includes(accessed)) {
        violations.push({
          type: 'COMPUTED_HOST_ACCESS',
          capability: accessed,
          detail: `Reflected computed property access '${match[0]}' in *(Pure) function '${fn.name}'`
        });
      }
    }

    // 3. Prototype Chain Constructor Escalation
    if (/constructor\s*(?:\.\s*constructor|\[\s*['"`]constructor['"`]\s*\])/g.test(body) || /\bFunction\s*\(/g.test(body)) {
      violations.push({
        type: 'CONSTRUCTOR_ESCALATION_ESCAPE',
        capability: 'Function.constructor',
        detail: `Constructor prototype chain escalation attempt in *(Pure) function '${fn.name}'`
      });
    }

    // 4. Meta-Reflection Escapes
    if (/Reflect\s*\.\s*(?:get|apply|construct|defineProperty)/g.test(body)) {
      violations.push({
        type: 'REFLECTION_ESCAPE',
        capability: 'Reflect',
        detail: `Reflective host escape via 'Reflect.*' in *(Pure) function '${fn.name}'`
      });
    }

    // 5. String-based indirect eval invocation
    if (/\(\s*0\s*,\s*eval\s*\)/g.test(body) || /\[\s*['"]ev['"]\s*\+\s*['"]al['"]\s*\]/g.test(body)) {
      violations.push({
        type: 'INDIRECT_EVAL_ESCAPE',
        capability: 'eval',
        detail: `Indirect eval invocation in *(Pure) function '${fn.name}'`
      });
    }

    return {
      valid: violations.length === 0,
      effect: 'Pure',
      violations
    };
  }

  static enforcePurityOrThrow(fn) {
    const audit = this.auditFunctionSemantics(fn);
    if (!audit.valid) {
      throw new CompileCapabilityError(fn.name, fn.effect || 'Pure', audit.violations);
    }
    return audit;
  }
}
