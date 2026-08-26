/**
 * LIA → C emitter (peripheral; not nucleus).
 * Expression emission goes through the AST-based emit_expr_c (typed,
 * JS-precedence-correct); unsupported constructs fall back to the legacy
 * text rewriter per statement.
 */
import { parseLia } from './compiler.mjs';
import { parseStmts, tryParseStmts, collectAssignedIds } from './body_ast.mjs';
import { isJsRuntimeOnly, rewriteExpr, emitCond, assignOpLine, parseParamList, emitNilDefaults, safeEmitId, emitNameMap, inferTypes } from './emit_shared.mjs';
import { emitExprC, emitCondC, buildCtx } from './emit_expr_c.mjs';
import { emitThrowLine } from './emit_rewrite.mjs';
import { rawParamNames, rewriteSafeParamIds } from './emit_safe_ids_load.mjs';
import { isQualityFnSet, formatQualityMain } from './emit_entry_main_load.mjs';

function emitStmts(stmts, indent, ctx) {
  const pad = '  '.repeat(indent);
  const lines = [];
  const tryE = (e) => {
    try { return emitExprC(e, ctx); } catch { return rewriteExpr(e, 'c'); }
  };
  const tryC = (c) => {
    try { return emitCondC(c, ctx); } catch { return emitCond(c, 'c'); }
  };
  for (const st of stmts) {
    if (st.type === 'assign') {
      const idxLhs = String(st.id).match(/^([A-Za-z_]\w*)\[([^\]]+)\]$/);
      if (idxLhs) {
        const idx = (() => { try { return emitExprC(idxLhs[2], ctx); } catch { return rewriteExpr(idxLhs[2], 'c'); } })();
        if (st.op === '=') lines.push(`${pad}${idxLhs[1]}[${idx}] = ${tryE(st.expr)};`);
        else {
          const bin = String(st.op).slice(0, -1);
          lines.push(`${pad}${idxLhs[1]}[${idx}] = ${idxLhs[1]}[${idx}] ${bin} (${tryE(st.expr)});`);
        }
        continue;
      }
      if (st.op === '=' && ctx.arrays.has(st.id)) {
        const a = ctx.arrays.get(st.id);
        const kw = (ctx.mutatedArr && ctx.mutatedArr.has(st.id)) ? '' : 'static ';
        lines.push(`${pad}${kw}long long ${st.id}[] = { ${a.items} };`);
        continue;
      }
      if (st.op === '=' && ctx.dynArrays && ctx.dynArrays.has(st.id)) {
        const da = ctx.dynArrays.get(st.id);
        lines.push(`${pad}${st.id}[0] = ${tryE(da.parts[0])};`);
        for (let ix3 = 1; ix3 < da.parts.length; ix3++) {
          lines.push(`${pad}${st.id}[${ix3}] = ${tryE(da.parts[ix3])};`);
        }
        continue;
      }
      if (ctx.strIds.has(st.id) && (st.op === '+=' || st.op === '=')) {
        lines.push(assignOpLine(st.id, st.op, st.expr, 'c', pad));
        continue;
      }
      if (st.op === '+=') {
        lines.push(`${pad}${safeEmitId(st.id)} = ${safeEmitId(st.id)} + (${tryE(st.expr)});`);
        continue;
      }
      if (/^(<<=|>>=|&=|\|=|\^=)$/.test(String(st.op))) {
        const bin = String(st.op).slice(0, -1);
        lines.push(`${pad}${safeEmitId(st.id)} = ${safeEmitId(st.id)} ${bin} (${tryE(st.expr)});`);
        continue;
      }
      lines.push(`${pad}${safeEmitId(st.id)} ${st.op} ${tryE(st.expr)};`);
    } else if (st.type === 'return') {
      lines.push(`${pad}return ${tryE(st.expr)};`);
    } else if (st.type === 'throw') {
      lines.push(emitThrowLine(st.expr, 'c', pad, rewriteExpr));
    } else if (st.type === 'expr') {
      if (/^break\b/.test(st.expr.trim())) lines.push(`${pad}break;`);
      else if (/^continue\b/.test(st.expr.trim())) lines.push(`${pad}continue;`);
      else if (/^throw\b/.test(st.expr.trim())) lines.push(emitThrowLine(st.expr, 'c', pad, rewriteExpr));
      else lines.push(`${pad}${tryE(st.expr)};`);
    } else if (st.type === 'if') {
      lines.push(`${pad}if (${tryC(st.cond)}) {`);
      lines.push(...emitStmts(st.then, indent + 1, ctx));
      for (const e of st.elseIf || []) {
        lines.push(`${pad}} else if (${tryC(e.cond, ctx)}) {`);
        lines.push(...emitStmts(e.body, indent + 1, ctx));
      }
      if (st.else) {
        lines.push(`${pad}} else {`);
        lines.push(...emitStmts(st.else, indent + 1, ctx));
      }
      lines.push(`${pad}}`);
    } else if (st.type === 'for') {
      lines.push(
        `${pad}for (${tryE(st.init)}; ${tryC(st.cond)}; ${tryE(st.step)}) {`,
      );
      lines.push(...emitStmts(st.body, indent + 1, ctx));
      lines.push(`${pad}}`);
    } else if (st.type === 'while') {
      lines.push(`${pad}while (${tryC(st.cond)}) {`);
      lines.push(...emitStmts(st.body, indent + 1, ctx));
      lines.push(`${pad}}`);
    }
  }
  return lines;
}


