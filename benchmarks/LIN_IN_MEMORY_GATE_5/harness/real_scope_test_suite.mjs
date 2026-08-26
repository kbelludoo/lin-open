// Test Suite for RealAstAlphaCanonicalizer
import { RealAstAlphaCanonicalizer } from '../runtime/real_ast_alpha_canonicalizer.mjs';

export function runRealScopeTestSuite() {
  console.log("================================================================================");
  console.log("   REAL AST SEMANTIC SCOPE-TREE ALPHA-CANONICALIZATION TEST SUITE             ");
  console.log("================================================================================");

  const cases = [
    {
      id: "CATCH_SHADOWING_POP",
      name: "Catch-Clause Error Shadowing and Scope Pop Restoration",
      fn1: { name: "catchTest1", params: ["err"], effect: "Pure", body: "try { run(); } catch (err) { log(err); } return err;" },
      fn2: { name: "catchTest2", params: ["e"], effect: "Pure", body: "try { run(); } catch (e) { log(e); } return e;" }
    },
    {
      id: "BLOCK_SHADOWING_POP",
      name: "Block-Scope Shadowing and Outer Parameter Restoration",
      fn1: { name: "blockTest1", params: ["x"], effect: "Pure", body: "if (true) { let x = 10; log(x); } return x;" },
      fn2: { name: "blockTest2", params: ["y"], effect: "Pure", body: "if (true) { let y = 10; log(y); } return y;" }
    },
    {
      id: "LOOP_SHADOWING_POP",
      name: "For-Loop Local Iterator Shadowing and Scope Pop",
      fn1: { name: "loopTest1", params: ["i"], effect: "Pure", body: "for (let i = 0; i < 5; i++) { log(i); } return i;" },
      fn2: { name: "loopTest2", params: ["j"], effect: "Pure", body: "for (let j = 0; j < 5; j++) { log(j); } return j;" }
    },
    {
      id: "STRING_LITERAL_PROTECTION",
      name: "String Literal Preservation ('x' not renamed to $p0)",
      fn1: { name: "strTest1", params: ["x"], effect: "Pure", body: "const name = 'x'; return name + ': ' + x;" },
      fn2: { name: "strTest2", params: ["y"], effect: "Pure", body: "const name = 'x'; return name + ': ' + y;" }
    }
  ];

  let passed = 0;
  for (const c of cases) {
    const canon1 = RealAstAlphaCanonicalizer.canonicalize(c.fn1.params, c.fn1.body);
    const canon2 = RealAstAlphaCanonicalizer.canonicalize(c.fn2.params, c.fn2.body);
    const hash1 = RealAstAlphaCanonicalizer.computeSemanticHash(c.fn1);
    const hash2 = RealAstAlphaCanonicalizer.computeSemanticHash(c.fn2);

    const isMatch = (hash1 === hash2);
    if (isMatch) passed++;

    console.log(`[+] ${c.id}: ${c.name}`);
    console.log(`    - Canonical 1: ${canon1}`);
    console.log(`    - Canonical 2: ${canon2}`);
    console.log(`    - Hash Match: ${isMatch ? "YES (Alpha-Equivalent)" : "NO"}\n`);
  }

  const success = passed === cases.length;
  console.log(`>>> Real AST Scope-Tree Suite: ${passed}/${cases.length} Passed (${success ? "100.0% SUCCESS" : "FAIL"})\n`);
  return { passed, total: cases.length, success };
}
