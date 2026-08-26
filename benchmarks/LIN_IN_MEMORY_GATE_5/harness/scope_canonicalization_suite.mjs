// Scope-Stack Alpha-Canonicalization Verification Suite
import { AstAlphaScopeStack } from '../runtime/ast_alpha_scope_stack.mjs';

export function runScopeCanonicalizationSuite() {
  console.log("================================================================================");
  console.log("   SCOPE-STACK AST ALPHA-CANONICALIZATION TEST SUITE                           ");
  console.log("================================================================================");

  const cases = [
    {
      id: "CASE_01_BLOCK_SHADOWING",
      name: "Nested Block Shadowing with Scope Restoration",
      fn1: { name: "test1", params: ["x"], effect: "Pure", body: "if (true) { let x = 10; console.log(x); } return x;" },
      fn2: { name: "test2", params: ["y"], effect: "Pure", body: "if (true) { let y = 10; console.log(y); } return y;" }
    },
    {
      id: "CASE_02_LOOP_SHADOWING",
      name: "For-Loop Lexical Variable Shadowing",
      fn1: { name: "loop1", params: ["i"], effect: "Pure", body: "for (let i = 0; i < 5; i++) { doWork(i); } return i;" },
      fn2: { name: "loop2", params: ["j"], effect: "Pure", body: "for (let j = 0; j < 5; j++) { doWork(j); } return j;" }
    },
    {
      id: "CASE_03_TRY_CATCH_SHADOWING",
      name: "Catch-Clause Error Binding Shadowing",
      fn1: { name: "catch1", params: ["err"], effect: "Pure", body: "try { run(); } catch (err) { log(err); } return err;" },
      fn2: { name: "catch2", params: ["e"], effect: "Pure", body: "try { run(); } catch (e) { log(e); } return e;" }
    },
    {
      id: "CASE_04_STRING_LITERAL_ISOLATION",
      name: "String Literal Preservation against Renaming",
      fn1: { name: "str1", params: ["val"], effect: "Pure", body: "const name = 'val'; return name + ': ' + val;" },
      fn2: { name: "str2", params: ["other"], effect: "Pure", body: "const name = 'val'; return name + ': ' + other;" }
    }
  ];

  let passed = 0;
  for (const c of cases) {
    const hash1 = AstAlphaScopeStack.computeSemanticHash(c.fn1);
    const hash2 = AstAlphaScopeStack.computeSemanticHash(c.fn2);
    const canon1 = AstAlphaScopeStack.canonicalize(c.fn1.params, c.fn1.body);
    const canon2 = AstAlphaScopeStack.canonicalize(c.fn2.params, c.fn2.body);

    const isMatch = (hash1 === hash2);
    if (isMatch) passed++;

    console.log(`[+] ${c.id}: ${c.name}`);
    console.log(`    - Canonical AST 1: ${canon1}`);
    console.log(`    - Canonical AST 2: ${canon2}`);
    console.log(`    - Hash 1: ${hash1}`);
    console.log(`    - Hash 2: ${hash2}`);
    console.log(`    - Match: ${isMatch ? "YES (Alpha-Equivalent)" : "NO"}\n`);
  }

  const success = passed === cases.length;
  console.log(`>>> Scope-Stack Alpha-Canonicalization: ${passed}/${cases.length} Passed (${success ? "100.0% SUCCESS" : "FAIL"})\n`);
  return { passed, total: cases.length, success };
}
