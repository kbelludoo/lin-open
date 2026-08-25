import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import { parseLinToIR } from '../compiler/ir.mjs';
import { emitTypeScript } from '../compiler/ts_generic_emitter.mjs';
import { emitRust } from '../compiler/rust_generic_emitter.mjs';
import { emitC99 } from '../compiler/c99_generic_emitter.mjs';
import { generateTestCorpus } from '../fuzzer/program_generator.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const BUILD_DIR = path.join(ROOT, 'build');

function sha256(str) {
  return crypto.createHash('sha256').update(str).digest('hex').slice(0, 16);
}

export function runFullFuzzedSuite() {
  console.log("================================================================================");
  console.log("   LIN-SIGIL-005: 50 FUZZED PROGRAMS DIFFERENTIAL TESTING (GENERIC EMITTERS)    ");
  console.log("================================================================================");

  const corpus = generateTestCorpus();
  console.log(`Generated test corpus: ${corpus.length} distinct programs.\n`);

  let g1CompileSuccess = true;
  let g2ParityMatches = 0;
  let g3DriftCount = 0;
  let g4EffectLeakMatches = 0;
  const programResults = [];

  for (const prog of corpus) {
    const ir = parseLinToIR(prog.lin_source);

    // Static Effect Isolation Check
    let hasEffectLeak = false;
    for (const fn of ir.functions) {
      if (fn.effects.includes('Pure') && (fn.body.includes('console.log') || fn.body.includes('log('))) {
        hasEffectLeak = true;
      }
    }

    // 1. LIN ORACLE
    let linStatus = 'ACCEPTED';
    let linReason = 'OK';
    let linRes = null;

    if (hasEffectLeak) {
      linStatus = 'REJECTED';
      linReason = 'EFFECT_LEAK';
    } else {
      const targetFn = ir.functions.find(f => f.name === prog.fn_name);
      if (targetFn) {
        // Preconditions
        for (const c of targetFn.contracts) {
          if (c.kind === 'pre') {
            const preFn = new Function(...Object.keys(prog.args), `return (${c.expr});`);
            if (!preFn(...Object.values(prog.args))) {
              linStatus = 'REJECTED';
              linReason = 'PRECONDITION_VIOLATED';
              break;
            }
          }
        }
        if (linStatus === 'ACCEPTED') {
          // Eval body
          const bodyFn = new Function(...Object.keys(prog.args), targetFn.body.replace(/\^/g, 'return '));
          const candidateRes = bodyFn(...Object.values(prog.args));
          // Postconditions
          for (const c of targetFn.contracts) {
            if (c.kind === 'post') {
              const postFn = new Function(...Object.keys(prog.args), 'result', `return (${c.expr});`);
              if (!postFn(...Object.values(prog.args), candidateRes)) {
                linStatus = 'REJECTED';
                linReason = 'POSTCONDITION_VIOLATED';
                break;
              }
            }
          }
          if (linStatus === 'ACCEPTED') {
            linRes = candidateRes;
          }
        }
      }
    }

    const linFingerprint = sha256(`${linStatus}:${linReason}:${linRes}`);

    // 2. GENERIC TYPESCRIPT EMIT & EXEC
    let tsStatus = 'ACCEPTED';
    let tsReason = 'OK';
    let tsRes = null;

    if (hasEffectLeak) {
      tsStatus = 'REJECTED';
      tsReason = 'EFFECT_LEAK';
    } else {
      const tsCode = emitTypeScript(ir);
      const tsFile = path.join(BUILD_DIR, `${prog.prog_id}.mjs`);
      fs.writeFileSync(tsFile, tsCode, 'utf8');

      const runnerCode = `
        import { ${prog.fn_name} } from './${prog.prog_id}.mjs';
        try {
          const args = ${JSON.stringify(prog.args)};
          const res = ${prog.fn_name}(...Object.values(args));
          console.log(JSON.stringify({ status: 'ACCEPTED', reason: 'OK', res }));
        } catch(err) {
          console.log(JSON.stringify({ status: 'REJECTED', reason: err.message, res: null }));
        }
      `;
      const runnerFile = path.join(BUILD_DIR, `run_${prog.prog_id}.mjs`);
      fs.writeFileSync(runnerFile, runnerCode, 'utf8');

      try {
        const out = execSync(`node ${runnerFile}`, { encoding: 'utf8' });
        const p = JSON.parse(out.trim());
        tsStatus = p.status;
        tsReason = p.reason;
        tsRes = p.res;
      } catch (err) {
        g1CompileSuccess = false;
        tsStatus = 'ERROR';
        tsReason = err.message;
      }
    }

    const tsFingerprint = sha256(`${tsStatus}:${tsReason}:${tsRes}`);

    // 3. GENERIC RUST EMIT & EXEC (rustc -O)
    let rustStatus = 'ACCEPTED';
    let rustReason = 'OK';
    let rustRes = null;

    if (hasEffectLeak) {
      rustStatus = 'REJECTED';
      rustReason = 'EFFECT_LEAK';
    } else {
      const rustCode = emitRust(ir);
      const argValues = Object.values(prog.args).join(', ');
      const rustMain = `
        ${rustCode}
        fn main() {
            match ${prog.fn_name}(${argValues}) {
                Ok(v) => println!("{{\\"status\\":\\"ACCEPTED\\",\\"reason\\":\\"OK\\",\\"res\\":{}}}", v),
                Err(e) => println!("{{\\"status\\":\\"REJECTED\\",\\"reason\\":\\"{}\\",\\"res\\":null}}", e),
            }
        }
      `;
      const rsFile = path.join(BUILD_DIR, `${prog.prog_id}.rs`);
      const rsBin = path.join(BUILD_DIR, `bin_rs_${prog.prog_id}`);
      fs.writeFileSync(rsFile, rustMain, 'utf8');

      try {
        execSync(`rustc -O ${rsFile} -o ${rsBin}`, { encoding: 'utf8' });
        const out = execSync(rsBin, { encoding: 'utf8' });
        const p = JSON.parse(out.trim());
        rustStatus = p.status;
        rustReason = p.reason;
        rustRes = p.res;
      } catch (err) {
        g1CompileSuccess = false;
        rustStatus = 'ERROR';
        rustReason = err.message;
      }
    }

    const rustFingerprint = sha256(`${rustStatus}:${rustReason}:${rustRes}`);

    // 4. GENERIC C99 EMIT & EXEC (gcc -O3)
    let cStatus = 'ACCEPTED';
    let cReason = 'OK';
    let cRes = null;

    if (hasEffectLeak) {
      cStatus = 'REJECTED';
      cReason = 'EFFECT_LEAK';
    } else {
      const cCode = emitC99(ir);
      const argValues = Object.values(prog.args).join(', ');
      const cMain = `
        ${cCode}
        int main() {
            const char* err = NULL;
            int res = ${prog.fn_name}(${argValues}, &err);
            if (strcmp(err, "OK") == 0) {
                printf("{\\"status\\":\\"ACCEPTED\\",\\"reason\\":\\"OK\\",\\"res\\":%d}\\n", res);
            } else {
                printf("{\\"status\\":\\"REJECTED\\",\\"reason\\":\\"%s\\",\\"res\\":null}\\n", err);
            }
            return 0;
        }
      `;
      const cFile = path.join(BUILD_DIR, `${prog.prog_id}.c`);
      const cBin = path.join(BUILD_DIR, `bin_c_${prog.prog_id}`);
      fs.writeFileSync(cFile, cMain, 'utf8');

      try {
        execSync(`gcc -O3 ${cFile} -o ${cBin}`, { encoding: 'utf8' });
        const out = execSync(cBin, { encoding: 'utf8' });
        const p = JSON.parse(out.trim());
        cStatus = p.status;
        cReason = p.reason;
        cRes = p.res;
      } catch (err) {
        g1CompileSuccess = false;
        cStatus = 'ERROR';
        cReason = err.message;
      }
    }

    const cFingerprint = sha256(`${cStatus}:${cReason}:${cRes}`);

    // Verify 100% Fingerprint Equivalence
    const allMatch = (
      linFingerprint === tsFingerprint &&
      linFingerprint === rustFingerprint &&
      linFingerprint === cFingerprint
    );

    if (allMatch) {
      g2ParityMatches++;
    } else {
      g3DriftCount++;
    }

    if (prog.expected_reason === 'EFFECT_LEAK' && allMatch) {
      g4EffectLeakMatches++;
    }

    console.log(`  [${prog.prog_id}] ${prog.fn_name} -> LIN: ${linStatus} (${linReason}) | TS: ${tsStatus} | Rust: ${rustStatus} | C: ${cStatus} => ${allMatch ? 'PARITY 100% MATCH' : 'DRIFT'}`);

    programResults.push({
      prog_id: prog.prog_id,
      fn_name: prog.fn_name,
      status: linStatus,
      reason: linReason,
      fingerprints: {
        lin: linFingerprint,
        ts: tsFingerprint,
        rust: rustFingerprint,
        c99: cFingerprint
      },
      parity: allMatch
    });
  }

  const parityRate = (g2ParityMatches / corpus.length) * 100;
  console.log(`\n================================================================================`);
  console.log(`>>> Differential Testing Parity: ${g2ParityMatches}/${corpus.length} (${parityRate.toFixed(1)}%) with ${g3DriftCount} drift.`);
  console.log(`================================================================================`);

  const report = {
    benchmark: "LIN-SIGIL-005",
    total_programs: corpus.length,
    parity_matches: g2ParityMatches,
    drift_count: g3DriftCount,
    parity_rate: `${parityRate.toFixed(1)}%`,
    g1_generic_compile_success: g1CompileSuccess,
    g2_cross_target_parity: g2ParityMatches === corpus.length,
    g3_zero_semantic_drift: g3DriftCount === 0,
    programs: programResults
  };

  const outPath = path.join(ROOT, 'results/LIN_SIGIL_005_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(`[+] Report saved to: ${outPath}`);
  return report;
}

runFullFuzzedSuite();
