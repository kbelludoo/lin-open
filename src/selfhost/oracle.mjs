import { createHash } from 'node:crypto';
import vm from 'node:vm';
import { siblingsPrelude } from './extract.mjs';

export function hashOutputs(outputs) {
  return createHash('sha256').update(JSON.stringify(outputs.map((x) => safeString(x)))).digest('hex');
}

function safeString(x) {
  if (typeof x === 'string') return x;
  try {
    return JSON.stringify(x) ?? String(x);
  } catch {
    return String(x);
  }
}

const SEEDS = [
  [0], [1], [2], [-1], [''], ['a'], ['foo'],
  [0, 1], [1, 2], ['a', 'b'], ['foo', 'bar'], ['', ''], [1, 2, 3], [3, 2, '0'],
];

export function holdoutArgs(arity, n = 8) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const s = SEEDS[i % SEEDS.length];
    const args = [];
    for (let j = 0; j < arity; j++) args.push(s[j % s.length]);
    out.push(args);
  }
  return out;
}

export function unsupported(fn) {
  const body = String(fn.body || '');
  const params = (fn.params || []).join(',');
  if (/\byield\b/.test(body)) return 'async_gen';
  if (/\.\.\./.test(params) || /[{[]/.test(params.replace(/=\s*[^,]*/g, ''))) return 'complex_params';
  if (/\bawait\b/.test(body)) return 'async_await';
  if (/\bclass\b/.test(body) || /\bthis\b/.test(body)) return 'class_this';
  return null;
}

export function runFnInMemory(name, body, rawParams, args, prelude = '') {
  const wrapper = `(function(){\nfunction ${name}(${rawParams}){${body}}\nreturn ${name}.apply(null, __args);\n})()`;
  const sandbox = vm.createContext({
    __args: args,
    console,
    Math,
    JSON,
    Object,
    Array,
    String,
    Number,
    Boolean,
    RegExp,
    Date,
    Error,
    TypeError,
    RangeError,
    parseInt,
    parseFloat,
    isNaN,
    isFinite,
    Symbol,
    Map,
    Set,
  });
  return new vm.Script(`${prelude}\n${wrapper}`).runInContext(sandbox, { timeout: 2000 });
}

export function buildOracle(fn, allFns, opts = {}) {
  const varsPrelude = opts.varsPrelude || '';
  const reason = unsupported(fn);
  if (reason) return { ok: false, skip: true, reason };
  const arity = fn.params.length;
  const cases = (opts.args || holdoutArgs(arity, opts.cases || 8)).map((args) => {
    let want;
    let err = null;
    try {
      want = runFnInMemory(fn.name, sanitizeBody(fn.body), fn.rawParams, args, varsPrelude + '\n' + siblingsPrelude(allFns, fn.name));
    } catch (e) {
      err = e.message;
    }
    return { args, want: err ? `__error__:${err}` : want };
  });
  if (cases.every((c) => typeof c.want === 'string' && c.want.startsWith('__error__:'))) {
    return { ok: false, skip: true, reason: 'oracle_unloadable' };
  }
  return { ok: true, skip: false, cases, hash: hashOutputs(cases.map((c) => c.want)) };
}

export function sanitizeBody(body) {
  let s = String(body || '');
  s = s.replace(/\basync\s+/g, '').replace(/\bawait\s+/g, '');
  s = s.replace(/\bimport\.meta\b/g, '({url:"file:///lin.js"})');
  return s;
}

export function verifyAgainstOracle(fn, compiledFn, oracle) {
  for (const c of oracle.cases) {
    let got;
    let err = null;
    try {
      got = compiledFn(...c.args);
    } catch (e) {
      err = e.message;
    }
    const gotKey = err ? `__error__:${err}` : got;
    const wantKey = c.want;
    if (safeString(gotKey) !== safeString(wantKey)) {
      return { pass: false, detail: `${fn.name}${JSON.stringify(c.args)} got=${safeString(gotKey)} want=${safeString(wantKey)}` };
    }
  }
  return { pass: true, detail: 'behavior_eq' };
}
