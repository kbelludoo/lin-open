/**
 * Parse LIA function bodies into a small statement AST for multi-target emit.
 */
export function findMatching(s, openIdx, openCh, closeCh) {
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
    if (c === openCh) depth++;
    else if (c === closeCh) {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function skipWs(s, i) {
  while (i < s.length && /\s/.test(s[i])) i++;
  return i;
}

function parseBlockBody(s, openBrace) {
  const close = findMatching(s, openBrace, '{', '}');
  if (close < 0) throw new Error('LIA_AST_BRACE');
  return { stmts: parseStmts(s.slice(openBrace + 1, close)), end: close + 1 };
}

/**
 * @returns {import('./emit_shared.mjs').Stmt[]}
 */
export function tryParseStmts(body) {
  try {
    return parseStmts(body);
  } catch {
    return null;
  }
}

export function parseStmts(body) {
  const s = String(body || '');
  const out = [];
  let i = 0;
  while (i < s.length) {
    i = skipWs(s, i);
    if (i >= s.length) break;
    if (s[i] === ';') {
      i++;
      continue;
    }

    if (s.startsWith('?(', i)) {
      const openParen = i + 1;
      const closeParen = findMatching(s, openParen, '(', ')');
      if (closeParen < 0) throw new Error('LIA_AST_IF_PAREN');
      const cond = s.slice(openParen + 1, closeParen);
      let j = skipWs(s, closeParen + 1);
      if (s[j] !== '{') throw new Error('LIA_AST_IF_BRACE');
      const thenB = parseBlockBody(s, j);
      j = thenB.end;
      const elseIf = [];
      let elseStmts = null;
      while (true) {
        j = skipWs(s, j);
        if (s[j] === ';') {
          j = skipWs(s, j + 1);
        }
        if (s.startsWith(':(', j)) {
          const op = j + 1;
          const cp = findMatching(s, op, '(', ')');
          const c2 = s.slice(op + 1, cp);
          let k = skipWs(s, cp + 1);
          if (s[k] !== '{') throw new Error('LIA_AST_ELIF_BRACE');
          const b = parseBlockBody(s, k);
          elseIf.push({ cond: c2, body: b.stmts });
          j = b.end;
          continue;
        }
        if (s.startsWith(':{', j)) {
          const b = parseBlockBody(s, j + 1);
          elseStmts = b.stmts;
          j = b.end;
        }
        break;
      }
      out.push({ type: 'if', cond, then: thenB.stmts, elseIf, else: elseStmts });
      i = j;
      continue;
    }

    if (s.startsWith('while', i) && /^\s*\(/.test(s.slice(i + 5))) {
      const open = s.indexOf('(', i);
      const close = findMatching(s, open, '(', ')');
      if (close < 0) throw new Error('LIA_AST_WHILE_PAREN');
      const cond = s.slice(open + 1, close);
      let j = skipWs(s, close + 1);
      if (s[j] !== '{') throw new Error('LIA_AST_WHILE_BRACE');
      const b = parseBlockBody(s, j);
      out.push({ type: 'while', cond, body: b.stmts });
      i = b.end;
      continue;
    }

    if (s.startsWith('#(', i)) {
      const openParen = i + 1;
      const closeParen = findMatching(s, openParen, '(', ')');
      if (closeParen < 0) throw new Error('LIA_AST_FOR_PAREN');
      const head = s.slice(openParen + 1, closeParen);
      const parts = head.split(';');
      if (parts.length !== 3) throw new Error('LIA_AST_FOR_HEAD');
      let j = skipWs(s, closeParen + 1);
      if (s[j] !== '{') throw new Error('LIA_AST_FOR_BRACE');
      const b = parseBlockBody(s, j);
      out.push({
        type: 'for',
        init: parts[0].trim(),
        cond: parts[1].trim(),
        step: parts[2].trim(),
        body: b.stmts,
      });
      i = b.end;
      continue;
    }

    if (s.startsWith('throw', i) && !/[A-Za-z0-9_$]/.test(s[i + 5] || '')) {
      let j = i + 5;
      let depth = 0;
      let quote = null;
      while (j < s.length) {
        const c = s[j];
        if (quote) {
          if (c === '\\') { j += 2; continue; }
          if (c === quote) quote = null;
          j++;
          continue;
        }
        if (c === '"' || c === "'") { quote = c; j++; continue; }
        if (c === '(' || c === '{' || c === '[') depth++;
        else if (c === ')' || c === '}' || c === ']') depth--;
        else if (c === ';' && depth === 0) break;
        else if (depth === 0 && j > i + 5 && (s.startsWith('?(', j) || s.startsWith('#(', j) || s[j] === '^')) break;
        j++;
      }
      out.push({ type: 'throw', expr: s.slice(i, j).trim() });
      i = j < s.length && s[j] === ';' ? j + 1 : j;
      continue;
    }

    if (s.startsWith('switch', i) && /^\s*\(/.test(s.slice(i + 6))) {
      const open = s.indexOf('(', i);
      const close = findMatching(s, open, '(', ')');
      if (close >= 0) {
        let j = skipWs(s, close + 1);
        if (s[j] === '{') {
          const closeB = findMatching(s, j, '{', '}');
          if (closeB >= 0) {
            out.push(switchToIf(s.slice(open + 1, close).trim(), s.slice(j + 1, closeB)));
            i = closeB + 1;
            continue;
          }
        }
      }
    }

    if (s.startsWith('match', i) && /^\s*\(/.test(s.slice(i + 5))) {
      const open = s.indexOf('(', i);
      const close = findMatching(s, open, '(', ')');
      if (close >= 0) {
        let j = skipWs(s, close + 1);
        if (s[j] === '{') {
          const closeB = findMatching(s, j, '{', '}');
          if (closeB >= 0) {
            const expr = s.slice(open + 1, close).trim();
            const inner = s.slice(j + 1, closeB);
            const arms = parseMatchArms(inner);
            out.push({ type: 'match', expr, arms });
            i = closeB + 1;
            continue;
          }
        }
      }
    }

    if (s[i] === '^') {
      let j = i + 1;
      let depth = 0;
      let quote = null;
      let inRe = false;
      while (j < s.length) {
        const c = s[j];
        if (quote) {
          if (c === '\\') { j += 2; continue; }
          if (c === quote) quote = null;
          j++;
          continue;
        }
        if (inRe) {
          if (c === '\\') { j += 2; continue; }
          if (c === '/') inRe = false;
          j++;
          continue;
        }
        if (c === '"' || c === "'") { quote = c; j++; continue; }
        if (c === '/' && isRegexStart(s, j)) { inRe = true; j++; continue; }
        if (c === '(' || c === '{' || c === '[') depth++;
        else if (c === ')' || c === '}' || c === ']') depth--;
        else if (c === ';' && depth === 0) break;
        else if ((c === '?' || c === '#' || c === '^') && depth === 0 && j > i + 1) break;
        j++;
      }
      let retExpr = s.slice(i + 1, j).trim();
      if (retExpr.startsWith('return ') || retExpr.startsWith('return\t')) {
        retExpr = retExpr.slice(6).trim();
      }
      out.push({ type: 'return', expr: retExpr });
      i = j < s.length && s[j] === ';' ? j + 1 : j;
      continue;
    }

    // assignment or expr until ; or control at depth 0 (not ^ inside /regex/ or strings)
    let j = i;
    let depth = 0;
    let quote = null;
    let inRe = false;
    while (j < s.length) {
      const c = s[j];
      if (quote) {
        if (c === '\\') { j += 2; continue; }
        if (c === quote) quote = null;
        j++;
        continue;
      }
      if (inRe) {
        if (c === '\\') { j += 2; continue; }
        if (c === '/') inRe = false;
        j++;
        continue;
      }
      if (c === '"' || c === "'") { quote = c; j++; continue; }
      if (c === '/' && isRegexStart(s, j)) { inRe = true; j++; continue; }
      if (c === '(' || c === '{' || c === '[') depth++;
      else if (c === ')' || c === '}' || c === ']') depth--;
      else if (c === ';' && depth === 0) break;
      else if (depth === 0 && j > i && (s.startsWith('?(', j) || s.startsWith('#(', j))) break;
      j++;
    }
    const chunk = s.slice(i, j).trim();
    if (chunk) {
      const dm = chunk.match(/^\(\{([^}]+)\}=([\s\S]+)\)$/);
      if (dm) {
        for (const part of dm[1].split(',')) {
          const pm = part.trim().match(/^([A-Za-z_$][\w$]*)(?:\s*=\s*([\s\S]+))?$/);
          if (!pm) continue;
          const fallback = pm[2] ? pm[2].trim() : '""';
          out.push({
            type: 'assign', id: pm[1], op: '=',
            expr: `_lia_or(_lia_get(${dm[2].trim()},"${pm[1]}"),${fallback})`,
          });
        }
      } else {
        const am = chunk.match(/^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])*)\s*(<<=|>>=|[+\-*/%&|^]=|=)\s*([\s\S]+)$/);
        if (am) out.push({ type: 'assign', id: am[1], op: am[2], expr: am[3].trim() });
        else out.push({ type: 'expr', expr: chunk });
      }
    }
    i = j < s.length && s[j] === ';' ? j + 1 : j;
  }
  return out;
}

export function collectAssignedIds(stmts) {
  const ids = new Set();
  const walk = (list) => {
    for (const st of list || []) {
      if (st.type === 'assign' && !String(st.id).includes('.') && !/\[[^\]]+\]/.test(String(st.id))) ids.add(st.id);
      if (st.type === 'for' || st.type === 'while') {
        if (st.type === 'for') {
          const im = st.init.match(/^([A-Za-z_$][\w$]*)\s*=/);
          if (im) ids.add(im[1]);
        }
        walk(st.body);
      }
      if (st.type === 'if') {
        walk(st.then);
        for (const e of st.elseIf || []) walk(e.body);
        if (st.else) walk(st.else);
      }
      if (st.type === 'match') {
        for (const arm of st.arms || []) {
          const idm = arm.pat.match(/^[A-Za-z_$][\w$]*\(([^)]+)\)$/);
          if (idm) {
            const innerVars = idm[1].split(',').map((x) => x.trim()).filter((x) => /^[A-Za-z_$][\w$]*$/.test(x));
            for (const v of innerVars) ids.add(v);
          }
          walk(arm.body);
        }
      }
    }
  };
  walk(stmts);
  return [...ids];
}

