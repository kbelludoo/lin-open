// True AST Scope, Closure, and Operator Canonicalization Verification Suite
import { TrueAstAlphaCanonicalizer } from '../runtime/true_ast_alpha_canonicalizer.mjs';

export function runTrueAstCanonicalizationSuite() {
  console.log("================================================================================");
  console.log("   TRUE AST RECURSIVE CLOSURE & SCOPE ALPHA-CANONICALIZATION TEST SUITE        ");
  console.log("================================================================================");

  const cases = [
    {
      id: "CLOSURE_NESTED_FUNCTIONS",
      name: "Nested Higher-Order Function Closure with Captured Outer Bindings",
      src1: `function outer(x) { return function inner(y) { return x + y; }; }`,
      src2: `function outer(a) { return function inner(b) { return a + b; }; }`
    },
    {
      id: "STRICT_EQUALITY_OPERATORS",
      name: "3-Character Strict Operators (=== and !==) Parsing & Canonicalization",
      src1: `function compareStrict(a, b) { if (a === b) return true; if (a !== b) return false; return false; }`,
      src2: `function compareStrict(x, y) { if (x === y) return true; if (x !== y) return false; return false; }`
    },
    {
      id: "VAR_FUNCTION_SCOPE_HOISTING",
      name: "Function-Scoped var Hoisting from Nested Block to Outer Scope",
      src1: `function testVar(flag) { if (flag) { var result = 42; } return result; }`,
      src2: `function testVar(cond) { if (cond) { var output = 42; } return output; }`
    },
    {
      id: "FOR_WITHOUT_BLOCK",
      name: "Single-Statement For Loop (No Braces) with Immediate Scope Pop",
      src1: `function f(x) { for (let i = 0; i < 5; i++) doWork(i); return x; }`,
      src2: `function f(y) { for (let j = 0; j < 5; j++) doWork(j); return y; }`
    },
    {
      id: "TRY_CATCH_ERROR_POP",
      name: "Catch Clause Binding Pop & Outer Parameter Restoration",
      src1: `function f(err) { try { run(); } catch (err) { log(err); } return err; }`,
      src2: `function f(e) { try { run(); } catch (e) { log(e); } return e; }`
    },
    {
      id: "OBJECT_LITERAL_KEYS",
      name: "Object Expression Key Preservation ({ x: value })",
      src1: `function f(x) { return { x: x, label: "test" }; }`,
      src2: `function f(y) { return { x: y, label: "test" }; }`
    }
  ];

  let passed = 0;
  for (const c of cases) {
    const hash1 = TrueAstAlphaCanonicalizer.computeCanonicalHash(c.src1);
    const hash2 = TrueAstAlphaCanonicalizer.computeCanonicalHash(c.src2);
    const isMatch = (hash1 === hash2);
    if (isMatch) passed++;

    console.log(`[+] ${c.id}: ${c.name}`);
    console.log(`    - Canonical Hash 1: ${hash1}`);
    console.log(`    - Canonical Hash 2: ${hash2}`);
    console.log(`    - True AST Equivalence Match: ${isMatch ? "YES (Identical Canonical AST Tree)" : "NO"}\n`);
  }

  const success = passed === cases.length;
  console.log(`>>> True AST Closure & Scope Suite: ${passed}/${cases.length} Passed (${success ? "100.0% SUCCESS" : "FAIL"})\n`);
  return { passed, total: cases.length, success };
}
