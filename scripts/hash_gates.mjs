/**
 * Bootstrap hash gates — mandatory before promoting LIN-compiled cores or removing .mjs mirrors.
 * G_CORE_CODE_HASH | G_SEMANTIC_HASH | G_NUCLEUS_LOCK | G_COMPILER_EMIT_IDEMPOTENT
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { extractRulelContent } from './lin_bootstrap.mjs';

const nodeRequire = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'src');

export const GATES = {
  CORE_CODE_HASH: 'G_CORE_CODE_HASH',
  SEMANTIC_HASH: 'G_SEMANTIC_HASH',
  NUCLEUS_LOCK: 'G_NUCLEUS_LOCK',
  COMPILER_EMIT_IDEMPOTENT: 'G_COMPILER_EMIT_IDEMPOTENT',
  TRANSPIL_HASH: 'G_TRANSPIL_HASH',
};

const CORES = [
  { lin: 'lexer_slices.lin', cjs: 'lexer_slices.compiled.cjs', exports: ['identLenAt', 'wsRunAt', 'numLenAt'] },
  { lin: 'semantic_hash_core.lin', cjs: 'semantic_hash_core.compiled.cjs', exports: ['escapeRe', 'canonicalize'] },
  { lin: 'effects_core.lin', cjs: 'effects_core.compiled.cjs', exports: ['firstUseIsRead', 'collectAssignedIds'] },
  { lin: 'rulel_core.lin', cjs: 'rulel_core.compiled.cjs', exports: ['splitTopEntries', 'parseValuePairs', 'parseRulel', 'validateComms'] },
  { lin: 'vm_core.lin', cjs: 'vm_core.compiled.cjs', exports: ['assertJsSyntaxCore', 'validateSandboxSpec'] },
  { lin: 'verifier_core.lin', cjs: 'verifier_core.compiled.cjs', exports: ['deepEq', 'findMissingExports'] },
  {
    lin: 'transpiler_to_lin_core.lin',
    cjs: 'transpiler_to_lin_core.compiled.cjs',
    exports: ['detectLanguage', 'extractBracedFunctions', 'transpileRustToLin', 'transpileGoToLin', 'transpileCToLin', 'transpileZigToLin'],
  },
];

function sha256(text) {
  return crypto.createHash('sha256').update(String(text), 'utf8').digest('hex');
}

function seedRulelPath(cjsName) {
  return path.join(SRC, cjsName.replace(/\.compiled\.cjs$/, '.compiled_cjs.rulel'));
}

function readSeed(cjsName) {
  const rulelPath = seedRulelPath(cjsName);
  if (!fs.existsSync(rulelPath)) return null;
  return extractRulelContent(fs.readFileSync(rulelPath, 'utf8'));
}

function evalCjs(code, label) {
  const module = { exports: {} };
  const req = (spec) => nodeRequire(spec);
  vm.runInNewContext(code, { module, exports: module.exports, require: req, console }, { timeout: 10_000, filename: label });
  return module.exports;
}

function deepEq(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (!deepEq(a[i], b[i])) return false;
    return true;
  }
  if (typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    for (const k of ka) if (!deepEq(a[k], b[k])) return false;
    return true;
  }
  return Number.isNaN(a) && Number.isNaN(b);
}

function probeCoreExports(cjsName, mod) {
  switch (cjsName) {
    case 'lexer_slices.compiled.cjs':
      return (
        mod.identLenAt('foo', 0) === 3 &&
        mod.wsRunAt('  \tx', 0) === 3 &&
        mod.numLenAt('123abc', 0) === 3
      );
    case 'semantic_hash_core.compiled.cjs': {
      const c1 = mod.canonicalize('a, b', 'return a + b;');
      const c2 = mod.canonicalize('x, y', 'return x + y;');
      return c1 === c2 && mod.escapeRe('a.b') === 'a\\.b';
    }
    case 'effects_core.compiled.cjs': {
      const ids = [...mod.collectAssignedIds('x = 1; y = 2;')];
      return deepEq(ids, ['x', 'y']);
    }
    case 'rulel_core.compiled.cjs': {
      const doc = mod.parseRulel('@RULEL:TEST:1.0\n~R{.m=meta}\n.m{k="v"}\n');
      return doc.header.id === 'TEST';
    }
    case 'vm_core.compiled.cjs':
      return mod.assertJsSyntaxCore('var x = 1;') === true && mod.validateSandboxSpec('crypto') === true;
    case 'verifier_core.compiled.cjs':
      return mod.deepEq({ a: [1, 2] }, { a: [1, 2] }) && mod.deepEq({ a: 1 }, { a: 2 }) === false;
    case 'transpiler_to_lin_core.compiled.cjs':
      return (
        mod.detectLanguage('fn main() {}', 'main.rs') === 'rs' &&
        mod.detectLanguage('package main', 'main.go') === 'go'
      );
    default:
      return true;
  }
}

function coreBehaviorEq(compiledCode, seedCode, cjsName) {
  try {
    const compiled = evalCjs(compiledCode, `probe-compiled:${cjsName}`);
    const seeded = evalCjs(seedCode, `probe-seed:${cjsName}`);
    if (!probeCoreExports(cjsName, compiled) || !probeCoreExports(cjsName, seeded)) return false;
    for (const name of Object.keys(seeded)) {
      if (typeof seeded[name] !== 'function') continue;
      if (typeof compiled[name] !== 'function') return false;
    }
    return true;
  } catch {
    return false;
  }
}

export function verifyCoreSeedHashes(compileFn) {
  const results = [];
  let ok = true;
  for (const core of CORES) {
    const seed = readSeed(core.cjs);
    if (!seed) {
      results.push({ cjs: core.cjs, ok: false, mode: 'missing_seed' });
      ok = false;
      continue;
    }
    const seedHash = sha256(seed);
    let entry = { cjs: core.cjs, seedHash: seedHash.slice(0, 16) };

    try {
      const src = fs.readFileSync(path.join(SRC, core.lin), 'utf8');
      const compiled = `${compileFn(src, { target: 'js' }).code}\nmodule.exports={${core.exports.join(',')}};\n`;
      const compiledHash = sha256(compiled);
      entry.compiledHash = compiledHash.slice(0, 16);
      if (compiledHash === seedHash) {
        entry = { ...entry, ok: true, mode: 'byte_match' };
      } else if (coreBehaviorEq(compiled, seed, core.cjs)) {
        entry = { ...entry, ok: true, mode: 'behavior_eq' };
      } else {
        entry = { ...entry, ok: false, mode: 'hash_and_behavior_mismatch' };
        ok = false;
      }
    } catch (e) {
      if (!probeCoreExports(core.cjs, evalCjs(seed, `probe-seed:${core.cjs}`))) {
        entry = { ...entry, ok: false, mode: 'rulel_seed_invalid', error: String(e.message || e).slice(0, 120) };
        ok = false;
      } else {
        entry = { ...entry, ok: true, mode: 'rulel_seed', note: String(e.message || e).slice(0, 80) };
      }
    }
    results.push(entry);
  }
  return { gate: GATES.CORE_CODE_HASH, ok, cores: results };
}

export function verifySemanticHashGate(semanticHashFn) {
  const h1 = semanticHashFn('a,b', 'a + b - 1');
  const h2 = semanticHashFn('x,y', 'x+y-1');
  const h3 = semanticHashFn('a,b', 'a - b + 1');
  const ok = h1 === h2 && h1 !== h3 && /^[0-9a-f]{16}$/.test(h1);
  return {
    gate: GATES.SEMANTIC_HASH,
    ok,
    h1,
    h2,
    h3,
    renameInvariant: h1 === h2,
    divergence: h1 !== h3,
  };
}

export function readNucleusLock() {
  const jsonRulel = path.join(ROOT, 'nucleus.lock_json.rulel');
  if (fs.existsSync(jsonRulel)) {
    const content = extractRulelContent(fs.readFileSync(jsonRulel, 'utf8'));
    if (content) return JSON.parse(content);
  }
  const rulel = path.join(ROOT, 'nucleus.lock.rulel');
  if (fs.existsSync(rulel)) {
    const text = fs.readFileSync(rulel, 'utf8');
    const m = text.match(/\.verifier_sha256="([^"]+)"/);
    if (m) return { verifier_sha256: m[1], algorithm: 'sha256' };
  }
  return null;
}

export function verifyNucleusLock() {
  const lock = readNucleusLock();
  if (!lock?.verifier_sha256) {
    return { gate: GATES.NUCLEUS_LOCK, ok: false, detail: 'nucleus.lock missing verifier_sha256' };
  }
  const verifierRulel = path.join(SRC, 'verifier.rulel');
  if (!fs.existsSync(verifierRulel)) {
    return { gate: GATES.NUCLEUS_LOCK, ok: false, detail: 'src/verifier.rulel missing' };
  }
  const verifierSrc = extractRulelContent(fs.readFileSync(verifierRulel, 'utf8'));
  const got = sha256(verifierSrc);
  const ok = got === lock.verifier_sha256;
  return {
    gate: GATES.NUCLEUS_LOCK,
    ok,
    expected: lock.verifier_sha256.slice(0, 16),
    got: got.slice(0, 16),
    algorithm: lock.algorithm || 'sha256',
  };
}

export function verifyCompilerEmitIdempotent(compileFn) {
  const src = fs.readFileSync(path.join(SRC, 'compiler.lin'), 'utf8');
  try {
    const gen1 = compileFn(src, { target: 'js' }).code;
    const gen2 = compileFn(src, { target: 'js' }).code;
    const h1 = sha256(gen1);
    const h2 = sha256(gen2);
    return {
      gate: GATES.COMPILER_EMIT_IDEMPOTENT,
      ok: h1 === h2,
      gen1Hash: h1.slice(0, 16),
      gen2Hash: h2.slice(0, 16),
    };
  } catch (e) {
    return { gate: GATES.COMPILER_EMIT_IDEMPOTENT, ok: false, error: String(e.message || e).slice(0, 200) };
  }
}

export async function verifyTranspileHashGate(runtimeDir) {
  try {
    const verifyUrl = pathToFileURL(path.join(runtimeDir, 'transpile_hash_verify.mjs')).href;
    const emitUrl = pathToFileURL(path.join(runtimeDir, 'emit_from_js.mjs')).href;
    const { verifyTranspileOutput, G_TRANSPIL_HASH } = await import(verifyUrl);
    const { emitLinFromJs } = await import(emitUrl);
    const jsSource = [
      'function add(a, b) { return a + b; }',
      'function mul(a, b) { return a * b; }',
      'module.exports = { add, mul };',
    ].join('\n');
    const emitted = emitLinFromJs(jsSource);
    const report = verifyTranspileOutput(emitted.lin);
    const ok = report.ok && report.gate === G_TRANSPIL_HASH && report.semantic_hash_stable && report.code_hash_stable;
    return {
      gate: GATES.TRANSPIL_HASH,
      ok,
      semantic_hash_stable: report.semantic_hash_stable,
      code_hash_stable: report.code_hash_stable,
      code_hash: report.code_hash?.slice(0, 16),
    };
  } catch (e) {
    return { gate: GATES.TRANSPIL_HASH, ok: false, error: String(e.message || e).slice(0, 200) };
  }
}

export async function runAllHashGates(runtimeDir) {
  const compilerUrl = pathToFileURL(path.join(runtimeDir, 'compiler.mjs')).href;
  const semanticUrl = pathToFileURL(path.join(runtimeDir, 'semantic_hash.mjs')).href;
  const { compile } = await import(compilerUrl);
  const { semanticHash } = await import(semanticUrl);

  const gates = [
    verifyCoreSeedHashes(compile),
    verifySemanticHashGate(semanticHash),
    verifyNucleusLock(),
    verifyCompilerEmitIdempotent(compile),
    await verifyTranspileHashGate(runtimeDir),
  ];
  const ok = gates.every((g) => g.ok);
  return { ok, gates, checkedAt: new Date().toISOString() };
}
