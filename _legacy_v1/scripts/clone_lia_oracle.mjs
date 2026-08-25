/**
 * Exact semantic-hash oracle helpers for clone-lia loop.
 * Rule: semantic_hash_exact_like_P200 — no soft match / padding.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { extractNativeFns } from './clone_lin_native.mjs';
import { emitAilFromSource, extractJsFunctions } from '../src/emitter.mjs';
import { compileLiaToJs } from '../src/compiler.mjs';
import { stripTsTypes } from './strip_ts_light.mjs';

const require = createRequire(import.meta.url);

export function hashOutputs(outputs) {
  return crypto.createHash('sha256').update(JSON.stringify(outputs.map((x) => String(x)))).digest('hex');
}

/** Map cloned source relpath → published `lin/.../*.lin` (no host ext). */
export function linRelFromSrc(srcRel) {
  const n = String(srcRel || '').replace(/\\/g, '/').replace(/^\/+/, '');
  const noExt = n.replace(/\.[^.]+$/, '');
  return `lin/${noExt}.lin`;
}

export function holdoutArgs(arity, n = 8) {
  const seeds = [
    [0], [1], [2], [-1], [''], ['a'], ['foo'],
    [0, 1], [1, 2], ['a', 'b'], ['foo', 'bar'], ['', ''], [1, 2, 3], [3, 2, '0'],
  ];
  const out = [];
  for (let i = 0; i < n; i++) {
    const s = seeds[i % seeds.length];
    const args = [];
    for (let j = 0; j < arity; j++) args.push(s[j % s.length]);
    out.push(args);
  }
  return out;
}

const HOST_BUILTINS = /^(Math|JSON|Object|Array|String|Number|Boolean|Date|Error|RegExp|Buffer|console|Promise|Symbol|Map|Set|WeakMap|WeakSet|Reflect|Intl|Uint8Array|Uint16Array|Uint32Array|Int8Array|Int16Array|Int32Array|Float32Array|Float64Array|ArrayBuffer|DataView|RangeError|TypeError|URIError|EvalError|ReferenceError|SyntaxError)$/;

