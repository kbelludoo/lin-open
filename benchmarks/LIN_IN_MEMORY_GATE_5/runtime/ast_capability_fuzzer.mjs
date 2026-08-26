// LIN 10,000 Adversarial Capability Fuzzer & False-Positive Validation Engine
import { AstAlphaCanonicalizer } from './ast_alpha_canonicalizer.mjs';

export const FORBIDDEN_HOST_CAPABILITIES = [
  'process', 'globalThis', 'window', 'document', 'fetch', 'require',
  'eval', 'Function', 'fs', 'net', 'http', 'https', 'child_process',
  'WebSocket', 'XMLHttpRequest', 'localStorage', 'sessionStorage',
  'Reflect', 'Proxy', 'importScripts', 'Deno', 'Bun'
];

export class AstCapabilityFuzzer {
  // Deep Token & Semantic Capability Verifier
  static auditFunction(fn) {
    if (fn.effect !== 'Pure') {
      return { valid: true, effect: fn.effect, violations: [] };
    }

    const tokens = AstAlphaCanonicalizer.tokenize(fn.body || '');
    const violations = [];

    // Track dynamic aliasing across statements: e.g. const g = globalThis; const c = obj["constructor"]
    const aliasedGlobals = new Set();
    const aliasedCtors = new Set();

    for (let i = 0; i < tokens.length; i++) {
      const tok = tokens[i];

      // Skip string literals & comments for direct identifier access to prevent False Positives
      if (tok.type === 'STRING_LITERAL' || tok.type === 'COMMENT') {
        continue;
      }

      // 1. Direct host identifier lookup (outside string literals!)
      if (tok.type === 'IDENTIFIER' && FORBIDDEN_HOST_CAPABILITIES.includes(tok.value)) {
        violations.push({
          type: 'DIRECT_IDENTIFIER',
          target: tok.value,
          detail: `Direct access to forbidden host identifier '${tok.value}' in *(Pure)`
        });
      }

      // 2. Track global aliasing: const g = globalThis, const x = window, const y = this
      if (tok.type === 'IDENTIFIER' && (tok.value === 'const' || tok.value === 'let' || tok.value === 'var')) {
        if (i + 3 < tokens.length && tokens[i + 1].type === 'IDENTIFIER' && tokens[i + 2].value === '=') {
          const varName = tokens[i + 1].value;
          const assigned = tokens[i + 3].value;
          if (assigned === 'globalThis' || assigned === 'window' || assigned === 'this' || assigned === 'global' || assigned === 'self') {
            aliasedGlobals.add(varName);
          }
          if (assigned === 'Reflect' || assigned === 'Proxy') {
            aliasedGlobals.add(varName);
          }
        }
      }

      // 3. Computed Index / Dynamic Access on globals or aliased variables: g["process"], globalThis['fetch'], window['eval']
      if (tok.type === 'IDENTIFIER' && (tok.value === 'globalThis' || tok.value === 'window' || tok.value === 'self' || tok.value === 'this' || aliasedGlobals.has(tok.value))) {
        if (i + 1 < tokens.length && tokens[i + 1].value === '[') {
          // Computed bracket access on a global alias!
          let j = i + 2;
          let bracketContent = '';
          while (j < tokens.length && tokens[j].value !== ']') {
            bracketContent += tokens[j].value;
            j++;
          }
          for (const cap of FORBIDDEN_HOST_CAPABILITIES) {
            if (bracketContent.includes(cap) || bracketContent.includes('constructor') || bracketContent.includes('join') || bracketContent.includes('+')) {
              violations.push({
                type: 'COMPUTED_GLOBAL_ACCESS',
                target: bracketContent,
                detail: `Dynamic computed property lookup '${tok.value}[${bracketContent}]' in *(Pure)`
              });
              break;
            }
          }
        }
      }

      // 4. Constructor / Prototype Escalation: obj["constructor"], obj.constructor.constructor
      if (tok.value === 'constructor') {
        if (i + 1 < tokens.length && (tokens[i + 1].value === '(' || tokens[i + 1].value === '[' || (tokens[i + 1].value === '.' && i + 2 < tokens.length && tokens[i + 2].value === 'constructor'))) {
          violations.push({
            type: 'CONSTRUCTOR_ESCALATION',
            target: 'constructor',
            detail: `Constructor prototype escalation detected in *(Pure)`
          });
        }
      }

      // 5. Reflection & Meta-Programming: Reflect.get, Reflect.apply, Reflect["apply"]
      if (tok.value === 'Reflect' || aliasedGlobals.has('Reflect')) {
        violations.push({
          type: 'REFLECTION_CALL',
          target: 'Reflect',
          detail: `Reflective meta-programming access 'Reflect' in *(Pure)`
        });
      }

      // 6. Indirect eval comma operator: (0, eval)(...)
      if (tok.value === '(' && i + 4 < tokens.length && tokens[i + 1].value === '0' && tokens[i + 2].value === ',' && tokens[i + 3].value === 'eval') {
        violations.push({
          type: 'INDIRECT_EVAL',
          target: 'eval',
          detail: `Indirect eval comma operator expression in *(Pure)`
        });
      }
    }

    return {
      valid: violations.length === 0,
      effect: fn.effect || 'Pure',
      violations
    };
  }

