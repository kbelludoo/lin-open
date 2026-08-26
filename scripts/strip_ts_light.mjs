/**
 * Peripheral TS→JS erase for clone oracle (no LIN nucleus).
 * Brace-aware: strips annotations/generics/as/satisfies/interfaces, keeps values.
 */

function isIdentStart(c) {
  return /[A-Za-z_$]/.test(c || '');
}
function isIdent(c) {
  return /[A-Za-z0-9_$]/.test(c || '');
}

function skipWs(s, i) {
  while (i < s.length && /[\s]/.test(s[i])) i++;
  return i;
}

function skipQuoted(s, i) {
  const q = s[i];
  i++;
  while (i < s.length) {
    if (s[i] === '\\') { i += 2; continue; }
    if (s[i] === q) return i + 1;
    i++;
  }
  return i;
}

function skipLine(s, i) {
  while (i < s.length && s[i] !== '\n') i++;
  return i;
}

function skipBlock(s, i) {
  i += 2;
  while (i < s.length && !(s[i] === '*' && s[i + 1] === '/')) i++;
  return i < s.length ? i + 2 : i;
}

function wordAt(s, i, w) {
  if (!s.startsWith(w, i)) return false;
  const prev = s[i - 1];
  const next = s[i + w.length];
  if (prev && (isIdent(prev) || prev === '.')) return false;
  if (next && isIdent(next)) return false;
  return true;
}

/** Consume a TS type starting at i (already at first type token or ws). */
export function skipTsType(s, i) {
  i = skipWs(s, i);
  let a = 0;
  let p = 0;
  let b = 0;
  let k = 0;
  let started = false;
  let afterTypeOp = true;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') { i = skipQuoted(s, i); started = true; afterTypeOp = false; continue; }
    if (c === '/' && s[i + 1] === '/') { i = skipLine(s, i); continue; }
    if (c === '/' && s[i + 1] === '*') { i = skipBlock(s, i); continue; }
    if (c === '<') { a++; i++; started = true; afterTypeOp = true; continue; }
    if (c === '>' && a) { a--; i++; afterTypeOp = false; continue; }
    if (c === '(') { p++; i++; started = true; afterTypeOp = true; continue; }
    if (c === ')' && p) { p--; i++; afterTypeOp = false; continue; }
    if (c === '{') {
      if (started && !afterTypeOp && !a && !p && !b && !k) break;
      b++; i++; started = true; afterTypeOp = true; continue;
    }
    if (c === '}' && b) { b--; i++; afterTypeOp = false; continue; }
    if (c === '[') { k++; i++; started = true; afterTypeOp = true; continue; }
    if (c === ']' && k) { k--; i++; afterTypeOp = false; continue; }
    if (a || p || b || k) { i++; started = true; continue; }
    if (c === '|' || c === '&') { i++; afterTypeOp = true; continue; }
    if (c === '?' || c === '.' || c === '!') { i++; continue; }
    if (wordAt(s, i, 'extends') || wordAt(s, i, 'keyof') || wordAt(s, i, 'infer')
      || wordAt(s, i, 'typeof') || wordAt(s, i, 'readonly') || wordAt(s, i, 'unique')
      || wordAt(s, i, 'asserts') || wordAt(s, i, 'is')) {
      while (i < s.length && isIdent(s[i])) i++;
      afterTypeOp = true;
      continue;
    }
    if (c === '=' && s[i + 1] === '>') break;
    if (',;=:){}\n'.includes(c)) break;
    if (wordAt(s, i, 'of') || wordAt(s, i, 'in')) break;
    i++;
    started = true;
    afterTypeOp = false;
  }
  return i;
}

function skipGeneric(s, i) {
  if (s[i] !== '<') return i;
  return skipTsType(s, i);
}

function skipTypeArgs(s, i) {
  if (s[i] !== '<') return i;
  let d = 1;
  let j = i + 1;
  while (j < s.length && d > 0) {
    const c = s[j];
    if (c === '"' || c === "'" || c === '`') { j = skipQuoted(s, j); continue; }
    if (c === '\n' && d === 1) return i;
    if (c === '<') d++;
    else if (c === '>') d--;
    j++;
  }
  return d === 0 ? j : i;
}

