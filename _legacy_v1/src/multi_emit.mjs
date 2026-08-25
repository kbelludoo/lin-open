/**
 * LIA multi-target compile dispatcher.
 * Default target = ts (LIN defaultEmitTarget). Stub langs are not PASS.
 */
import fs from 'node:fs';
import { parseLia } from './compiler.mjs';
import { assertDivProof } from './lin_refine_div_load.mjs';
import { runFormalGate } from './formal_gate.mjs';
import { emitJs } from './emit_js.mjs';
import { emitTs } from './emit_ts.mjs';
import { emitPy } from './emit_py.mjs';
import { emitGo } from './emit_go.mjs';
import { emitRust } from './emit_rust.mjs';
import { emitC } from './emit_c.mjs';
import { emitJava } from './emit_java.mjs';
import { TARGETS, DEFAULT_EMIT_TARGET, defaultOutPath, STUB_TARGETS, REAL_TARGETS } from './emit_shared.mjs';

export { TARGETS, DEFAULT_EMIT_TARGET, defaultOutPath, REAL_TARGETS };

export function compileLia(liaText, opts = {}) {
  const target = String(opts.target || DEFAULT_EMIT_TARGET).toLowerCase();
  if (STUB_TARGETS.includes(target)) {
    throw new Error(`experimental_not_PASS:${target}; real=${REAL_TARGETS.join('|')}; default=${DEFAULT_EMIT_TARGET}`);
  }
  if (!REAL_TARGETS.includes(target)) {
    throw new Error(`LIA_EMIT_TARGET: unsupported ${target}; want ${REAL_TARGETS.join('|')} (default ${DEFAULT_EMIT_TARGET})`);
  }
  if (opts.skipRefineProof !== true) {
    assertDivProof(liaText, parseLia(liaText));
  }
  // M006-A Formal Semantic Gate: verify invariants BEFORE any lowering/emission.
  let formalReport = null;
  if (opts.formalGate !== false) {
    formalReport = runFormalGate(parseLia(liaText), { strict: opts.formalStrict === true });
  }
  let result;
  if (target === 'ts') result = emitTs(liaText, opts);
  else if (target === 'js') result = emitJs(liaText, opts);
  else if (target === 'py') result = emitPy(liaText, opts);
  else if (target === 'go') result = emitGo(liaText, opts);
  else if (target === 'c') result = emitC(liaText, opts);
  else if (target === 'java') result = emitJava(liaText, opts);
  else result = emitRust(liaText, opts);
  if (formalReport) result = { ...result, formalReport };
  return result;
}

export function compileLiaToTargetFile(liaPath, outPath = null, opts = {}) {
  const target = String(opts.target || DEFAULT_EMIT_TARGET).toLowerCase();
  const lia = fs.readFileSync(liaPath, 'utf8');
  const result = compileLia(lia, { ...opts, target });
  const dest = outPath || defaultOutPath(liaPath, target);
  fs.writeFileSync(dest, result.code, 'utf8');
  return { outPath: dest, ...result };
}