function buildFnSigs(prog) {
  const sigs = new Map();
  for (const fn of prog.fns) {
    const flags = rawArrayFlags(fn.params);
    sigs.set(fn.name, { arrPos: new Set(flags.map((f, i) => (f ? i : -1)).filter((i) => i >= 0)) });
  }
  return sigs;
}
let globalSigs = null;

function paramTypeFor(p, ctx) {
  if (!ctx || !ctx.paramTypes || !ctx.paramTypes[p]) return 'long long';
  const t = ctx.paramTypes[p];
  if (t === 'str') return 'const char *';
  if (t === 'cb') return 'char *';
  if (t === 'arr') return 'long long *';
  return 'long long';
}

/** Positional array-flags + clean names from raw param text. */
function rawArrayFlags(rawParams) {
  return String(rawParams || '')
    .split(',')
    .map((p) => /\[\s*\]\s*$/.test(p.trim()));
}

/** Positional type markers from raw param text: `p:s` const char*, `p:cb` mutable char*. */
function rawTypeMarkers(rawParams) {
  return String(rawParams || '')
    .split(',')
    .map((p) => {
      const m = p.trim().match(/:\s*(s|cb)\s*(\[\s*\])?\s*$/);
      if (!m) return '';
      return m[1];
    });
}

/**
 * parseLia() strips `name:type` suffixes, so recover type markers by
 * re-scanning the raw source signatures:  !fname(p:s, q:cb[], r[])
 */
function sigMarkersByFn(liaText) {
  const map = new Map();
  const re = /(?:^|[;!{;\n])\s*!([A-Za-z_$][\w$]*)\s*\(([^)]*)\)/g;
  let m;
  while ((m = re.exec(String(liaText || '')))) {
    map.set(m[1], rawTypeMarkers(m[2]));
  }
  return map;
}