function isRegexStart(s, j) {
  let k = j - 1;
  while (k >= 0 && /\s/.test(s[k])) k--;
  if (k < 0) return true;
  return /[=(,[:!?&|{;]/.test(s[k]);
}

function onlySemi(s) {
  return !String(s || '').replace(/[\s;]/g, '');
}

function parseMatchArms(inner) {
  const arms = [];
  let i = 0;
  while (i < inner.length) {
    i = skipWs(inner, i);
    if (i >= inner.length) break;
    if (inner[i] === ';') { i++; continue; }
    let q = null;
    let d = 0;
    let arrowIdx = -1;
    for (let k = i; k < inner.length; k++) {
      const ch = inner[k];
      if (q) {
        if (ch === '\\') { k++; continue; }
        if (ch === q) q = null;
        continue;
      }
      if (ch === '"' || ch === "'") { q = ch; continue; }
      if (ch === '(' || ch === '{' || ch === '[') d++;
      else if (ch === ')' || ch === '}' || ch === ']') d--;
      else if (d === 0 && ch === '=' && inner[k + 1] === '>') {
        arrowIdx = k;
        break;
      }
    }
    if (arrowIdx < 0) break;
    const patRaw = inner.slice(i, arrowIdx).trim();
    let pat = patRaw;
    let guard = null;
    const guardMatch = patRaw.match(/^([\s\S]+?)\s+if\s+([\s\S]+)$/);
    if (guardMatch) {
      pat = guardMatch[1].trim();
      guard = guardMatch[2].trim();
    }
    let bodyStart = arrowIdx + 2;
    bodyStart = skipWs(inner, bodyStart);
    let bodyStmts = [];
    let nextI = bodyStart;
    if (inner[bodyStart] === '{') {
      const closeB = findMatching(inner, bodyStart, '{', '}');
      if (closeB >= 0) {
        bodyStmts = parseStmts(inner.slice(bodyStart + 1, closeB));
        nextI = closeB + 1;
      }
    } else {
      let k = bodyStart;
      let q2 = null;
      let d2 = 0;
      for (; k < inner.length; k++) {
        const ch = inner[k];
        if (q2) {
          if (ch === '\\') { k++; continue; }
          if (ch === q2) q2 = null;
          continue;
        }
        if (ch === '"' || ch === "'") { q2 = ch; continue; }
        if (ch === '(' || ch === '{' || ch === '[') d2++;
        else if (ch === ')' || ch === '}' || ch === ']') d2--;
        else if (d2 === 0 && (ch === ',' || ch === ';')) break;
      }
      const exprStr = inner.slice(bodyStart, k).trim();
      if (exprStr) {
        if (/^\^/.test(exprStr)) {
          bodyStmts = [{ type: 'return', expr: exprStr.slice(1).trim() }];
        } else {
          bodyStmts = [{ type: 'expr', expr: exprStr }];
        }
      }
      nextI = k < inner.length ? k + 1 : k;
    }
    arms.push({ pat, guard, body: bodyStmts });
    i = nextI;
  }
  return arms;
}

function switchToIf(cond, inner) {
  const clauses = [];
  let i = 0;
  let labels = [];
  let isDefault = false;
  let bodyStart = -1;
  const flush = (end) => {
    if (bodyStart < 0 && !labels.length && !isDefault) return;
    clauses.push({ labels, isDefault, body: parseStmts(inner.slice(Math.max(bodyStart, 0), end)) });
    labels = [];
    isDefault = false;
    bodyStart = -1;
  };
  while (i < inner.length) {
    i = skipWs(inner, i);
    if (i >= inner.length) break;
    if (inner.startsWith('case', i) && /[\s'"]/.test(inner[i + 4] || '')) {
      if (bodyStart >= 0 && !onlySemi(inner.slice(bodyStart, i))) flush(i);
      let e = i + 4;
      e = skipWs(inner, e);
      let d = 0;
      let q = null;
      let k = e;
      for (; k < inner.length; k++) {
        const ch = inner[k];
        if (q) {
          if (ch === '\\') { k++; continue; }
          if (ch === q) q = null;
          continue;
        }
        if (ch === '"' || ch === "'") { q = ch; continue; }
        if (ch === '(' || ch === '{') d++;
        else if (ch === ')' || ch === '}') d--;
        else if (ch === ':' && d === 0) break;
      }
      labels.push(inner.slice(e, k).trim());
      i = k + 1;
      bodyStart = i;
      continue;
    }
    if (inner.startsWith('default', i) && /[\s:]/.test(inner[i + 7] || '')) {
      if (bodyStart >= 0 && !onlySemi(inner.slice(bodyStart, i))) flush(i);
      isDefault = true;
      const col = inner.indexOf(':', i);
      i = col >= 0 ? col + 1 : i + 7;
      bodyStart = i;
      continue;
    }
    i++;
  }
  if (labels.length || isDefault || bodyStart >= 0) flush(inner.length);
  const normals = clauses.filter((c) => !c.isDefault);
  const def = clauses.find((c) => c.isDefault);
  const orCond = (ls) => (ls.length ? ls.map((l) => `${cond}==${l}`).join('||') : 'true');
  if (!normals.length) {
    return { type: 'if', cond: 'true', then: def?.body || [], elseIf: [], else: null };
  }
  return {
    type: 'if',
    cond: orCond(normals[0].labels),
    then: normals[0].body,
    elseIf: normals.slice(1).map((c) => ({ cond: orCond(c.labels), body: c.body })),
    else: def ? def.body : null,
  };
}