  // Generate 10,000 Synthetic Adversarial Escape Attacks
  static generate10kAttacks() {
    const attacks = [];
    const globalAliases = ['globalThis', 'window', 'self', 'this', 'g', 'root', 'host'];
    const caps = FORBIDDEN_HOST_CAPABILITIES;
    const joins = [
      (c) => `'${c}'`,
      (c) => `['${c.slice(0, 2)}', '${c.slice(2)}'].join('')`,
      (c) => `'${c.slice(0, 3)}' + '${c.slice(3)}'`,
      (c) => `"${c}"`
    ];

    for (let i = 0; i < 10000; i++) {
      const alias = globalAliases[i % globalAliases.length];
      const cap = caps[i % caps.length];
      const joiner = joins[i % joins.length];

      let body = '';
      const mode = i % 5;
      if (mode === 0) {
        // Direct access
        body = `return ${cap};`;
      } else if (mode === 1) {
        // Aliased global bracket access
        body = `const ${alias} = globalThis; const f = ${alias}[${joiner(cap)}]; return f();`;
      } else if (mode === 2) {
        // Constructor escalation
        body = `const c = ({}).constructor.constructor; return c('return ${cap}')();`;
      } else if (mode === 3) {
        // Reflect escape
        body = `return Reflect.get(globalThis, '${cap}');`;
      } else {
        // Indirect eval / dynamic execution
        body = `return (0, eval)('${cap}');`;
      }

      attacks.push({
        id: `FUZZ_ATTACK_${i.toString().padStart(5, '0')}`,
        name: `Attack Vector ${i} (${cap} via Mode ${mode})`,
        fn: {
          name: `malicious_${i}`,
          params: ["input"],
          effect: "Pure",
          body
        }
      });
    }

    return attacks;
  }

  // Generate 50 Legitimate Pure Functions that contain tricky words inside string literals or comments
  // (Testing that False Positives are strictly 0.0%)
  static generateFalsePositiveTestSet() {
    const legitimateTests = [];
    const stringsWithTrickyKeywords = [
      "The window of opportunity is open",
      "We are processing the transaction",
      "Let's fetch the data description",
      "Running evaluation metric",
      "Object constructor pattern is clean",
      "Checking process status message"
    ];

    for (let i = 0; i < 50; i++) {
      const trickyStr = stringsWithTrickyKeywords[i % stringsWithTrickyKeywords.length];
      legitimateTests.push({
        id: `LEGITIMATE_PURE_${i}`,
        name: `Legitimate Pure Function ${i}`,
        fn: {
          name: `safeFunction_${i}`,
          params: ["x", "y"],
          effect: "Pure",
          body: `
            // This is a comment mentioning process and window and fetch
            const label = "${trickyStr}";
            const calc = x + y;
            return label + ": " + calc;
          `
        }
      });
    }

    return legitimateTests;
  }
}