function rawParamNamesClean(rawParams) {
  return String(rawParams || '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => safeEmitId(p.replace(/\[\s*\]\s*$/, '').replace(/^([A-Za-z_$][\w$]*)\s*=.*$/, '$1').replace(/\?$/, '').trim()));
}

export function emitC(liaText, opts = {}) {
  const prog = parseLia(liaText);
  const parts = [
    '/* generated by lia multi-emit → c */',
    '#include <stdio.h>',
    '#include <stdlib.h>',
    '#include <string.h>',
    '#include <stdbool.h>',
    '',
    'static const char *_lia_typeof(long long x) { (void)x; return "number"; }',
    'static int _lia_instanceof(long long x) { (void)x; return 0; }',
    'static void _lia_set(long long o, const char *k) { (void)o; (void)k; }',
    'static int _lia_isfinite(long long x) { (void)x; return 1; }',
    'static int _lia_isnan(long long x) { (void)x; return 0; }',
    'static char *_lia_cat_c(const char *a, const char *b) {',
    '  const char *x = a ? a : "";',
    '  const char *y = b ? b : "";',
    '  size_t n = strlen(x) + strlen(y) + 1;',
    '  char *out = (char *)malloc(n);',
    '  if (!out) return NULL;',
    '  snprintf(out, n, "%s%s", x, y);',
    '  return out;',
    '}',
    'static char *_lia_sprintf_ll(const char *fmt, long long v) {',
    '  char *buf = (char *)malloc(64);',
    '  if (!buf) return NULL;',
    '  if (fmt && strstr(fmt, "kb")) snprintf(buf, 64, "%lldkb", v);',
    '  else if (fmt && strstr(fmt, "mb")) snprintf(buf, 64, "%lldmb", v);',
    '  else if (fmt && strstr(fmt, "gb")) snprintf(buf, 64, "%lldgb", v);',
    '  else snprintf(buf, 64, "%lldb", v);',
    '  return buf;',
    '}',
    'static const char *_lia_or_c(const char *a, const char *b) {',
    '  if (a && a[0]) return a;',
    '  return b ? b : "";',
    '}',
    '',
  ];
  const fileHosty = opts.stubRuntime === true || opts.fileHosty === true;
  const names = emitNameMap(prog.fns);
  if (fileHosty) {
    for (const k of Object.keys(names)) names[k] = `lfn_${names[k]}`;
  }
  for (const fn of prog.fns) {
    const { defaults } = parseParamList(fn.params);
    const cName = names[fn.name];
    if (fileHosty || (isJsRuntimeOnly(fn.body, fn.name) && opts.stubRuntime !== false)) {
      parts.push(`long long ${cName}(void) { return 0; /* JS-runtime-only */ }`);
      continue;
    }
    const bodySrc = rewriteSafeParamIds(fn.body, rawParamNames(fn.params));
    const stmts = tryParseStmts(bodySrc) || tryParseStmts(fn.body);
    if (!stmts) {
      parts.push(`long long ${cName}(void) { return 0; /* JS-runtime-only */ }`);
      continue;
    }
    const assigned = collectAssignedIds(stmts);
    const types = inferTypes(stmts);
    const { names: paramNames, defaults: defaults2 } = parseParamList(fn.params);
    const rawNames = rawParamNamesClean(fn.params);
    if (rawNames.length === paramNames.length) paramNames.length = 0, paramNames.push(...rawNames);
    void defaults2;
    const arrFlags = rawArrayFlags(fn.params);
    const typeMarkers = sigMarkersByFn(liaText).get(fn.name) || rawTypeMarkers(fn.params);
    if (!globalSigs) globalSigs = buildFnSigs(prog);
    const ctx = buildCtx(paramNames, types, stmts, new Set(prog.fns.map((f) => f.name)), [], globalSigs);
    paramNames.forEach((p, ix2) => {
      if (arrFlags[ix2]) ctx.paramTypes[p] = 'arr';
      if (typeMarkers[ix2] === 's') { ctx.paramTypes[p] = 'str'; ctx.strIds.add(p); }
      if (typeMarkers[ix2] === 'cb') { ctx.paramTypes[p] = 'cb'; ctx.strIds.add(p); }
    });
    const paramList = paramNames.length
      ? paramNames.map((p) => `${paramTypeFor(p, ctx)} ${safeEmitId(p)}`).join(', ')
      : 'void';
    const locals = assigned.filter((id) => !paramNames.includes(id) && !ctx.arrays.has(id));
    const extraArrDecls = [];
    if (ctx.dynArrays) for (const [id, da] of ctx.dynArrays) extraArrDecls.push(`  long long ${id}[${da.len}];`);
    if (ctx.arrLocals) for (const [id, n] of ctx.arrLocals) {
      if (!ctx.dynArrays.has(id) && !paramNames.includes(id)) extraArrDecls.push(`  long long ${id}[${n}] = {0};`);
    }
    const decls = [...extraArrDecls,
      ...locals.filter((id) => !(ctx.arrLocals && ctx.arrLocals.has(id))).map((id) => {
        if (ctx.strIds.has(id)) return `  const char *${id} = NULL;`;
        return `  long long ${id} = 0;`;
      })];
    const mutatedArr = new Set();
    {
      (function walkM(list) {
        for (const q of list || []) {
          const im = String(q.id || '').match(/^([A-Za-z_]\w*)\[/);
          if (q.type === 'assign' && im) mutatedArr.add(im[1]);
          walkM(q.then); walkM(q.elseIf?.map((e) => e.body)); walkM(q.else); walkM(q.body);
        }
      })(stmts);
      let mm2;
      const cre = /\b([A-Za-z_]\w*)\s*\(([^()]*?)\)/g;
      const texts = [];
      (function tw(list) {
        for (const q of list || []) {
          texts.push(q.expr || '', q.cond || '', q.init || '', q.step || '');
          tw(q.then); tw(q.elseIf?.map((e) => e.body)); tw(q.else); tw(q.body);
        }
      })(stmts);
      for (const tx of texts) {
        if (!tx) continue;
        cre.lastIndex = 0;
        while ((mm2 = cre.exec(tx))) {
          const sig = globalSigs ? globalSigs.get(mm2[1]) : null;
          if (!sig || !sig.arrPos.size) continue;
          const args2 = mm2[2].split(',');
          for (const pos of sig.arrPos) {
            if (pos < args2.length) {
              const aid = args2[pos].trim();
              if (/^[A-Za-z_]\w*$/.test(aid)) mutatedArr.add(aid);
            }
          }
        }
      }
    }
    ctx.mutatedArr = mutatedArr;
    const cacheStub = /\bcache\b/.test(fn.body) ? ['  const char *cache[64] = {0};'] : [];
    const bodyLines = [...cacheStub, ...decls, ...emitNilDefaults(defaults, 'c'), ...emitStmts(stmts, 1, ctx)];
    const retIsStr = /asprintf|_lia_sprintf|bytes_to_string/.test(fn.name + fn.body)
      || fn.name.includes('to_string') || fn.name.includes('ToString')
      || /leftPad|pad|join|trim/i.test(fn.name)
      || ctx.retStr === true;
    const ret = retIsStr ? 'const char *' : 'long long';
    parts.push(`${ret} ${cName}(${paramList}) {\n${bodyLines.join('\n')}\n}`);
  }
  if (isQualityFnSet(prog.fns.map((f) => f.name))) {
    parts.push(formatQualityMain('c', names));
  } else if (opts.withMain === true) {
    const primary = prog.exports[0] || prog.fns[0]?.name || 'main_fn';
    parts.push(`int main(void) { printf("ok %s\\n", "${primary}"); return 0; }`);
  }
  return { code: `${parts.join('\n')}\n`, program: prog, target: 'c' };
}
