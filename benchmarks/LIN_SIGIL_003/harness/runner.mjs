import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { LinSemanticVerifier } from './verifier.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

function stripSigilWrapper(line) {
  let s = line.substring(1).trim();
  if (s.startsWith('(') && s.endsWith(')')) {
    s = s.slice(1, -1).trim();
  }
  return s;
}

function parseLinWithContracts(src) {
  const lines = src.split('\n');
  const functions = [];
  const schemaInvariants = [];
  let currentFn = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('~')) {
      // schema declaration
    } else if (line.startsWith('%') && !currentFn) {
      schemaInvariants.push(stripSigilWrapper(line));
    } else if (line.startsWith('!')) {
      const openParen = line.indexOf('(');
      const closeParen = line.indexOf(')');
      if (openParen > 1 && closeParen > openParen) {
        const name = line.substring(1, openParen).trim();
        const params = line.substring(openParen + 1, closeParen).split(',').map(p => p.trim().split(':')[0].trim()).filter(Boolean);
        currentFn = { name, params, contracts: [], effects: ['pure'], body: '' };
        functions.push(currentFn);
      }
    } else if (line.startsWith('%') && currentFn) {
      currentFn.contracts.push(stripSigilWrapper(line));
    } else if (line.startsWith('*') && currentFn) {
      currentFn.effects = [stripSigilWrapper(line)];
    } else if (currentFn && line.startsWith('{')) {
      let bodyLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('}')) {
        bodyLines.push(lines[i]);
        i++;
      }
      currentFn.body = bodyLines.join('\n').replace(/\^/g, 'return ');
      currentFn = null;
    }
  }

  return { functions, schemaInvariants };
}

export function runSemanticSuite() {
  console.log("================================================================================");
  console.log("    LIN-SIGIL-003: SEMANTIC EXECUTION & CONTRACT/EFFECT VERIFICATION            ");
  console.log("================================================================================");

  const verifier = new LinSemanticVerifier();
  const casesDir = path.join(ROOT, 'cases');

  const caseSpecs = [
    { file: "01_pure_contract_pass.lin", fnName: "divide", args: { a: 10, b: 2 }, expectedStatus: "ACCEPTED" },
    { file: "02_precondition_fail.lin", fnName: "divide", args: { a: 10, b: 0 }, expectedStatus: "REJECTED", expectedReason: "PRECONDITION_VIOLATED" },
    { file: "03_postcondition_fail.lin", fnName: "divide", args: { a: 10, b: 2 }, expectedStatus: "REJECTED", expectedReason: "POSTCONDITION_VIOLATED" },
    { file: "04_effect_leak_fail.lin", fnName: "compute", args: { x: 5 }, expectedStatus: "REJECTED", expectedReason: "EFFECT_LEAK" },
    { file: "05_invariant_struct_pass.lin", fnName: "push", args: { self: { size: 0, capacity: 5, items: [] }, item: 42 }, expectedStatus: "ACCEPTED" },
    { file: "06_invariant_violation_fail.lin", fnName: "corruptPush", args: { self: { size: 0, capacity: 5, items: [] }, item: 42 }, expectedStatus: "REJECTED", expectedReason: "INVARIANT_VIOLATED" }
  ];

  const results = [];
  let passedCount = 0;

  for (const spec of caseSpecs) {
    const src = fs.readFileSync(path.join(casesDir, spec.file), 'utf8');
    const ast = parseLinWithContracts(src);
    verifier.registerSignatures(ast);

    // 1. Static Effect Isolation Check
    const effectCheck = verifier.verifyEffectIsolation(ast);

    let finalStatus = 'ACCEPTED';
    let finalReason = 'OK';
    let resultValue = null;

    if (!effectCheck.valid) {
      finalStatus = 'REJECTED';
      finalReason = 'EFFECT_LEAK';
    } else {
      // 2. Contract Evaluation Check
      const targetFn = ast.functions.find(f => f.name === spec.fnName);
      if (targetFn) {
        const evalRes = verifier.verifyContractExecution({
          fnName: targetFn.name,
          args: spec.args,
          fnBody: targetFn.body,
          contracts: targetFn.contracts,
          schemaInvariants: ast.schemaInvariants
        });
        finalStatus = evalRes.status;
        finalReason = evalRes.reason || 'OK';
        resultValue = evalRes.result;
      }
    }

    const matchedExpected = finalStatus === spec.expectedStatus && (!spec.expectedReason || finalReason === spec.expectedReason);
    if (matchedExpected) passedCount++;

    console.log(`  [Case ${spec.file}] Result: ${finalStatus} (${finalReason}) | Expected: ${spec.expectedStatus} -> ${matchedExpected ? 'PASS' : 'FAIL'}`);

    results.push({
      case: spec.file,
      fnName: spec.fnName,
      status: finalStatus,
      reason: finalReason,
      expectedStatus: spec.expectedStatus,
      expectedReason: spec.expectedReason,
      matched: matchedExpected,
      resultValue
    });
  }

  const successRate = (passedCount / caseSpecs.length) * 100;
  console.log(`\nSemantic Gate: ${passedCount}/${caseSpecs.length} test vectors accurately enforced (${successRate.toFixed(1)}%).`);

  const summary = {
    total_vectors: caseSpecs.length,
    passed_vectors: passedCount,
    success_rate: `${successRate.toFixed(1)}%`,
    cases: results
  };

  const outPath = path.join(ROOT, 'results/LIN_SIGIL_003_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(summary, null, 2));
  console.log(`[+] Results written to: ${outPath}`);
  return summary;
}

runSemanticSuite();