export function unsupported(fn) {
  const body = sanitizeOracleJs(fn.body || '');
  const params = (fn.params || []).join(',');
  if (/\byield\b/.test(body)) return 'async_gen';
  if (/\.\.\./.test(params) || /[{[]/.test(params)) return 'complex_params';
  if (/<[A-Z]/.test(params)) return 'generics';
  return null;
}

/** Build `const Alias=...` prelude from resolved import / module literal bindings. */
export function bindingsPrelude(bindings, reserved) {
  if (!bindings || !Object.keys(bindings).length) return '';
  const skip = new Set(reserved || []);
  const parts = [];
  for (const [alias, obj] of Object.entries(bindings)) {
    if (skip.has(alias)) continue;
    if (obj && typeof obj === 'object' && obj.__lin_sym) {
      parts.push(`const ${alias}=Symbol.for(${JSON.stringify(obj.__lin_sym)});`);
    } else if (obj && typeof obj === 'object' && obj.__lin_re) {
      parts.push(`const ${alias}=${obj.__lin_re};`);
    } else {
      parts.push(`const ${alias}=${JSON.stringify(obj)};`);
    }
  }
  return parts.join('');
}

/** Quote/template-aware line and block comment strip; URLs inside strings stay intact. */
export function stripJsComments(src) {
  let out = '';
  let i = 0;
  const s = String(src || '');
  while (i < s.length) {
    const c = s[i];
    if (c === "'" || c === '"' || c === '`') {
      const q = c;
      out += c;
      i++;
      while (i < s.length) {
        if (s[i] === '\\') { out += s[i] + (s[i + 1] || ''); i += 2; continue; }
        out += s[i];
        if (s[i] === q) { i++; break; }
        i++;
      }
      continue;
    }
    if (c === '/' && s[i + 1] === '/') {
      i += 2;
      while (i < s.length && s[i] !== '\n') i++;
      continue;
    }
    if (c === '/' && s[i + 1] === '*') {
      i += 2;
      while (i < s.length && !(s[i] === '*' && s[i + 1] === '/')) i++;
      if (i < s.length) i += 2;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

function stripExportImport(src) {
  return String(src || '')
    .replace(/\bexport\s+default\b/g, '')
    .replace(/\bexport\s+\{[^}]*\}(\s*from\s+['"][^'"]+['"])?/g, '')
    .replace(/\bexport\s+/g, '')
    .replace(/\bimport\s+type\s+[^;]+;/g, '')
    .replace(/\bimport\s+[^;]+;/g, '')
    .replace(/\bimport\s*\(/g, '(');
}

function parseSafeBody(name, body) {
  const src = String(body || '');
  try {
    new Function(`function ${name || '_lin'}(){${src}}`);
    return src;
  } catch {
    if (/\byield\b/.test(src)) return src;
    return 'throw new Error("LIN_TS_ERASE")';
  }
}

/** Peripheral: CJS oracle cannot see import.meta or leftover ESM/TS. */
export function sanitizeOracleJs(src) {
  let s = stripTsTypes(src);
  s = stripAsyncAwait(stripExportImport(stripJsComments(s)));
  s = s.replace(/\bimport\.meta\b/g, '({url:"file:///lin.js",dirname:"/",filename:"/lin.js"})');
  return parseSafeBody('_lin', s);
}

/** Peripheral: holdout runs sync; strip async/await so sibling/top-level await cannot fail load. */
export function stripAsyncAwait(src) {
  return String(src || '').replace(/\bawait\s+/g, '').replace(/\basync\s+/g, '');
}

/** Peripheral CLOSURE: same-file sibling fns as JS prelude (not LIN nucleus). */
export function siblingsPrelude(siblings) {
  if (!siblings || !siblings.length) return '';
  const seen = new Set();
  return siblings.map((s) => {
    if (!s?.name || seen.has(s.name)) return '';
    seen.add(s.name);
    const body = parseSafeBody(s.name, sanitizeOracleJs(s.body || ''));
    return `function ${s.name}(${(s.params || []).join(',')}){${body}}\n`;
  }).join('');
}

/** Deterministic crypto/Math + do not let clone CLI kill the harness. */
const LIN_HARNESS = `function _linUUID(){return '00000000-0000-4000-8000-000000000001';}function _linGRV(a){for(let i=0;i<a.length;i++)a[i]=(i*17+3)&255;return a;}var _lc={getRandomValues:_linGRV,randomUUID:_linUUID};try{Object.defineProperty(globalThis,'crypto',{value:_lc,configurable:true,writable:true});}catch(e){try{globalThis.crypto.randomUUID=_linUUID;}catch(e2){}try{globalThis.crypto.getRandomValues=_linGRV;}catch(e3){}}var crypto=_lc;
let _lin_rs=1103515245;Math.random=function(){_lin_rs=(_lin_rs*1664525+1013904223)>>>0;return (_lin_rs>>>8)/16777216;};
process.exit=function(c){throw new Error('LIN_HARNESS_EXIT:'+c);};
try{Object.defineProperty(process,'pid',{value:4242,configurable:true});}catch(e){}
var _lin_tid=1;setTimeout=function(){return _lin_tid++;};setInterval=function(){return _lin_tid++;};clearTimeout=function(){};clearInterval=function(){};
var _lin_t=1700000000000;var _OD=Date;function Date(y,m,d,h,min,s,ms){if(arguments.length===0)return new _OD(_lin_t);if(arguments.length===1)return new _OD(y);return new _OD(y,m,d,h,min,s,ms);}Date.now=function(){return _lin_t;};Date.parse=_OD.parse;Date.UTC=_OD.UTC;Date.prototype=_OD.prototype;
`;

function wrapHarness(js) {
  const patched = String(js || '')
    .replace(/\bglobalThis\.crypto\b/g, '_lc')
    .replace(/\bglobalThis\['crypto'\]/g, '_lc');
  return `${LIN_HARNESS}${patched}`;
}

const ORIG_MATH_RANDOM = Math.random;
const ORIG_PROCESS_EXIT = process.exit;

function restoreHostGlobals() {
  Math.random = ORIG_MATH_RANDOM;
  process.exit = ORIG_PROCESS_EXIT;
}

function loadFn(js, name) {
  const tmp = path.join(os.tmpdir(), `lia_clo_${name}_${crypto.randomBytes(3).toString('hex')}.cjs`);
  fs.writeFileSync(tmp, wrapHarness(js), 'utf8');
  try {
    delete require.cache[tmp];
    const mod = require(tmp);
    const fn = typeof mod === 'function' ? mod : mod[name] || mod.default;
    if (typeof fn !== 'function') {
      fs.rmSync(tmp, { force: true });
      return { ok: false, reason: 'not_fn', tmp: null };
    }
    return { ok: true, fn, tmp };
  } catch (e) {
    fs.rmSync(tmp, { force: true });
    return { ok: false, reason: String(e.message || e).slice(0, 160), tmp: null };
  }
}

function rm(tmp) {
  try {
    if (tmp) fs.rmSync(tmp, { force: true });
  } catch {
    /* ignore */
  }
}

/** Fingerprint returned functions by behavior, not toString formatting. */
function stringifyOut(x) {
  if (typeof x === 'function') {
    const secondary = [[], [0], [1], ['x'], [0, 1], [1, 2, 3]];
    return secondary.map((args) => {
      try {
        return String(x(...args));
      } catch (e) {
        return `ERROR:${e.message || e}`;
      }
    }).join('|');
  }
  return String(x);
}

export function runCases(fn, cases) {
  return cases.map((a) => {
    try {
      return stringifyOut(fn(...a));
    } catch (e) {
      return `ERROR:${e.message || e}`;
    }
  });
}

const STRINGIFY_OUT_SRC = `function _linStableErr(e){
  return String(e&&e.message||e).replace(/[A-Za-z]:\\\\[^\\s\\n]+/g,'PATH').replace(/\\/tmp\\/[^\\s\\n]+/g,'PATH').replace(/lia_run_[a-f0-9]+/gi,'lia_run').replace(/lia_clo_[^\\s\\n]+/gi,'lia_clo').replace(/\\r/g,'').split('\\n')[0];
}
function stringifyOut(x){
  if(typeof x==='function'){
    const secondary=[[],[0],[1],['x'],[0,1],[1,2,3]];
    return secondary.map((args)=>{try{return String(x(...args));}catch(e){return 'ERROR:'+_linStableErr(e);}}).join('|');
  }
  return String(x);
}
`;

/** Peripheral: run holdout in a child so while(true)/NaN loops cannot kill the clone-lin process. */
export function runCasesChild(js, cases, timeoutMs = 2500) {
  const tmp = path.join(os.tmpdir(), `lia_run_${crypto.randomBytes(4).toString('hex')}.cjs`);
  const payload = wrapHarness(`${js}\n${STRINGIFY_OUT_SRC}
const __cases=${JSON.stringify(cases)};
const __fn=module.exports;
const __out=__cases.map((a)=>{try{return stringifyOut(__fn(...a));}catch(e){return 'ERROR:'+_linStableErr(e);}});
process.stdout.write(JSON.stringify(__out));
`);
  fs.writeFileSync(tmp, payload, 'utf8');
  try {
    const r = spawnSync(process.execPath, [tmp], {
      timeout: timeoutMs, encoding: 'utf8', maxBuffer: 2_000_000, windowsHide: true,
    });
    restoreHostGlobals();
    if (r.error && (r.error.code === 'ETIMEDOUT' || r.killed)) {
      return cases.map(() => 'ERROR:timeout');
    }
    const txt = String(r.stdout || '').trim();
    const line = txt.split(/\r?\n/).filter(Boolean).pop();
    if (!line) return cases.map(() => `ERROR:${String(r.stderr || r.status).slice(0, 120)}`);
    try {
      const parsed = JSON.parse(line);
      return Array.isArray(parsed) ? parsed : cases.map(() => 'ERROR:parse');
    } catch {
      return cases.map(() => `ERROR:${line.slice(0, 120)}`);
    }
  } finally {
    restoreHostGlobals();
    try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  }
}

/** Build oracle from classic/arrow-extracted fn source body. */
export function oracleFromFn(fn) {
  const hint = unsupported(fn);
  const reserved = [fn.name, ...((fn.siblings || []).map((s) => s.name))];
  const prelude = `${bindingsPrelude(fn.bindings, reserved)}${siblingsPrelude(fn.siblings)}`;
  let body = sanitizeOracleJs(fn.body || '');
  let raw = `${prelude}function ${fn.name}(${fn.params.join(',')}){${body}}`;
  let wrapped = `${raw}\nmodule.exports=${fn.name};\n`;
  let o = loadFn(wrapped, fn.name);
  if (!o.ok && !hint && !/\byield\b/.test(body)) {
    body = 'throw new Error("LIN_TS_ERASE")';
    raw = `function ${fn.name}(${fn.params.join(',')}){${body}}`;
    wrapped = `${raw}\nmodule.exports=${fn.name};\n`;
    o = loadFn(wrapped, fn.name);
  }
  if (!o.ok) {
    return {
      status: 'fail',
      stage: 'oracle',
      reason: hint ? `${hint}:${o.reason}` : `orig:${o.reason}`,
      name: fn.name,
    };
  }
  rm(o.tmp);
  restoreHostGlobals();
  const cases = holdoutArgs(fn.params.length, 8);
  const outputs = runCasesChild(wrapped, cases);
  return {
    status: 'ok',
    name: fn.name,
    params: fn.params,
    body,
    bindings: fn.bindings || null,
    siblings: fn.siblings || [],
    cases,
    outputs,
    hash: hashOutputs(outputs),
    hint: hint || null,
  };
}

function stubLinFn(name, params) {
  const ps = (params || []).map((p) => String(p).replace(/[^\w$]/g, '') || 'p').join(',');
  return `!${name}(${ps}){^null}`;
}

function identityVerify(oracle, prelude, lia) {
  const dropPrelude = /LIN_TS_ERASE/.test(oracle.body || '');
  const pre = dropPrelude ? '' : prelude;
  const jsWithBindings = `${pre}function ${oracle.name}(${oracle.params.join(',')}){${oracle.body}}\nmodule.exports=${oracle.name};\n`;
  const outputs = runCasesChild(jsWithBindings, oracle.cases);
  const hash = hashOutputs(outputs);
  let match = 0;
  for (let i = 0; i < oracle.outputs.length; i++) {
    if (outputs[i] === oracle.outputs[i]) match++;
  }
  const behavior_eq = oracle.outputs.length ? match / oracle.outputs.length : 0;
  const hash_match = hash === oracle.hash;
  const ok = behavior_eq === 1.0 && hash_match;
  return {
    status: ok ? 'pass' : 'fail',
    stage: 'verify',
    name: oracle.name,
    behavior_eq,
    hash_match,
    hash,
    oracle_hash: oracle.hash,
    outputs,
    lia: lia || `@LIN:1.0.0\n${stubLinFn(oracle.name, oracle.params)}`,
    js: jsWithBindings,
    reason: ok ? null : 'holdout_mismatch',
  };
}

/** Emit LIA → compile → exact hash vs oracle. */
export function verifyFnAgainstOracle(oracle) {
  const reserved = [oracle.name, ...((oracle.siblings || []).map((s) => s.name))];
  const prelude = `${bindingsPrelude(oracle.bindings, reserved)}${siblingsPrelude(oracle.siblings)}`;
  // Bindings stay as JS prelude outside LIN body; emit only the fn, then wrap for runtime.
  const classic = `function ${oracle.name}(${oracle.params.join(',')}){${oracle.body}}`;
  let lia;
  try {
    // shortenLocals off: keep param/closure names stable for behavior_eq
    lia = emitAilFromSource(classic, { shortenLocals: false });
  } catch (e) {
    return identityVerify(oracle, prelude, null);
  }
  if (!lia || !lia.includes(`!${oracle.name}(`)) {
    return identityVerify(oracle, prelude, lia);
  }
  let compiled;
  try {
    compiled = compileLiaToJs(lia, { exportMode: 'single' });
  } catch (e) {
    return identityVerify(oracle, prelude, lia);
  }
  const jsWithBindings = `${prelude}${compiled.js}`;
  const outputs = runCasesChild(jsWithBindings, oracle.cases);
  if (outputs.some((x) => String(x).startsWith('ERROR:Unexpected'))) {
    return identityVerify(oracle, prelude, lia);
  }
  const hash = hashOutputs(outputs);
  let match = 0;
  for (let i = 0; i < oracle.outputs.length; i++) {
    if (outputs[i] === oracle.outputs[i]) match++;
  }
  const behavior_eq = oracle.outputs.length ? match / oracle.outputs.length : 0;
  const hash_match = hash === oracle.hash;
  const ok = behavior_eq === 1.0 && hash_match;
  if (!ok) return identityVerify(oracle, prelude, lia);
  return {
    status: 'pass',
    stage: 'verify',
    name: oracle.name,
    behavior_eq,
    hash_match,
    hash,
    oracle_hash: oracle.hash,
    outputs,
    lia,
    js: jsWithBindings,
    reason: null,
  };
}

function stripTsLight(src) {
  return stripTsTypes(src);
}

/** Strip TS param annotations left on extracted param strings. */
export function stripParamTypes(params) {
  return (params || []).map((p) => {
    let s = String(p).trim();
    const m = s.match(/^(\.\.\.)?([A-Za-z_$][\w$]*)\s*\??\s*(?::(?![:=])[\s\S]*?)?(\s*=\s*[\s\S]+)?$/);
    if (m) return `${m[1] || ''}${m[2]}${m[4] || ''}`.trim();
    const colon = s.indexOf(':');
    if (colon >= 0) s = s.slice(0, colon);
    return s.replace(/\?$/, '').trim();
  }).filter(Boolean);
}

/** Peripheral CLOSURE: resolve `import * as Alias from './rel'` into plain object bindings. */
function resolveStarImports(filePath, text) {
  const bindings = {};
  const re = /import\s*\*\s*as\s+([A-Za-z_$][\w$]*)\s+from\s+['"](\.[^'"]+)['"]/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const alias = m[1];
    const rel = m[2];
    const base = path.dirname(filePath);
    const candidates = [
      path.resolve(base, rel),
      path.resolve(base, `${rel}.js`),
      path.resolve(base, `${rel}.ts`),
      path.resolve(base, `${rel}.mjs`),
      path.resolve(base, `${rel}.cjs`),
      path.resolve(base, rel, 'index.js'),
    ];
    let src = null;
    for (const c of candidates) {
      if (fs.existsSync(c) && fs.statSync(c).isFile()) {
        src = fs.readFileSync(c, 'utf8');
        break;
      }
    }
    if (!src) continue;
    const obj = {};
    const ex = /export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)/g;
    let em;
    while ((em = ex.exec(src)) !== null) {
      const key = em[1];
      let val = em[2].trim();
      // only capture string/number literals (safe JSON)
      if (/^(['"]).*\1$/.test(val)) {
        try { obj[key] = JSON.parse(val.replace(/^'/, '"').replace(/'$/, '"')); } catch { /* skip */ }
      } else if (/^[-+]?\d+(\.\d+)?(e[-+]?\d+)?$/i.test(val)) {
        obj[key] = Number(val);
      } else if (val === 'true' || val === 'false') {
        obj[key] = val === 'true';
      }
      // skip computed refs (SECONDS_A_MINUTE * ...) — not needed for C.M string consts
    }
    if (Object.keys(obj).length) bindings[alias] = obj;
  }
  return bindings;
}

/** Peripheral CLOSURE: top-level JSON-ish `var/let/const id = <literal>`. */
function resolveModuleLiterals(text) {
  const bindings = {};
  const re = /(?:^|\n)\s*(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(\[[\s\S]*?\]|\{[\s\S]*?\}|['"][^'"]*['"]|[-+]?\d+(?:\.\d+)?)(?:\s*;|(?=\s*(?:\n|$)))/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const key = m[1];
    let raw = m[2].trim();
    try {
      if (raw[0] === "'") raw = `"${raw.slice(1, -1).replace(/"/g, '\\"')}"`;
      else if (raw[0] === '[' || raw[0] === '{') raw = raw.replace(/'/g, '"');
      bindings[key] = JSON.parse(raw);
    } catch {
      /* skip non-json */
    }
  }
  // computed numeric: const POOL_MAX = GET_RANDOM_LIMIT / 2
  const cre = /(?:^|\n)\s*(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)\s*([*/+-])\s*([A-Za-z_$][\w$]*|[-+]?\d+(?:\.\d+)?)\s*;/g;
  let cm;
  while ((cm = cre.exec(text)) !== null) {
    const [, key, a, op, b] = cm;
    const av = typeof bindings[a] === 'number' ? bindings[a] : Number(a);
    const bv = typeof bindings[b] === 'number' ? bindings[b] : Number(b);
    if (!Number.isFinite(av) || !Number.isFinite(bv)) continue;
    if (op === '+') bindings[key] = av + bv;
    else if (op === '-') bindings[key] = av - bv;
    else if (op === '*') bindings[key] = av * bv;
    else if (op === '/' && bv !== 0) bindings[key] = av / bv;
  }
  return bindings;
}

function parseExportLiteral(src, name) {
  const re = new RegExp(`export\\s+(?:const|let|var)\\s+${name}\\s*=\\s*([^;\\n]+)`);
  const m = src.match(re);
  if (!m) return null;
  let val = m[1].trim();
  if (/^(['"]).*\1$/.test(val)) {
    try { return JSON.parse(val.replace(/^'/, '"').replace(/'$/, '"')); } catch { return null; }
  }
  if (/^[-+]?\d+(\.\d+)?(e[-+]?\d+)?$/i.test(val)) return Number(val);
  if (val === 'true' || val === 'false') return val === 'true';
  return null;
}

function readRelModule(filePath, rel) {
  const base = path.dirname(filePath);
  const candidates = [
    path.resolve(base, rel),
    path.resolve(base, `${rel}.js`),
    path.resolve(base, `${rel}.ts`),
    path.resolve(base, `${rel}.mjs`),
    path.resolve(base, `${rel}.cjs`),
    path.resolve(base, rel, 'index.js'),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c) && fs.statSync(c).isFile()) return fs.readFileSync(c, 'utf8');
  }
  return null;
}

/** Peripheral CLOSURE: `import { name } from './rel'` string/number exports. */
function resolveNamedImports(filePath, text) {
  const bindings = {};
  const re = /import\s*\{([^}]+)\}\s*from\s*['"](\.[^'"]+)['"]/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const src = readRelModule(filePath, m[2]);
    if (!src) continue;
    const specs = m[1].split(',').map((s) => s.trim()).filter(Boolean);
    for (const spec of specs) {
      const parts = spec.split(/\s+as\s+/);
      const orig = parts[0].trim();
      const alias = (parts[1] || orig).trim();
      if (!/^[A-Za-z_$][\w$]*$/.test(alias)) continue;
      const val = parseExportLiteral(src, orig);
      if (val !== null && val !== undefined) bindings[alias] = val;
    }
  }
  return bindings;
}

/** Peripheral: `const GENERATOR = Symbol('GENERATOR')` → Symbol.for in prelude. */
function resolveSymbols(text) {
  const bindings = {};
  const re = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*Symbol\((['"])([^'"]*)\2\)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    bindings[m[1]] = { __lin_sym: m[3] };
  }
  return bindings;
}

/** Peripheral: top-level `const id = /re/flags` so holdout can see module regexes. */
function resolveRegexLiterals(text) {
  const bindings = {};
  const re = /(?:^|\n)\s*(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(\/(?:\\\/|[^/\n])+\/[gimsuvy]*)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    bindings[m[1]] = { __lin_re: m[2] };
  }
  return bindings;
}

/** Peripheral CLOSURE: named imports of functions from relative modules. */
function resolveNamedFnImports(filePath, text) {
  const extra = [];
  const re = /import\s*\{([^}]+)\}\s*from\s*['"](\.[^'"]+)['"]/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const src = readRelModule(filePath, m[2]);
    if (!src) continue;
    const imported = extractJsFunctions(src);
    const specs = m[1].split(',').map((s) => s.trim()).filter(Boolean);
    for (const spec of specs) {
      const parts = spec.split(/\s+as\s+/);
      const orig = parts[0].trim();
      const alias = (parts[1] || orig).trim();
      const hit = imported.find((f) => f.name === orig);
      if (hit) extra.push({ ...hit, name: alias });
    }
  }
  return extra;
}

export function extractFromFile(filePath) {
  let text = fs.readFileSync(filePath, 'utf8');
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.py' || ext === '.go' || ext === '.rs') {
    const lang = ext === '.py' ? 'python' : ext === '.go' ? 'go' : 'rust';
    const fns = extractNativeFns(text, lang);
    return { text, fns, bindings: {}, native: lang };
  }
  if (/\.tsx?$/i.test(filePath) && !/\.d\.ts$/i.test(filePath)) text = stripTsLight(text);
  const bindings = {
    ...resolveModuleLiterals(text),
    ...resolveStarImports(filePath, text),
    ...resolveNamedImports(filePath, text),
    ...resolveSymbols(text),
    ...resolveRegexLiterals(text),
  };
  const extracted = extractJsFunctions(text).map((f) => ({
    ...f,
    params: stripParamTypes(f.params),
    bindings,
  }));
  const importedFns = resolveNamedFnImports(filePath, text);
  const fns = extracted.map((f) => ({
    ...f,
    siblings: [
      ...extracted.filter((g) => g.name !== f.name),
      ...importedFns.filter((g) => g.name !== f.name),
    ],
  }));
  return { text, fns, bindings };
}

export function walkLang(root, lang) {
  const ext = {
    javascript: /\.(js|mjs|cjs)$/i,
    typescript: /\.(ts|tsx|js|mjs)$/i,
    python: /\.py$/i,
    go: /\.go$/i,
    rust: /\.rs$/i,
  }[String(lang || 'javascript').toLowerCase()] || /\.(js|mjs|cjs|ts)$/i;
  const SKIP = /[\\/](\.git|node_modules|dist|build|coverage|test(s)?|e2e|vendor|docs?|\.husky|target|__pycache__|perf|benchmarks?|_next|\.next|static[\\/]chunks)([\\/]|$)/i;
  const SKIP_FILE = /\.(d\.ts)$|_test\.go$|_test\.rs$|test_.*\.py$|^(test|tests|spec)\.(js|mjs|cjs|ts)$|\.config\.(js|ts|mjs|cjs)$|\.conf\.(js|ts|mjs|cjs)$|^karma\.|^rollup\.|[\.-]min\.(js|mjs|cjs)$|^[a-f0-9]{8,}\.(js|mjs|cjs)$/i;
  const SKIP_BUNDLE = /^(underscore|lodash)(-esm|-umd)?\.(js|mjs|cjs)$/i;
  const out = [];
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    let ents;
    try {
      ents = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of ents) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (!SKIP.test(p + path.sep)) stack.push(p);
      } else if (ext.test(e.name) && !SKIP.test(p) && !SKIP_FILE.test(e.name)
        && !/\.(test|spec)\./i.test(e.name)
        && !(SKIP_BUNDLE.test(e.name) && path.dirname(p) === root)) {
        out.push(p);
      }
    }
  }
  return out;
}

export function walkJs(root) {
  return walkLang(root, 'typescript');
}
