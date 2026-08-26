/**
 * LIA → Rust emitter (MVP; ALWAYS_INSTALL rustc via ensure_toolchains).
 */
import { parseLia } from './compiler.mjs';
import { parseStmts, tryParseStmts, collectAssignedIds } from './body_ast.mjs';
import { isJsRuntimeOnly, rewriteExpr, snakeCase, splitPrefixIncCond, emitCond, assignOpLine, isNumishId, isStringishId, isBoolishId, inferTypes, parseParamList, rewriteFnValues, safeEmitId, isNoopExpr, collectFreeHostIds, emitFreeHostDecls, isBoolFnName } from './emit_shared.mjs';
import { rawParamNames, rewriteSafeParamIds } from './emit_safe_ids_load.mjs';
import { emitThrowLine, rewriteSiblingCalls } from './emit_rewrite.mjs';
import { isQualityFnSet, wantSafeCompareMain, formatQualityMain } from './emit_entry_main_load.mjs';

function emitStmts(stmts, indent, types, retType) {
  const pad = '    '.repeat(indent);
  const lines = [];
  for (const st of stmts) {
    if (st.type === 'assign') {
      lines.push(assignOpLine(st.id, st.op, st.expr, 'rust', pad, types));
    } else if (st.type === 'return') {
      const e = rewriteExpr(st.expr, 'rust');
      if (retType === 'String') {
        if (/_lia_arr\(/.test(e)) lines.push(`${pad}return ${e};`);
        else if (/^\(?\s*\[/.test(String(st.expr || '').trim()) || /^\(?\s*\[/.test(String(e || '').trim())) {
          lines.push(`${pad}return format!("{:?}", ${e});`);
        } else {
          lines.push(`${pad}return _lia_val(${e});`);
        }
      } else {
        lines.push(`${pad}return ${e};`);
      }
    } else if (st.type === 'throw') {
      lines.push(emitThrowLine(st.expr, 'rust', pad, rewriteExpr));
    } else if (st.type === 'expr') {
      if (/^break\b/.test(st.expr.trim())) lines.push(`${pad}break;`);
      else if (/^throw\b/.test(st.expr.trim())) lines.push(emitThrowLine(st.expr, 'rust', pad, rewriteExpr));
      else if (/^[A-Za-z_][\w]*$/.test(st.expr.trim())) continue;
      else if (isNoopExpr(st.expr) || /String::new\(\)/.test(rewriteExpr(st.expr, 'rust'))) continue;
      else lines.push(`${pad}${rewriteExpr(st.expr, 'rust')};`);
    } else if (st.type === 'if') {
      lines.push(`${pad}if ${emitCond(st.cond, 'rust')} {`);
      lines.push(...emitStmts(st.then, indent + 1, types, retType));
      for (const e of st.elseIf || []) {
        lines.push(`${pad}} else if ${emitCond(e.cond, 'rust')} {`);
        lines.push(...emitStmts(e.body, indent + 1, types, retType));
      }
      if (st.else) {
        lines.push(`${pad}} else {`);
        lines.push(...emitStmts(st.else, indent + 1, types, retType));
      }
      lines.push(`${pad}}`);
    } else if (st.type === 'for') {
      const init = st.init.match(/^([A-Za-z_][\w]*)\s*=\s*(.+)$/);
      const stepInc = st.step.match(/^([A-Za-z_][\w]*)\+\+$/);
      if (init && stepInc) {
        const le = st.cond.match(/^([A-Za-z_][\w]*)\s*<=\s*(.+)$/);
        if (le && le[1] === init[1]) {
          lines.push(`${pad}for ${init[1]} in ${rewriteExpr(init[2], 'rust')}..=${rewriteExpr(le[2], 'rust')} {`);
          lines.push(...emitStmts(st.body, indent + 1, types, retType));
          lines.push(`${pad}}`);
          continue;
        }
        const cm = st.cond.match(/^([A-Za-z_][\w]*)\s*<\s*(.+)$/);
        if (cm && cm[1] === init[1]) {
          lines.push(`${pad}for ${init[1]} in ${rewriteExpr(init[2], 'rust')}..${rewriteExpr(cm[2], 'rust')} {`);
          lines.push(...emitStmts(st.body, indent + 1, types, retType));
          lines.push(`${pad}}`);
          continue;
        }
      }
      lines.push(`${pad}// LIA_EMIT_RUST: fallback C-for as loop`);
      if (init) lines.push(`${pad}let mut ${init[1]} = ${rewriteExpr(init[2], 'rust')};`);
      lines.push(`${pad}while ${rewriteExpr(st.cond, 'rust')} {`);
      lines.push(...emitStmts(st.body, indent + 1, types, retType));
      if (stepInc) lines.push(`${pad}    ${stepInc[1]} += 1;`);
      else lines.push(`${pad}    ${rewriteExpr(st.step, 'rust')};`);
      lines.push(`${pad}}`);
    } else if (st.type === 'while') {
      const inc = splitPrefixIncCond(st.cond);
      if (inc) {
        lines.push(`${pad}loop {`);
        lines.push(`${pad}    ${inc.id} += 1;`);
        lines.push(`${pad}    if !(${inc.id} ${inc.op} ${rewriteExpr(inc.rhs, 'rust')}) { break; }`);
        lines.push(...emitStmts(st.body, indent + 1, types, retType));
        lines.push(`${pad}}`);
      } else if (String(st.cond).trim() === 'true') {
        lines.push(`${pad}loop {`);
        lines.push(...emitStmts(st.body, indent + 1, types, retType));
        lines.push(`${pad}}`);
      } else {
        lines.push(`${pad}while ${emitCond(st.cond, 'rust')} {`);
        lines.push(...emitStmts(st.body, indent + 1, types, retType));
        lines.push(`${pad}}`);
      }
    } else if (st.type === 'match') {
      const matchTarget = rewriteExpr(st.expr, 'rust');
      lines.push(`${pad}match ${matchTarget} {`);
      for (const arm of st.arms || []) {
        const guardStr = arm.guard ? ` if ${emitCond(arm.guard, 'rust')}` : '';
        let armPat = arm.pat;
        if (armPat === '_') armPat = '_';
        lines.push(`${pad}    ${armPat}${guardStr} => {`);
        lines.push(...emitStmts(arm.body, indent + 2, types, retType));
        lines.push(`${pad}    }`);
      }
      lines.push(`${pad}}`);
    }
  }
  return lines;
}

/** Clean a LIN type annotation for Rust: map int/bool and strip refinement braces (int{!=0} -> i64). */
function cleanRustType(rawT) {
  return String(rawT || '').replace(/\{[^}]*\}/g, '').replace(/\bint\b/g, 'i64').replace(/\bbool\b/g, 'bool').trim();
}

function rustType(id, inferred) {
  if (inferred && inferred.has(id)) {
    const t = inferred.get(id);
    if (t === 'string' || t === 'String') return 'String';
    if (t === 'int' || t === 'i32' || t === 'i64') return 'i64';
    if (t === 'bool') return 'bool';
    return t;
  }
  if (isNumishId(id)) return 'i64';
  if (isBoolishId(id)) return 'bool';
  if (isStringishId(id)) return 'String';
  return 'String';
}

function rustDefault(ty) {
  if (ty === 'i64' || ty === 'int' || ty === 'i32') return '0';
  if (ty === 'bool') return 'false';
  return 'String::new()';
}

function rustLocals(locals, stmts) {
  const inferred = inferTypes(stmts);
  return locals.map((id) => {
    const sid = safeEmitId(id);
    const ty = rustType(sid, inferred);
    return `    let mut ${sid}: ${ty} = ${rustDefault(ty)};`;
  });
}

function rustRetType(fn, stmts) {
  if (fn && fn.returnType) {
    return cleanRustType(fn.returnType);
  }
  if (isBoolFnName(fn.name)) return 'bool';
  const inf = inferTypes(stmts);
  const rets = [];
  const walk = (list) => {
    for (const st of list || []) {
      if (st.type === 'return') rets.push(String(st.expr || '').trim());
      if (st.then) walk(st.then);
      if (st.else) walk(st.else);
      if (st.body) walk(st.body);
      for (const e of st.elseIf || []) walk(e.body);
    }
  };
  walk(stmts);
  if (!rets.length) return 'String';
  const boolish = (t) => {
    const s = String(t || '').trim();
    return /^(true|false)$/.test(s) || /(==|!=|<=|>=|<|>|&&|\|\||_lia_truthy|_lia_re_test)/.test(s);
  };
  if (isBoolFnName(fn.name) || (rets.length && rets.every(boolish))) return 'bool';
  const looksNumeric = (t) => {
    const s = String(t || '').trim();
    if (/^-?\d+$/.test(s) || inf.get(s) === 'int' || isNumishId(s)) return true;
    if (/^[A-Za-z_][\w]*(\s*[+\-*/%]\s*[A-Za-z_][\w]*)+$/.test(s)) {
      if (/\+/.test(s)) {
        const ids = s.split(/\s*[+\-*/%]\s*/);
        if (ids.some((id) => isStringishId(id) || inf.get(id) === 'string' || inf.get(id) === 'String')) return false;
      }
      return true;
    }
    return false;
  };
  return rets.every(looksNumeric) ? 'i64' : 'String';
}

export function emitRust(liaText, opts = {}) {
  const prog = parseLia(liaText);
  const parts = [
    '// generated by lia multi-emit → rust (MVP)',
    '#![allow(non_snake_case, unused_assignments, unused_variables, unused_parens, unused_mut, dead_code)]',
    'fn _lia_typeof<T>(_x: &T) -> &\'static str { "object" }',
    'fn _lia_instanceof<T>(_x: &T) -> bool { false }',
    'fn _lia_set<T, V>(_o: &T, _k: &str, v: V) -> V { v }',
    'fn _lia_isfinite<T>(_x: &T) -> bool { true }',
    'fn _lia_isnan<T>(_x: T) -> bool { false }',
    'fn _lia_obj() -> String { String::new() }',
    'fn _lia_arr(items: &[&str]) -> String { format!("\\u{1e}{}", items.join("\\u{1f}")) }',
    'fn _lia_len(s: &impl ToString) -> i64 { let t = s.to_string(); if let Some(rest) = t.strip_prefix(\'\\u{1e}\') { if rest.is_empty() { 0 } else { rest.split(\'\\u{1f}\').count() as i64 } } else { t.chars().count() as i64 } }',
    'fn _lia_at(s: &impl ToString, i: i64) -> String { let t = s.to_string(); let u = if i < 0 { 0 } else { i as usize }; if let Some(rest) = t.strip_prefix(\'\\u{1e}\') { rest.split(\'\\u{1f}\').nth(u).unwrap_or("").to_string() } else { t.chars().nth(u).map(|c| c.to_string()).unwrap_or_default() } }',
    'fn _lia_push(s: &mut String, v: impl ToString) { let v = v.to_string(); if s.is_empty() || !s.starts_with(\'\\u{1e}\') { *s = format!("\\u{1e}{}", v); return; } if s.len() == \'\\u{1e}\'.len_utf8() { s.push_str(&v); } else { s.push(\'\\u{1f}\'); s.push_str(&v); } }',
    'fn _lia_index_of(s: &impl ToString, x: impl ToString) -> i64 { let t = s.to_string(); let q = x.to_string(); if let Some(rest) = t.strip_prefix(\'\\u{1e}\') { rest.split(\'\\u{1f}\').position(|p| p == q).map(|i| i as i64).unwrap_or(-1) } else { t.find(&q).map(|i| t[..i].chars().count() as i64).unwrap_or(-1) } }',
    'fn _lia_keys(_o: &impl ToString) -> String { _lia_arr(&[]) }',
    'fn _lia_truthy(s: impl ToString) -> bool { let t = s.to_string(); t != "" && t != "false" && t != "0" && t != "null" && t != "undefined" }',
    'fn _lia_re_test(pat: &str, s: impl ToString) -> bool { let t = s.to_string(); if pat == "\\\\s" { t.chars().any(|c| c.is_whitespace()) } else if pat.contains("[A-Za-z0-9_$]") || pat == "[A-Za-z0-9_$]" { t.chars().any(|c| c.is_ascii_alphanumeric() || c == \'_\' || c == \'$\') } else { t.contains(pat) } }',
    'fn _lia_abs(x: &impl ToString) -> i64 { x.to_string().parse::<i64>().unwrap_or(0).abs() }',
    'fn _lia_round(x: i64) -> i64 { x }',
    'fn _lia_str(x: impl ToString) -> String { x.to_string() }',
    'fn _lia_val(x: impl ToString) -> String { x.to_string() }',
    'fn _lia_cat<A: ToString, B: ToString>(a: &A, b: &B) -> String { format!("{}{}", a.to_string(), b.to_string()) }',
    'fn _lia_num(x: &impl ToString) -> i64 { x.to_string().parse::<i64>().unwrap_or(0) }',
    'fn _lia_or(a: impl ToString, b: impl ToString) -> String { let a = a.to_string(); if a.is_empty() { b.to_string() } else { a } }',
    'fn _lia_get<T>(_o: &T, _k: &str) -> String { String::new() }',
    'fn _lia_includes(s: &impl ToString, x: impl ToString) -> bool { s.to_string().contains(&x.to_string()) }',
    'fn _lia_re_exec<T>(_s: T) -> String { String::new() }',
    'fn _lia_lower(x: impl ToString) -> String { x.to_string() }',
    'fn _lia_cache_get(cache: &[String], i: i32) -> String {',
    '    let u = if i < 0 { 0 } else { i as usize };',
    '    if u < cache.len() { cache[u].clone() } else { String::new() }',
    '}',
  ];
  const fileHosty = opts.stubRuntime === true || opts.fileHosty === true;
  if (prog.consts && !fileHosty) {
    for (const [k, v] of Object.entries(prog.consts)) parts.push(`const ${k}: i64 = ${v};`);
  }
  if (prog.enums && prog.enums.length) {
    for (const en of prog.enums) {
      const genStr = en.generics ? `<${en.generics.slice(1, -1)}>` : '';
      const varLines = (en.variants || []).map((v) => {
        if (v.params) return `    ${v.name}(${v.params}),`;
        return `    ${v.name},`;
      });
      parts.push(`#[derive(Debug, Clone, PartialEq)]\npub enum ${en.name}${genStr} {\n${varLines.join('\n')}\n}`);
    }
  }
  const usedFn = new Set();
  const rustFnName = (raw) => {
    let n = safeEmitId(snakeCase(raw));
    if (usedFn.has(n) || (raw !== n && String(raw).toLowerCase() === n && usedFn.has(n))) {
      n = `${n}_u`;
    }
    if (usedFn.has(n)) n = `${n}${usedFn.size}`;
    usedFn.add(n);
    return n;
  };
  const aliases = Object.fromEntries(prog.fns.map((f) => [f.name, rustFnName(f.name)]));
  usedFn.clear();
  for (const fn of prog.fns) {
    const name = rustFnName(fn.name);
    // Extract generic params from fn.generics like "<T>" or "<T,U>" if present
    const genDecl = fn.generics ? fn.generics.slice(1, -1) : null; // "T" or "T,U"
    const rawNames = rawParamNames(fn.params);
    const { names: params } = parseParamList(fn.params);
    const cleanParamNames = params.map((p) => safeEmitId(String(p).split(':')[0].trim()));
    // Build Rust generic param declaration for function signature
    const genRust = genDecl ? `<${genDecl.split(',').map(g => g.trim()).filter(Boolean).join(', ')}>` : '';
    const paramList = params.map((p, i) => {
      const orig = rawNames[i] || p;
      const cleanName = cleanParamNames[i];
      if (orig.includes(':')) {
        const typePart = cleanRustType(orig.split(':')[1].trim());
        return `${cleanName}: ${typePart}`;
      }
      if (genDecl && genDecl.split(',').map(g=>g.trim()).includes(fn.returnType)) {
        return `${cleanName}: ${fn.returnType}`;
      }
      if (isNumishId(orig) && !/^ms$/i.test(orig)) return `mut ${cleanName}: i64`;
      if (isBoolishId(orig)) return `${cleanName}: bool`;
      return `${cleanName}: impl ToString`;
    }).join(', ');
    const fullParamList = genDecl ? `${genRust}(${paramList})` : `(${paramList})`;
    const coerce = [];
    for (let i = 0; i < params.length; i++) {
      const orig = rawNames[i] || params[i];
      if (orig.includes(':')) continue;
      if (genDecl && genDecl.split(',').map(g=>g.trim()).includes(fn.returnType)) continue;
      if (!(isNumishId(orig) && !/^ms$/i.test(orig)) && !isBoolishId(orig)) {
        coerce.push(`    let mut ${cleanParamNames[i]} = ${cleanParamNames[i]}.to_string();`);
      }
    }
    if (isJsRuntimeOnly(fn.body, fn.name) && opts.stubRuntime !== false) {
      parts.push(
        `pub fn ${name}${genRust}() -> bool {\n    panic!("LIA_EMIT_RUST: JS-runtime-only (${fn.name})");\n}`,
      );
      continue;
    }
    const bodyStmts = tryParseStmts(
      rewriteSafeParamIds(
        rewriteSiblingCalls(
          rewriteFnValues(fn.body, prog.fns.map((f) => f.name).filter((n) => n !== fn.name), 'String::new()'),
          aliases,
        )
          .replace(/\bString\(([A-Za-z_][\w]*)\)/g, '$1.to_string()'),
        rawNames,
      ),
    );
    if (!bodyStmts) {
      parts.push(
        `pub fn ${name}${genRust}() -> bool {\n    panic!("LIA_EMIT_RUST: JS-runtime-only (${fn.name})");\n}`,
      );
      continue;
    }
    const forVars = new Set();
    const collectFor = (list) => {
      for (const st of list || []) {
        if (st.type === 'for') {
          const im = st.init.match(/^([A-Za-z_][\w]*)\s*=/);
          if (im) forVars.add(im[1]);
          collectFor(st.body);
        }
        if (st.type === 'if') {
          collectFor(st.then);
          for (const e of st.elseIf || []) collectFor(e.body);
          if (st.else) collectFor(st.else);
        }
      }
    };
    collectFor(bodyStmts);
    const patternVars = new Set();
    const collectPatVars = (list) => {
      for (const st of list || []) {
        if (st.type === 'match') {
          for (const arm of st.arms || []) {
            const idm = arm.pat.match(/^[A-Za-z_$][\w$]*\(([^)]+)\)$/);
            if (idm) {
              for (const v of idm[1].split(',').map((x) => x.trim())) patternVars.add(v);
            }
            collectPatVars(arm.body);
          }
        }
      }
    };
    collectPatVars(bodyStmts);
    const enumVariantNames = new Set(
      (prog.enums || []).flatMap((e) => (e.variants || []).map((v) => v.name))
    );
    const bodyLocals = collectAssignedIds(bodyStmts).filter(
      (id) => !cleanParamNames.includes(id) && !forVars.has(id) && !patternVars.has(id) && !enumVariantNames.has(id) && id !== 'cache',
    );
    const inferredTypes = inferTypes(bodyStmts);
    const cacheStub = /\bcache\b/.test(fn.body)
      ? ['    let mut cache: Vec<String> = vec![String::new(); 64];']
      : [];
    const retType = rustRetType(fn, bodyStmts);
    const emitted = emitStmts(bodyStmts, 1, inferredTypes, retType);
    if (!/\breturn\b/.test(emitted.join('\n'))) {
      emitted.push(retType === 'bool' ? '    false' : retType === 'i64' ? '    0' : '    String::new()');
    }
    const freeHost = emitFreeHostDecls(collectFreeHostIds(fn.body, params, prog.fns.map((f) => f.name)), 'rust');
    const bodyLines = [...coerce, ...cacheStub, ...freeHost, ...rustLocals(bodyLocals, bodyStmts), ...emitted];
    parts.push(`pub fn ${name}${genRust}(${paramList}) -> ${retType} {\n${bodyLines.join('\n')}\n}`);
  }
  const fnNames = prog.fns.map((f) => f.name);
  if (isQualityFnSet(fnNames)) {
    parts.push(formatQualityMain('rust', aliases));
  } else if (fnNames.includes('hostPickBanner')) {
    const h = (n) => aliases[n] || snakeCase(n);
    parts.push(`
fn main() {
    println!("{}", ${h('hostPickBanner')}());
    println!("{}", ${h('inMemoryHostLang')}());
    println!("{}", ${h('cliEmitDefault')}());
    println!("{}", ${h('cMemoryLabel')}());
    println!("{}", ${h('langMemoryKind')}("c"));
    println!("{}", ${h('langMemoryKind')}("rust"));
}
`);
  } else if (fnNames.includes('coreBanner')) {
    const h = (n) => aliases[n] || snakeCase(n);
    parts.push(`
fn main() {
    println!("{}", ${h('coreBanner')}());
    println!("{}", ${h('coreHostLang')}());
    println!("{}", ${h('cliDefaultLang')}());
    println!("{}", ${h('bootstrapLang')}());
    println!("{}", ${h('gatewayLang')}());
    println!("{}", ${h('unsafeTargetLang')}());
    println!("{}", ${h('phase1Name')}());
    println!("{}", ${h('rank1Lang')}());
    println!("{}", ${h('rank2Lang')}());
    println!("{}", ${h('rank3Lang')}());
}
`);
  } else if (wantSafeCompareMain(opts.withMain, fnNames)) {
    const primary = snakeCase(prog.exports[0] || prog.fns[0]?.name || 'safeCompare');
    parts.push(`
fn main() {
    assert!(${primary}("ab", "ab"));
    assert!(!${primary}("a", "b"));
    assert!(!${primary}("prefix", "pre"));
    assert!(${primary}("", ""));
    println!("ok rust safe-compare");
}`);
  }
  return { code: parts.join('\n') + '\n', program: prog, target: 'rust', stub: opts.stubRuntime !== false };
}
