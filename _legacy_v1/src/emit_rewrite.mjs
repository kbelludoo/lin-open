/**
 * Peripheral rewrite helpers for multi-emit (not nucleus).
 * throw / IIFE / Math / JSON / regex / balanced new / sibling calls.
 */

export function matchParen(s, openIdx) {
  let depth = 0;
  let quote = null;
  for (let i = openIdx; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === '\\') { i++; continue; }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'") { quote = c; continue; }
    if (c === '(') depth++;
    else if (c === ')') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

export function rewriteIifeTernary(s) {
  let t = String(s || '');
  const patterns = [
    /\(\(__c\)=>\{\?\(__c\)\{return\(([\s\S]*?)\)\}\s*;return\(([\s\S]*?)\)\}\)\(([\s\S]*?)\)/,
    /\(\(__c\)=>\{if\(__c\)\{return\(([\s\S]*?)\)\}\s*;return\(([\s\S]*?)\)\}\)\(([\s\S]*?)\)/,
    /\(\(__c\)=>\{if\(__c\)return\(([\s\S]*?)\);return\(([\s\S]*?)\)\}\)\(([\s\S]*?)\)/,
  ];
  let prev;
  do {
    prev = t;
    for (const re of patterns) t = t.replace(re, '($3?$1:$2)');
  } while (t !== prev);
  return t;
}

export function rewriteNewCalls(s) {
  let t = String(s || '');
  let out = '';
  let i = 0;
  while (i < t.length) {
    const m = t.slice(i).match(/\bnew\s+[A-Za-z_][\w]*/);
    if (!m || m.index == null) {
      out += t.slice(i);
      break;
    }
    out += t.slice(i, i + m.index);
    let j = i + m.index + m[0].length;
    while (j < t.length && /\s/.test(t[j])) j++;
    if (t[j] === '(') {
      const close = matchParen(t, j);
      if (close >= 0) {
        out += '_lia_obj()';
        i = close + 1;
        continue;
      }
    }
    out += '_lia_obj()';
    i = i + m.index + m[0].length;
  }
  return out;
}

export function extractThrowArg(expr) {
  let s = String(expr || '').replace(/^\s*throw\s+/, '').trim();
  const nm = s.match(/^new\s+[A-Za-z_][\w]*\s*\(/);
  if (nm) {
    const open = nm[0].length - 1;
    const close = matchParen(s, open);
    if (close >= 0) {
      let inner = s.slice(open + 1, close).trim().replace(/,\s*$/, '');
      while (inner.startsWith('(') && inner.endsWith(')')) inner = inner.slice(1, -1).trim();
      return inner || '""';
    }
  }
  return s || '""';
}

export function emitThrowLine(raw, target, pad, rewrite) {
  const msg = rewrite(extractThrowArg(raw), target);
  if (target === 'py') return `${pad}raise RuntimeError(${msg})`;
  if (target === 'go') return `${pad}panic(${msg})`;
  if (target === 'rust') return `${pad}panic!("{}", ${JSON.stringify(String(extractThrowArg(raw)).slice(0, 80))});`;
  if (target === 'java') return `${pad}throw new RuntimeException(String.valueOf(${msg}));`;
  if (target === 'c') return `${pad}abort();`;
  return `${pad}throw ${msg};`;
}

export function rewriteSiblingCalls(s, aliases) {
  let t = String(s || '');
  for (const [from, to] of Object.entries(aliases || {})) {
    if (!from || from === to) continue;
    t = t.replace(new RegExp(`\\b${from}\\b`, 'g'), to);
  }
  return t;
}

/** Rewrite `(cond?a:b)` with paren-aware scan. `to(cond,a,b)` returns replacement. */
export function rewriteTernaries(s, to) {
  let t = String(s || '');
  for (let guard = 0; guard < 16; guard++) {
    const hit = findTernary(t);
    if (!hit) break;
    t = t.slice(0, hit.open) + to(hit.cond, hit.a, hit.b) + t.slice(hit.close + 1);
  }
  return t;
}

function findTernary(s) {
  for (let i = 0; i < s.length; i++) {
    if (s[i] !== '(') continue;
    let depth = 0;
    let q = null;
    let qm = -1;
    let col = -1;
    for (let j = i; j < s.length; j++) {
      const c = s[j];
      if (q) {
        if (c === '\\') { j++; continue; }
        if (c === q) q = null;
        continue;
      }
      if (c === '"' || c === "'") { q = c; continue; }
      if (c === '(') depth++;
      else if (c === ')') {
        depth--;
        if (depth === 0) {
          if (qm > i && col > qm) {
            return {
              open: i,
              close: j,
              cond: s.slice(i + 1, qm).trim(),
              a: s.slice(qm + 1, col).trim(),
              b: s.slice(col + 1, j).trim(),
            };
          }
          break;
        }
      } else if (c === '?' && depth === 1 && qm < 0) qm = j;
      else if (c === ':' && depth === 1 && qm >= 0 && col < 0) col = j;
    }
  }
  return null;
}

/** Fold `a + b` at paren-depth 0 into `wrap(a,b)`. Unwraps outer parens first. */
export function foldPlus(s, wrap) {
  let t = String(s || '').trim();
  let wraps = 0;
  while (t.startsWith('(') && matchParen(t, 0) === t.length - 1) {
    t = t.slice(1, -1).trim();
    wraps++;
  }
  for (let guard = 0; guard < 16; guard++) {
    const hit = findPlus(t);
    if (!hit) break;
    if (/^-?\d/.test(hit.a.trim()) && /^-?\d/.test(hit.b.trim())) break;
    const out = wrap(hit.a, hit.b);
    if (out == null) break;
    t = t.slice(0, hit.left) + out + t.slice(hit.right);
  }
  while (wraps--) t = `(${t})`;
  return t;
}

function findPlus(s) {
  let depth = 0;
  let q = null;
  let minD = Infinity;
  let at = -1;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === '\\') { i++; continue; }
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'") { q = c; continue; }
    if (c === '(') depth++;
    else if (c === ')') depth--;
    else if (c === '+' && depth < minD) {
      minD = depth;
      at = i;
    }
  }
  if (at < 0) return null;
  let left = 0;
  depth = 0;
  q = null;
  for (let i = 0; i < at; i++) {
    const c = s[i];
    if (q) {
      if (c === '\\') { i++; continue; }
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'") { q = c; continue; }
    if (c === '(') depth++;
    else if (c === ')') depth--;
    else if (c === '+' && depth === minD) left = i + 1;
  }
  let right = s.length;
  depth = minD;
  q = null;
  for (let i = at + 1; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === '\\') { i++; continue; }
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'") { q = c; continue; }
    if (c === '(') depth++;
    else if (c === ')') {
      depth--;
      if (depth < minD) { right = i; break; }
    } else if (c === '+' && depth === minD) {
      right = i;
      break;
    }
  }
  return { left, right, a: s.slice(left, at).trim(), b: s.slice(at + 1, right).trim() };
}

