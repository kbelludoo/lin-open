import { tokenize } from '../lexer.mjs';

export function stripJsComments(src) {
  const toks = tokenize(String(src || '').replace(/^#!.*\n/, ''));
  let out = '';
  let lastEnd = 0;
  for (const t of toks) {
    if (t.type === 'comment') {
      out += src.slice(lastEnd, t.start);
      lastEnd = t.end;
    }
  }
  out += src.slice(lastEnd);
  return out;
}

export function extractJsFunctions(src) {
  const s = String(src || '');
  const clean = stripJsComments(s)
    .replace(/^\s*export\s+default\s+/gm, '')
    .replace(/^\s*export\s+\{[^}]*\}\s*;?\s*$/gm, '')
    .replace(/^\s*export\s+/gm, '')
    .replace(/^\s*import\s+type\s+[^;]+;\s*$/gm, '')
    .replace(/^\s*import\s+[^;]+;\s*$/gm, '');

  const fns = [];
  const seen = new Set();
  const pushFn = (name, params, body, kind) => {
    if (!name || seen.has(name)) return;
    fns.push({ name, params: splitParams(params), rawParams: params.trim(), body: body.trim(), kind });
    seen.add(name);
  };

  const kwRe = /(?:^|[;{}\n])\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/g;
  let m;
  while ((m = kwRe.exec(clean)) !== null) {
    const name = m[1];
    const openParen = clean.indexOf('(', m.index + m[0].length - 1);
    const closeParen = matchBracket(clean, openParen, '(', ')');
    if (closeParen < 0) continue;
    let j = closeParen + 1;
    while (j < clean.length && /\s/.test(clean[j])) j++;
    if (clean[j] !== '{') continue;
    const closeBrace = matchBracket(clean, j, '{', '}');
    if (closeBrace < 0) continue;
    pushFn(name, clean.slice(openParen + 1, closeParen), clean.slice(j + 1, closeBrace), 'declaration');
    kwRe.lastIndex = closeBrace;
  }

  const varRe = /(?:^|[;{}\n])\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b\s*\*?\s*[A-Za-z_$][\w$]*\s*)?\(/g;
  while ((m = varRe.exec(clean)) !== null) {
    const name = m[1];
    const openParen = clean.indexOf('(', m.index + m[0].length - 1);
    const closeParen = matchBracket(clean, openParen, '(', ')');
    if (closeParen < 0) continue;
    let j = closeParen + 1;
    while (j < clean.length && /\s/.test(clean[j])) j++;
    if (clean[j] !== '{') continue;
    const closeBrace = matchBracket(clean, j, '{', '}');
    if (closeBrace < 0) continue;
    pushFn(name, clean.slice(openParen + 1, closeParen), clean.slice(j + 1, closeBrace), 'assigned');
    varRe.lastIndex = closeBrace;
  }

  return { fns, rest: clean };
}

export function splitParams(raw) {
  return String(raw || '')
    .split(',')
    .map((p) => p.replace(/\s*=\s*[\s\S]+$/, '').trim().replace(/\s*:.*$/, '').trim())
    .filter(Boolean);
}

export function matchBracket(s, openIdx, openCh, closeCh) {
  if (openIdx < 0 || s[openIdx] !== openCh) return -1;
  let depth = 0;
  let quote = null;
  for (let i = openIdx; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === '\\') i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      continue;
    }
    if (c === openCh) depth++;
    else if (c === closeCh) {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

export function siblingsPrelude(fns, targetName) {
  const parts = [];
  for (const fn of fns || []) {
    if (!fn.name || fn.name === targetName) continue;
    try {
      new Function(`function ${fn.name}(){${fn.body}}`);
      parts.push(`function ${fn.name}(${fn.rawParams}){${fn.body}}`);
    } catch {}
  }
  return parts.join('\n');
}


export function extractTopLevelVars(src) {
  const toks = tokenize(stripJsComments(String(src || '')));
  const vars = [];
  let firstFn = toks.length;
  {
    let depth = 0;
    for (let k = 0; k < toks.length; k++) {
      const t = toks[k];
      if (t.type === 'punct') {
        if ('([{'.includes(t.value)) depth++;
        else if (')]}'.includes(t.value)) depth--;
        else if (depth === 0 && t.value === '!' ) {
          firstFn = k;
          break;
        }
      }
      if (t.type === 'id' && t.value === 'function' && depth === 0) {
        firstFn = k;
        break;
      }
    }
  }
  let i = 0;
  while (i < firstFn && toks[i].type !== 'eof') {
    const t = toks[i];
    if (t.type === 'nl' || t.type === 'punct' && t.value === ';') {
      i++;
      continue;
    }
    if (t.type === 'id' && ['var', 'let', 'const'].includes(t.value)) {

      const nameTok = toks[i + 1];
      if (nameTok && nameTok.type === 'id' && toks[i + 2]?.value === '=') {
        const initStart = i + 3;
        let j = initStart;
        let depth = 0;
        for (; j < toks.length; j++) {
          const tk = toks[j];
          if (tk.type === 'punct') {
            if ('([{'.includes(tk.value)) depth++;
            else if (')]}'.includes(tk.value)) {
              depth--;
              if (depth === 0) {
                j++;
                break;
              }
            } else if (depth === 0 && tk.value === ';') break;
          } else if (tk.type === 'nl' && depth === 0) break;
        }
        const initText = joinToks(toks, initStart, j);
        if (initText && !/\bfunction\b/.test(initText)) {
          vars.push({ name: nameTok.value, init: initText });
        }
        i = j;
        continue;
      }
    }
    i++;
  }
  return vars;
}

function joinToks(toks, from, toExclusive) {
  const parts = [];
  for (let i = from; i < toExclusive && i < toks.length; i++) {
    const t = toks[i];
    if (t.type === 'nl') continue;
    parts.push(t.value);
  }
  return parts.join(' ').trim();
}