function skipBalanced(s, i, open, close) {
  if (s[i] !== open) return i;
  let d = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') { i = skipQuoted(s, i); continue; }
    if (c === '/' && s[i + 1] === '/') { i = skipLine(s, i); continue; }
    if (c === '/' && s[i + 1] === '*') { i = skipBlock(s, i); continue; }
    if (c === open) d++;
    else if (c === close) {
      d--;
      i++;
      if (!d) return i;
      continue;
    }
    i++;
  }
  return i;
}

function skipDeclBlock(s, i) {
  i = skipWs(s, i);
  if (s[i] === '<') i = skipGeneric(s, i);
  i = skipWs(s, i);
  if (s[i] === '{') return skipBalanced(s, i, '{', '}');
  while (i < s.length && s[i] !== ';' && s[i] !== '\n') i++;
  if (s[i] === ';') i++;
  return i;
}

function stripParams(s, i, out) {
  if (s[i] !== '(') return i;
  out.push('(');
  i++;
  while (i < s.length && s[i] !== ')') {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const n = skipQuoted(s, i);
      out.push(s.slice(i, n));
      i = n;
      continue;
    }
    if (c === '/' && s[i + 1] === '/') { i = skipLine(s, i); continue; }
    if (c === '/' && s[i + 1] === '*') { i = skipBlock(s, i); continue; }
    if (c === '(') {
      const n = skipBalanced(s, i, '(', ')');
      out.push(s.slice(i, n));
      i = n;
      continue;
    }
    if (c === '{') {
      const n = skipBalanced(s, i, '{', '}');
      out.push(s.slice(i, n));
      i = n;
      continue;
    }
    if (c === '[') {
      const n = skipBalanced(s, i, '[', ']');
      out.push(s.slice(i, n));
      i = n;
      continue;
    }
    if (c === '?') { i++; continue; }
    if (c === ':') { i = skipTsType(s, i + 1); continue; }
    if (wordAt(s, i, 'public') || wordAt(s, i, 'private') || wordAt(s, i, 'protected')
      || wordAt(s, i, 'readonly') || wordAt(s, i, 'override') || wordAt(s, i, 'abstract')) {
      while (i < s.length && isIdent(s[i])) i++;
      i = skipWs(s, i);
      continue;
    }
    out.push(c);
    i++;
  }
  if (s[i] === ')') { out.push(')'); i++; }
  return i;
}