/** `id.method(...)` → `id` (compile stub; matchParen-safe). */
export function dropMethodsKeepRecv(s, names) {
  const t = String(s || '');
  if (!names?.length) return t;
  const re = new RegExp(`([A-Za-z_][\\w]*)\\s*\\.\\s*(?:${names.join('|')})\\s*\\(`, 'g');
  let out = '';
  let i = 0;
  let m;
  while ((m = re.exec(t))) {
    out += t.slice(i, m.index) + m[1];
    const open = m.index + m[0].length - 1;
    const close = matchParen(t, open);
    if (close < 0) return out + t.slice(m.index + m[1].length);
    i = close + 1;
    re.lastIndex = i;
  }
  return out + t.slice(i);
}

/** `id.replace(/re/, …).replace(…)` → `id` (compile stub; matchParen-safe). */
export function dropRegexMethods(s) {
  let t = String(s || '');
  t = t.replace(
    /([A-Za-z_][\w]*)\.match\s*\(\s*\/(?:\\\/|[^/\n])*\/[gimsuy]*\s*\)/g,
    '_lia_re_exec($1)',
  );
  let out = '';
  let i = 0;
  const re = /([A-Za-z_][\w]*)\s*\.\s*replace\s*\(/g;
  let m;
  while ((m = re.exec(t))) {
    out += t.slice(i, m.index) + m[1];
    const open = m.index + m[0].length - 1;
    const close = matchParen(t, open);
    if (close < 0) {
      out += t.slice(m.index + m[1].length);
      return out;
    }
    let j = close + 1;
    while (true) {
      let k = j;
      while (k < t.length && /\s/.test(t[k])) k++;
      const chained = t.slice(k).match(/^\.\s*replace\s*\(/);
      if (!chained) break;
      const c = matchParen(t, k + chained[0].length - 1);
      if (c < 0) break;
      j = c + 1;
    }
    i = j;
    re.lastIndex = i;
  }
  return out + t.slice(i);
}

function collapseCall(s, needle, repl) {
  let out = '';
  let i = 0;
  while (i < s.length) {
    const at = s.indexOf(needle, i);
    if (at < 0) return out + s.slice(i);
    out += s.slice(i, at) + repl;
    const close = matchParen(s, at + needle.length - 1);
    if (close < 0) return out + s.slice(at + needle.length);
    i = close + 1;
  }
  return out;
}

/** `_lia_get(x,"p").foo.bar()` and unknown `t.stringLiteral(...)` → `_lia_obj()`. */
export function collapseHostChains(s) {
  let t = String(s || '');
  t = t.replace(
    /\b[A-Za-z_][\w]*\.(?!slice\b|split\b|join\b|indexOf\b|includes\b|charCodeAt\b|replace\b|match\b|substring\b|substr\b|trim\b|toLowerCase\b|toString\b|to_string\b|concat\b|push\b|map\b|filter\b|startsWith\b|endsWith\b|lastIndexOf\b|length\b|is_empty\b|clone\b|len\b|as_bytes\b|chars\b|contains\b)[A-Za-z_][\w]*\s*\(/g,
    '_lia_obj(',
  );
  let out = '';
  let i = 0;
  const re = /_lia_[A-Za-z0-9_]+\(/g;
  let m;
  while ((m = re.exec(t))) {
    const at = m.index;
    const close = matchParen(t, at + m[0].length - 1);
    if (close < 0) break;
    out += t.slice(i, at);
    const call = t.slice(at, close + 1);
    let j = close + 1;
    while (true) {
      let k = j;
      while (k < t.length && /\s/.test(t[k])) k++;
      if (t[k] !== '.') break;
      k++;
      while (k < t.length && /\s/.test(t[k])) k++;
      const id = t.slice(k).match(/^[A-Za-z_][\w]*/);
      if (!id) break;
      k += id[0].length;
      while (k < t.length && /\s/.test(t[k])) k++;
      if (t[k] === '(') {
        const c = matchParen(t, k);
        if (c < 0) break;
        j = c + 1;
      } else if (t[k] === '[') {
        const c = t.indexOf(']', k);
        if (c < 0) break;
        j = c + 1;
      } else {
        j = k;
      }
    }
    out += j > close + 1 ? '_lia_obj()' : call;
    i = j;
    re.lastIndex = i;
  }
  return collapseCall(out + t.slice(i), '_lia_obj(', '_lia_obj()');
}

export function rewriteHostExpr(s, target) {
  let t = rewriteIifeTernary(s);
  t = t.replace(/\bMath\.abs\s*\(/g, '_lia_abs(');
  t = t.replace(/\bMath\.round\s*\(/g, '_lia_round(');
  t = t.replace(/\bMath\.(ceil|floor|trunc)\s*\(/g, '_lia_round(');
  t = t.replace(/\bMath\.(min|max)\s*\(([^,)]+),\s*([^)]+)\)/g, '_lia_num($2)');
  t = t.replace(/\bMath\.random\s*\(\s*\)/g, '0');
  t = t.replace(/\bMath\.[A-Za-z0-9]+\s*\(/g, '_lia_num(');
  if (target !== 'js' && target !== 'ts') {
    if (target === 'rust') {
      t = t.replace(/\/((?:\\\/|[^/\n])+)\/[gimsuy]*\.test\s*\(/g, (_, pat) => {
        const p = String(pat).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        return `_lia_re_test("${p}", `;
      });
    }
    t = t.replace(/\b(\d+)\.(\d+)\b/g, (_, a, b) => String(Math.round(Number(`${a}.${b}`))));
    t = t.replace(/(\d+)\s*\*\s*([A-Za-z_][\w]*)/g, '$1*_lia_num($2)');
    t = t.replace(/\b([A-Za-z_][\w]*)\s*\|\s*0\b/g, '_lia_num($1)');
    t = t.replace(/\b([A-Za-z_][\w]*)--\s*>\s*0/g, '$1 > 0');
    // Do NOT rewrite standalone i-- here; let each emitter handle decrement steps
    // t = t.replace(/\b([A-Za-z_][\w]*)--/g, '$1 != 0');
    t = dropRegexMethods(t);
    t = dropMethodsKeepRecv(t, ['slice', 'lastIndexOf', 'split', 'join', 'map', 'filter', 'substring', 'substr', 'evaluate', 'replaceWith']);
    t = t.replace(/([A-Za-z_][\w]*)\.includes\s*\(/g, '_lia_includes($1,');
    t = t.replace(/\/(?:\\\/|[^/\n])+\/[gimsuy]*/g, '""');
    t = t.replace(/\b_\b/g, '_u');
  }
  t = t.replace(/\bJSON\.stringify\s*\(/g, '_lia_str(');
  t = t.replace(/\bparseFloat\s*\(/g, target === 'py' ? 'float(' : '_lia_num(');
  t = t.replace(/\bNaN\b/g, target === 'py' ? "float('nan')" : '0');
  t = t.replace(/\/(?:\\\/|[^/\n])*\/[gimsuy]*\.exec\s*\(/g, '_lia_re_exec(');
  t = t.replace(/_lia_re_exec\(\s*([^,)]+)\s*,\s*\)/g, '_lia_re_exec($1)');
  t = t.replace(/([A-Za-z_][\w]*)\.toLowerCase\s*\(\s*\)/g, '_lia_lower($1)');
  t = rewriteNewCalls(t);
  return t;
}
