import { parseProgram } from './parser.mjs';
import { renderProgramJs } from './render_js.mjs';
import { programHashes } from './semantic_hash.mjs';
import { assertJsSyntax, runInMemory } from './vm.mjs';
import {
  emitTs, emitPy, emitGo, emitRust, emitC, emitJava,
  isJsRuntimeOnly, stmtsText,
} from './emitters.mjs';
import { EmitUnsupportedError } from './emitters.mjs';
import { validateRegex } from './regex_ir.mjs';

export const LIN_VERSION = '2.0.0';
export const REAL_TARGETS = ['js', 'ts', 'py', 'go', 'rust', 'c', 'java'];
export const DEFAULT_EMIT_TARGET = 'js';

export function compile(source, opts = {}) {
  const target = String(opts.target || DEFAULT_EMIT_TARGET).toLowerCase();
  if (!REAL_TARGETS.includes(target)) {
    throw new Error(`LIN_EMIT_TARGET: unsupported ${target}; want ${REAL_TARGETS.join('|')} (default ${DEFAULT_EMIT_TARGET})`);
  }
  opts.__srcText = source;
  const prog = parseProgram(source);
  validateExports(prog);
  validateRegexUsage(prog, target, opts);
  if (target === 'ts') {
    return finish(prog, emitTs(prog, opts), target);
  }
  if (target === 'js') {
    let code = renderProgramJs(prog, { ...opts, version: LIN_VERSION });
    if (opts.sandbox) {
      const guard = wrapSandbox(code, prog, opts.sandbox);
      if (guard) code += guard;
    }
    assertJsSyntax(code);
    return finish(prog, code, target);
  }
  const stubNames = new Set();
  for (const fn of prog.fns) {
    if (isJsRuntimeOnly(stmtsText(fn))) {
      if (opts.stubJsRuntimeOnly === true) stubNames.add(fn.name);
      else throw new Error(`LIN_EMIT_JS_RUNTIME_ONLY: fn ${fn.name} uses JS-only runtime on target ${target}`);
    }
  }
  opts.__stubNames = stubNames;
  try {
    switch (target) {
      case 'py': return finish(prog, emitPy(prog, opts), target);
      case 'go': return finish(prog, emitGo(prog, opts), target);
      case 'rust': return finish(prog, emitRust(prog, opts), target);
      case 'c': return finish(prog, emitC(prog, opts), target);
      case 'java': return finish(prog, emitJava(prog, opts), target);
      default: throw new Error(`LIN_EMIT_TARGET: ${target}`);
    }
  } catch (e) {
    if (e instanceof EmitUnsupportedError) throw e;
    throw e;
  }
}

function finish(prog, code, target) {
  return {
    code,
    program: prog,
    target,
    hashes: programHashes(prog),
    fns: prog.fns.map((f) => f.name),
  };
}

const REGEX_PRIMITIVES_RE = /\bregex_(test|find|replace|split)\b/;
const REGEX_JS_PRELUDE = `/* LIN_REGEX_001 primitives */
function __liaRe(x){
  if (x instanceof RegExp) return x;
  var s = String(x), f = '';
  var im = /^\\(\\?([gimsuy]+)\\)/.exec(s);
  if (im) { f = im[1]; s = s.slice(im[0].length); }
  return new RegExp(s, f);
}
function regex_test(text, re){ return __liaRe(re).test(text); }
function regex_find(text, re){ var m = __liaRe(re).exec(text); return m ? m[0] : null; }
function regex_replace(text, re, rep){ return String(text).replace(__liaRe(re), rep); }
function regex_split(text, re){ return String(text).split(__liaRe(re)); }
`;

function validateRegexUsage(prog, target, opts) {
  let usesPrimitives = false;
  const walk = (stmts) => {
    for (const st of stmts || []) {
      for (const key of ['expr', 'rhs', 'cond']) {
        const ex = st[key];
        if (ex && Array.isArray(ex.parts)) {
          for (const part of ex.parts) {
            if (part.kind === 'node' && part.node && part.node.kind === 'regex') {
              const { pattern, flags } = part.node;
              const v = validateRegex(pattern, flags);
              if (!v.ok) throw new Error(`LIN_REGEX_001: padrão inválido /${pattern}/${flags}: ${v.error}`);
            } else if (part.kind === 'raw' && REGEX_PRIMITIVES_RE.test(part.text)) {
              usesPrimitives = true;
            }
          }
        }
      }
      for (const key of ['then', 'else', 'body']) walk(st[key]);
      if (Array.isArray(st.elseIf)) for (const ei of st.elseIf) walk(ei.body);
      if (Array.isArray(st.arms)) for (const arm of st.arms) walk(arm.body);
    }
  };
  for (const fn of prog.fns || []) walk(fn.body);
  for (const mod of prog.modules || []) for (const fn of mod.program.fns || []) walk(fn.body);
  if (REGEX_PRIMITIVES_RE.test(String(opts.__srcText ?? ''))) usesPrimitives = true;
  if (usesPrimitives && !prog.__regexPrimChecked) {
    prog.__regexPrimChecked = true;
    if (target === 'js') opts.prelude = REGEX_JS_PRELUDE + (opts.prelude || '');
    else throw new Error(`LIN_REGEX_001: primitivas regex_* suportadas apenas no alvo js (pedido: ${target})`);
  }
}

function validateExports(prog) {
  const names = new Set();
  for (const fn of prog.fns) names.add(fn.name);
  for (const mod of prog.modules || []) {
    for (const fn of mod.program.fns || []) names.add(`${mod.name}.${fn.name}`);
  }
  for (const u of prog.uses || []) {
    for (const sym of u.symbols) names.add(sym);
  }
  for (const name of prog.exports) {
    const raw = name.includes(' as ') ? name.split(/\s+as\s+/)[0].trim() : name;
    if (!names.has(raw)) throw new Error(`LIN_EXPORT_NO_FN: ${name}`);
  }
}

function wrapSandbox(js, prog, sandboxSpec) {
  void js;
  const allowed = Array.isArray(sandboxSpec) ? sandboxSpec : ['Pure', 'Read'];
  const unsafe = {};
  for (const fn of prog.fns) {
    const fx = fn.effect || 'Pure';
    if (!allowed.includes(fx)) unsafe[fn.name] = fx;
  }
  const unsafeNames = Object.keys(unsafe);
  if (!unsafeNames.length) return '';
  return `

/* sandbox guard */
(function(){
  var _orig = module.exports;
  var _allowed = ${JSON.stringify(allowed)};
  var _unsafe = ${JSON.stringify(unsafe)};
  var _wrap = typeof _orig === 'function'
    ? function(){ throw new Error('LIN_SANDBOX: exported function is ' + Object.values(_unsafe)[0] + ', allowed=' + _allowed.join('|')); }
    : {};
  if (typeof _orig === 'object' && _orig) {
    for (var k in _orig) {
      if (_unsafe[k]) {
        _wrap[k] = (function(fx, nm){ return function(){ throw new Error('LIN_SANDBOX: ' + nm + ' has effect ' + fx + ', allowed=' + _allowed.join('|')); }; })(_unsafe[k], k);
      } else {
        _wrap[k] = _orig[k];
      }
    }
  }
  module.exports = _wrap;
})();
`;
}

export function compileToTargetFileShim(source, target) {
  void source;
  void target;
}

export { runInMemory };