export function stripTsTypes(src) {
  const s = String(src || '');
  const out = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const n = skipQuoted(s, i);
      out.push(s.slice(i, n));
      i = n;
      continue;
    }
    if (c === '/' && s[i + 1] === '/') { i = skipLine(s, i); continue; }
    if (c === '/' && s[i + 1] === '*') { i = skipBlock(s, i); continue; }
    if (c === '/' && !'*/'.includes(s[i + 1] || '')) {
      let p = i - 1;
      while (p >= 0 && /\s/.test(s[p])) p--;
      const prev = p >= 0 ? s[p] : '';
      let prevKw = false;
      if (isIdent(prev)) {
        let k = p;
        while (k >= 0 && isIdent(s[k])) k--;
        prevKw = /^(return|throw|case|typeof|delete|void|new|in|of|instanceof|else|await)$/.test(s.slice(k + 1, p + 1));
      }
      if (!prev || prevKw || /[=(:,!&|?{};[+~%^<>\n]/.test(prev)) {
        let j = i + 1;
        let inClass = false;
        let ok = false;
        while (j < s.length) {
          if (s[j] === '\\') { j += 2; continue; }
          if (s[j] === '\n') break;
          if (s[j] === '[' && !inClass) { inClass = true; j++; continue; }
          if (s[j] === ']' && inClass) { inClass = false; j++; continue; }
          if (s[j] === '/' && !inClass) { j++; ok = true; break; }
          j++;
        }
        if (ok) {
          while (j < s.length && /[gimsuvyd]/.test(s[j])) j++;
          out.push(s.slice(i, j));
          i = j;
          continue;
        }
      }
    }

    if (wordAt(s, i, 'import') && /\s+type\b/.test(s.slice(i + 6, i + 16))) {
      while (i < s.length && s[i] !== ';' && s[i] !== '\n') i++;
      if (s[i] === ';') i++;
      continue;
    }
    if (wordAt(s, i, 'export') && /\s+type\b/.test(s.slice(i + 6, i + 16))) {
      i += 6;
      i = skipWs(s, i);
      continue;
    }
    if (wordAt(s, i, 'export') && /\s+interface\b/.test(s.slice(i + 6, i + 20))) {
      i += 6;
      i = skipWs(s, i);
      continue;
    }
    if (wordAt(s, i, 'interface') || (wordAt(s, i, 'type') && /[\s<]/.test(s[i + 4] || ''))) {
      const isType = wordAt(s, i, 'type');
      i += isType ? 4 : 9;
      i = skipWs(s, i);
      while (i < s.length && isIdent(s[i])) i++;
      i = skipDeclBlock(s, i);
      continue;
    }
    if (wordAt(s, i, 'enum')) {
      i += 4;
      i = skipWs(s, i);
      const start = i;
      while (i < s.length && isIdent(s[i])) i++;
      const name = s.slice(start, i);
      i = skipWs(s, i);
      if (s[i] === '{') {
        const n = skipBalanced(s, i, '{', '}');
        out.push(`const ${name}=`);
        out.push(s.slice(i, n));
        i = n;
        continue;
      }
      continue;
    }
    if (wordAt(s, i, 'declare')) {
      while (i < s.length && s[i] !== ';' && s[i] !== '\n' && s[i] !== '{') i++;
      if (s[i] === '{') i = skipBalanced(s, i, '{', '}');
      else if (s[i] === ';') i++;
      continue;
    }
    if (wordAt(s, i, 'as') || wordAt(s, i, 'satisfies')) {
      const w = wordAt(s, i, 'as') ? 2 : 10;
      const j = skipWs(s, i + w);
      if (wordAt(s, i, 'as') && isIdentStart(s[j])) {
        let k = j;
        while (k < s.length && isIdent(s[k])) k++;
        const after = skipWs(s, k);
        const tail = out.join('').slice(-120);
        const importish = /\b(?:import|export)\b[\s\S]*$/.test(tail);
        if (importish && (s[after] === ',' || s[after] === '}' || wordAt(s, after, 'from'))) {
          out.push(s.slice(i, k));
          i = k;
          continue;
        }
      }
      if (wordAt(s, j, 'const')) {
        i = j + 5;
        continue;
      }
      i = skipTsType(s, j);
      continue;
    }
    if (wordAt(s, i, 'public') || wordAt(s, i, 'private') || wordAt(s, i, 'protected')
      || wordAt(s, i, 'readonly') || wordAt(s, i, 'override') || wordAt(s, i, 'abstract')) {
      while (i < s.length && isIdent(s[i])) i++;
      i = skipWs(s, i);
      continue;
    }

    if (wordAt(s, i, 'async')) {
      out.push('async');
      i += 5;
      continue;
    }
    if (wordAt(s, i, 'function')) {
      const sigAt = out.length;
      out.push(s.slice(i, i + 8));
      i += 8;
      const afterFn = skipWs(s, i);
      out.push(s.slice(i, afterFn) || ' ');
      i = afterFn;
      if (s[i] === '*') {
        out.push('*');
        i += 1;
        const afterStar = skipWs(s, i);
        out.push(s.slice(i, afterStar));
        i = afterStar;
      }
      if (isIdentStart(s[i])) {
        const n = i;
        while (i < s.length && isIdent(s[i])) i++;
        out.push(s.slice(n, i));
      }
      i = skipWs(s, i);
      if (s[i] === '<') i = skipGeneric(s, i);
      i = skipWs(s, i);
      i = stripParams(s, i, out);
      i = skipWs(s, i);
      if (s[i] === ':') i = skipTsType(s, i + 1);
      i = skipWs(s, i);
      if (s[i] === ';') {
        out.length = sigAt;
        i++;
      }
      continue;
    }

    if (wordAt(s, i, 'const') || wordAt(s, i, 'let') || wordAt(s, i, 'var')) {
      const kw = wordAt(s, i, 'const') ? 'const' : wordAt(s, i, 'let') ? 'let' : 'var';
      out.push(kw);
      i += kw.length;
      const afterKw = skipWs(s, i);
      out.push(s.slice(i, afterKw));
      i = afterKw;
      if (s[i] === '{' || s[i] === '[') {
        const n = s[i] === '{' ? skipBalanced(s, i, '{', '}') : skipBalanced(s, i, '[', ']');
        out.push(s.slice(i, n));
        i = n;
      } else if (isIdentStart(s[i])) {
        const n = i;
        while (i < s.length && isIdent(s[i])) i++;
        out.push(s.slice(n, i));
      }
      const afterBind = skipWs(s, i);
      out.push(s.slice(i, afterBind));
      i = afterBind;
      if (s[i] === '!') i++;
      i = skipWs(s, i);
      if (s[i] === ':') i = skipTsType(s, i + 1);
      const afterTy = skipWs(s, i);
      out.push(s.slice(i, afterTy));
      i = afterTy;
      const forIter = wordAt(s, i, 'of') || wordAt(s, i, 'in');
      if (!forIter && s[i] !== '=' && s[i] !== ',' && s[i] !== ';' && s[i] !== '\n' && kw === 'const') {
        out.push('=undefined');
      } else if (!forIter && s[i] !== '=' && kw === 'const' && (s[i] === ';' || s[i] === '\n' || !s[i])) {
        out.push('=undefined');
      }
      continue;
    }

    if (c === '=' && s[skipWs(s, i + 1)] === '<') {
      out.push('=');
      i = skipWs(s, i + 1);
      const after = skipGeneric(s, i);
      const k = skipWs(s, after);
      if (s[k] === '(') { i = after; continue; }
      out.push(s.slice(i, after));
      i = after;
      continue;
    }

    if (c === '(') {
      const n = skipBalanced(s, i, '(', ')');
      let k = skipWs(s, n);
      if (s[k] === ':') k = skipTsType(s, k + 1);
      k = skipWs(s, k);
      if (s[k] === '=' && s[k + 1] === '>') {
        i = stripParams(s, i, out);
        i = skipWs(s, i);
        if (s[i] === ':') i = skipTsType(s, i + 1);
        continue;
      }
      out.push('(');
      i++;
      continue;
    }

    if (isIdentStart(c) && (i === 0 || !isIdent(s[i - 1]))) {
      const n = i;
      while (i < s.length && isIdent(s[i])) i++;
      out.push(s.slice(n, i));
      if (s[i] === '<') {
        const after = skipTypeArgs(s, i);
        const k = skipWs(s, after);
        if (after !== i && (s[k] === '(' || s[k] === '.' || s[k] === ';' || s[k] === ')' || s[k] === ',')) i = after;
      }
      continue;
    }

    if (c === ')' ) {
      out.push(')');
      i++;
      const j = skipWs(s, i);
      if (s[j] === ':') {
        const after = skipTsType(s, j + 1);
        const k = skipWs(s, after);
        if (s[k] === '{' || (s[k] === '=' && s[k + 1] === '>')) {
          i = after;
          continue;
        }
      }
      continue;
    }

    if (c === '?' && s[i + 1] === '.') { out.push('?.'); i += 2; continue; }
    if (c === '?' && s[i + 1] === '?') { out.push('??'); i += 2; continue; }
    if (c === '!' && /[.;,)\]\}\[]/.test(s[i + 1] || '')) { i++; continue; }

    out.push(c);
    i++;
  }
  return out.join('');
}
