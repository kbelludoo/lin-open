import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import { emitTypeScript } from '../emitters/ts_emitter.mjs';
import { emitRust } from '../emitters/rust_emitter.mjs';
import { emitC99 } from '../emitters/c99_emitter.mjs';
import { LinSemanticVerifier } from '../../LIN_SIGIL_003/harness/verifier.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const CASES_DIR = path.resolve(ROOT, '../LIN_SIGIL_003/cases');
const BUILD_DIR = path.join(ROOT, 'build');

function stripSigilWrapper(line) {
  let s = line.substring(1).trim();
  if (s.startsWith('(') && s.endsWith(')')) s = s.slice(1, -1).trim();
  return s;
}

function parseLin(src) {
  const lines = src.split('\n');
  const functions = [];
  const schemaInvariants = [];
  let currentFn = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('~')) {
      // schema
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

export function runMultiTargetTrial() {
  console.log("================================================================================");
  console.log("   LIN-SIGIL-004: MULTI-TARGET COMPILATION & CROSS-BACKEND EQUIVALENCE         ");
  console.log("================================================================================");

  const verifier = new LinSemanticVerifier();
  const caseSpecs = [
    { id: "case_01", file: "01_pure_contract_pass.lin", fnName: "divide", args: { a: 10, b: 2 }, expectedStatus: "ACCEPTED", expectedReason: "OK" },
    { id: "case_02", file: "02_precondition_fail.lin", fnName: "divide", args: { a: 10, b: 0 }, expectedStatus: "REJECTED", expectedReason: "PRECONDITION_VIOLATED" },
    { id: "case_03", file: "03_postcondition_fail.lin", fnName: "divide", args: { a: 10, b: 2 }, expectedStatus: "REJECTED", expectedReason: "POSTCONDITION_VIOLATED" },
    { id: "case_04", file: "04_effect_leak_fail.lin", fnName: "compute", args: { x: 5 }, expectedStatus: "REJECTED", expectedReason: "EFFECT_LEAK" },
    { id: "case_05", file: "05_invariant_struct_pass.lin", fnName: "push", args: { self: { size: 0, capacity: 5, items: [] }, item: 42 }, expectedStatus: "ACCEPTED", expectedReason: "OK" },
    { id: "case_06", file: "06_invariant_violation_fail.lin", fnName: "corruptPush", args: { self: { size: 0, capacity: 5, items: [] }, item: 42 }, expectedStatus: "REJECTED", expectedReason: "INVARIANT_VIOLATED" }
  ];

  const results = [];
  let g1CompileSuccess = true;
  let g2ValidAccepted = true;
  let g3InvalidRejected = true;
  let g4EffectLeakRejected = true;
  let g5CrossTargetEq = true;
  let g6FalseAcceptance = 0;
  let g7FalseRejection = 0;
  let g8SemanticDrift = 0;
  let g9RustReleaseCorrectness = true;
  let g10RustDebugReleaseEquivalence = true;

  for (const spec of caseSpecs) {
    const src = fs.readFileSync(path.join(CASES_DIR, spec.file), 'utf8');
    const ast = parseLin(src);
    verifier.registerSignatures(ast);

    // Static Effect Check in LIN
    const effectCheck = verifier.verifyEffectIsolation(ast);
    const hasStaticEffectLeak = !effectCheck.valid;

    // --- 1. TYPESCRIPT EMIT & EXECUTE ---
    let tsStatus = 'ACCEPTED';
    let tsReason = 'OK';
    if (hasStaticEffectLeak) {
      tsStatus = 'REJECTED';
      tsReason = 'EFFECT_LEAK';
    } else {
      const tsCode = emitTypeScript(ast);
      const tsFile = path.join(BUILD_DIR, `${spec.id}.mjs`);
      fs.writeFileSync(tsFile, tsCode, 'utf8');
      try {
        const evalTs = `
          import { ${spec.fnName} } from './${spec.id}.mjs';
          try {
            const args = ${JSON.stringify(spec.args)};
            let res;
            if (args.self) {
              res = ${spec.fnName}(args.self, args.item);
            } else {
              res = ${spec.fnName}(args.a, args.b);
            }
            console.log(JSON.stringify({ status: 'ACCEPTED', reason: 'OK', res }));
          } catch(err) {
            console.log(JSON.stringify({ status: 'REJECTED', reason: err.message }));
          }
        `;
        const runnerFile = path.join(BUILD_DIR, `run_${spec.id}.mjs`);
        fs.writeFileSync(runnerFile, evalTs, 'utf8');
        const out = execSync(`node ${runnerFile}`, { encoding: 'utf8' });
        const parsed = JSON.parse(out.trim());
        tsStatus = parsed.status;
        tsReason = parsed.reason;
      } catch (err) {
        g1CompileSuccess = false;
        tsStatus = 'ERROR';
        tsReason = err.message;
      }
    }

    // --- 2. RUST EMIT, COMPILE & EXECUTE (Debug & Release-Safe) ---
    let rustDebugStatus = 'ACCEPTED';
    let rustDebugReason = 'OK';
    let rustReleaseStatus = 'ACCEPTED';
    let rustReleaseReason = 'OK';

    if (hasStaticEffectLeak) {
      rustDebugStatus = 'REJECTED'; rustDebugReason = 'EFFECT_LEAK';
      rustReleaseStatus = 'REJECTED'; rustReleaseReason = 'EFFECT_LEAK';
    } else {
      const rustCode = emitRust(ast, 'release_safe');
      const rustMain = `
        ${rustCode}
        fn main() {
            ${spec.args.self ? `
            let mut buf = Buffer { size: ${spec.args.self.size}, capacity: ${spec.args.self.capacity}, items: vec![] };
            match ${spec.fnName}(&mut buf, ${spec.args.item}) {
                Ok(v) => println!("{{\\"status\\":\\"ACCEPTED\\",\\"reason\\":\\"OK\\",\\"res\\":{}}}", v),
                Err(e) => println!("{{\\"status\\":\\"REJECTED\\",\\"reason\\":\\"{}\\"}}", e),
            }
            ` : `
            match ${spec.fnName}(${spec.args.a}, ${spec.args.b}) {
                Ok(v) => println!("{{\\"status\\":\\"ACCEPTED\\",\\"reason\\":\\"OK\\",\\"res\\":{}}}", v),
                Err(e) => println!("{{\\"status\\":\\"REJECTED\\",\\"reason\\":\\"{}\\"}}", e),
            }
            `}
        }
      `;
      const rsFile = path.join(BUILD_DIR, `${spec.id}.rs`);
      fs.writeFileSync(rsFile, rustMain, 'utf8');

      // Compile Debug & Release
      const binDebug = path.join(BUILD_DIR, `rust_dbg_${spec.id}`);
      const binRelease = path.join(BUILD_DIR, `rust_rel_${spec.id}`);
      try {
        execSync(`rustc ${rsFile} -o ${binDebug}`, { encoding: 'utf8' });
        execSync(`rustc -O ${rsFile} -o ${binRelease}`, { encoding: 'utf8' });

        const outDbg = execSync(binDebug, { encoding: 'utf8' });
        const pDbg = JSON.parse(outDbg.trim());
        rustDebugStatus = pDbg.status;
        rustDebugReason = pDbg.reason;

        const outRel = execSync(binRelease, { encoding: 'utf8' });
        const pRel = JSON.parse(outRel.trim());
        rustReleaseStatus = pRel.status;
        rustReleaseReason = pRel.reason;
      } catch (err) {
        g1CompileSuccess = false;
        rustDebugStatus = 'ERROR';
        rustReleaseStatus = 'ERROR';
      }
    }

    // --- 3. C99 EMIT, COMPILE & EXECUTE ---
    let cStatus = 'ACCEPTED';
    let cReason = 'OK';
    if (hasStaticEffectLeak) {
      cStatus = 'REJECTED';
      cReason = 'EFFECT_LEAK';
    } else {
      const cCode = emitC99(ast);
      const cMain = `
        ${cCode}
        int main() {
            const char* err = NULL;
            ${spec.args.self ? `
            Buffer buf;
            buf.size = ${spec.args.self.size};
            buf.capacity = ${spec.args.self.capacity};
            int res = ${spec.fnName}(&buf, ${spec.args.item}, &err);
            if (strcmp(err, "OK") == 0) {
                printf("{\\"status\\":\\"ACCEPTED\\",\\"reason\\":\\"OK\\",\\"res\\":%d}\\n", res);
            } else {
                printf("{\\"status\\":\\"REJECTED\\",\\"reason\\":\\"%s\\"}\\n", err);
            }
            ` : `
            int res = ${spec.fnName}(${spec.args.a}, ${spec.args.b}, &err);
            if (strcmp(err, "OK") == 0) {
                printf("{\\"status\\":\\"ACCEPTED\\",\\"reason\\":\\"OK\\",\\"res\\":%d}\\n", res);
            } else {
                printf("{\\"status\\":\\"REJECTED\\",\\"reason\\":\\"%s\\"}\\n", err);
            }
            `}
            return 0;
        }
      `;
      const cFile = path.join(BUILD_DIR, `${spec.id}.c`);
      const cBin = path.join(BUILD_DIR, `c99_${spec.id}`);
      fs.writeFileSync(cFile, cMain, 'utf8');
      try {
        execSync(`gcc -O3 ${cFile} -o ${cBin}`, { encoding: 'utf8' });
        const outC = execSync(cBin, { encoding: 'utf8' });
        const pC = JSON.parse(outC.trim());
        cStatus = pC.status;
        cReason = pC.reason;
      } catch (err) {
        g1CompileSuccess = false;
        cStatus = 'ERROR';
      }
    }

    // --- EVALUATE EQUIVALENCE & GATES ---
    const allMatchExpected = (
      tsStatus === spec.expectedStatus && tsReason === spec.expectedReason &&
      rustDebugStatus === spec.expectedStatus && rustDebugReason === spec.expectedReason &&
      rustReleaseStatus === spec.expectedStatus && rustReleaseReason === spec.expectedReason &&
      cStatus === spec.expectedStatus && cReason === spec.expectedReason
    );

    if (spec.expectedStatus === 'ACCEPTED' && !allMatchExpected) {
      g2ValidAccepted = false;
      g7FalseRejection++;
    }
    if (spec.expectedStatus === 'REJECTED' && !allMatchExpected) {
      g3InvalidRejected = false;
      g6FalseAcceptance++;
    }
    if (spec.expectedReason === 'EFFECT_LEAK' && (tsReason !== 'EFFECT_LEAK' || rustReleaseReason !== 'EFFECT_LEAK' || cReason !== 'EFFECT_LEAK')) {
      g4EffectLeakRejected = false;
    }
    if (rustDebugReason !== rustReleaseReason) {
      g10RustDebugReleaseEquivalence = false;
    }
    if (rustReleaseStatus !== spec.expectedStatus || rustReleaseReason !== spec.expectedReason) {
      g9RustReleaseCorrectness = false;
    }
    if (!allMatchExpected) {
      g5CrossTargetEq = false;
      g8SemanticDrift++;
    }

    console.log(`  [Case ${spec.file}] Expected: ${spec.expectedStatus} (${spec.expectedReason})`);
    console.log(`    -> TS:   ${tsStatus} (${tsReason})`);
    console.log(`    -> Rust: ${rustReleaseStatus} (${rustReleaseReason}) [Release-Safe]`);
    console.log(`    -> C99:  ${cStatus} (${cReason})`);
    console.log(`    -> Parity: ${allMatchExpected ? '100% MATCH' : 'DIVERGENCE'}\n`);

    results.push({
      case: spec.file,
      expected: { status: spec.expectedStatus, reason: spec.expectedReason },
      targets: {
        typescript: { status: tsStatus, reason: tsReason },
        rust_debug: { status: rustDebugStatus, reason: rustDebugReason },
        rust_release: { status: rustReleaseStatus, reason: rustReleaseReason },
        c99_native: { status: cStatus, reason: cReason }
      },
      parity: allMatchExpected
    });
  }

  const report = {
    benchmark: "LIN-SIGIL-004",
    gates: {
      G1_compile_success: g1CompileSuccess,
      G2_valid_programs_accepted: g2ValidAccepted,
      G3_invalid_contracts_rejected: g3InvalidRejected,
      G4_effect_violations_rejected: g4EffectLeakRejected,
      G5_cross_target_equivalence: g5CrossTargetEq,
      G6_false_acceptance_count: g6FalseAcceptance,
      G7_false_rejection_count: g7FalseRejection,
      G8_semantic_drift_count: g8SemanticDrift,
      G9_rust_release_correctness: g9RustReleaseCorrectness,
      G10_rust_debug_release_equivalence: g10RustDebugReleaseEquivalence
    },
    cases: results
  };

  const outPath = path.join(ROOT, 'results/LIN_SIGIL_004_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(`[+] Full Trial Complete! Report saved to ${outPath}`);
  return report;
}

runMultiTargetTrial();
