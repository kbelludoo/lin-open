const KEYWORD_WORDS = new Set(['return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void', 'do', 'else', 'case', 'yield', 'await', 'match', 'as', 'satisfies']);

export function stripTsLight(src) {
  let s = String(src || '');
  s = s.replace(/^\s*\/\*\*[\s\S]*?\*\//gm, '');
  s = s.replace(/\/\/[^\n]*/g, '');
  s = removeTsDeclarations(s);
  s = collapseOverloads(s);
  s = s.replace(/\bexport\s+(?=default\b|async\b|function\b|const\b|let\b|var\b|class\b)/g, '');
  s = stripTypeAnnotations(s);
  s = stripAsCasts(s);
  s = s.replace(/\(\s*,/g, '(').replace(/,\s*\)/g, ')');
  s = s.replace(/([\w$\])])\s*!(?=[,;.)])/g, '$1');
  s = s.replace(/^\s*;\s*$/gm, '');
  return s;
}

function stripAsCasts(src) {
  const s = String(src || '');
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const q = c;
      out += c;
      i++;
      while (i < s.length) {
        if (s[i] === '\\') {
          out += s[i] + (s[i + 1] || '');
          i += 2;
          continue;
        }
        out += s[i];
        if (s[i] === q) {
          i++;
          break;
        }
        i++;
      }
      continue;
    }
    const tail = s.slice(i);
    const asM = tail.match(/^as\b|^satisfies\b/);
    if (asM && (i === 0 || !/[\w$]/.test(s[i - 1]))) {
      let j = i + asM[0].length;
      while (j < s.length && /\s/.test(s[j])) j++;
      if (s[j] === '{') {
        let d = 0;
        for (; j < s.length; j++) {
          if (s[j] === '{') d++;
          else if (s[j] === '}') {
            d--;
            if (d === 0) break;
          }
        }
        j++;
      } else {
        for (; j < s.length; j++) {
          if (/[,;)}\n=]/.test(s[j])) break;
        }
      }
      out = out.replace(/\s+$/, '');
      i = j;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

function removeTsDeclarations(src) {
  const s = String(src);
  let out = '';
  let i = 0;
  while (i < s.length) {
    const rest = s.slice(i);
    const m = rest.match(/^\s*(?:export\s+)?(?:type\s+[A-Za-z_$][\w$]*\s*=|interface\s+[A-Za-z_$][\w$]*(<[^>]*>)?\s*\{)/);
    if (!m) {
      out += s[i];
      i++;
      continue;
    }
    out += s.slice(i, i + m[0].length - m[0].trimStart().length ? 0 : 0);
    let j = i + m.index + m[0].length;
    j = i + m[0].length;
    let depth = 0;
    let closed = false;
    const usesBrace = /\{\s*$/.test(m[0]);
    for (; j < s.length; j++) {
      const c = s[j];
      if (c === '"' || c === "'" || c === '`') {
        const q = c;
        j++;
        while (j < s.length && s[j] !== q) {
          if (s[j] === '\\') j++;
          j++;
        }
        continue;
      }
      if ('{[('.includes(c)) {
        depth++;
        continue;
      }
      if ('}])'.includes(c)) {
        depth--;
        if (depth < 0 && c === '}') {
          j++;
          closed = true;
          break;
        }
        continue;
      }
      if (c === ';' && depth <= 0 && !usesBrace) {
        j++;
        closed = true;
        break;
      }
    }
    const startLine = s.indexOf('\n', i);
    if (!closed) {
      out += '\n';
      i = startLine < 0 ? s.length : startLine;
    } else {
      out += '\n';
      i = j;
    }
  }
  return out;
}

function collapseOverloads(src) {
  const re = /(?:^|\n)[ \t]*(?:export\s+)?function\s+[A-Za-z_$][\w$]*\s*\((?:[^()]|\([^()]*\))*\)\s*:\s*(?:[^;{}\n]|\n(?!\s*(?:export|function)))+;/g;
  return String(src).replace(re, '\n');
}

function stripTypeAnnotations(src) {
  const s = String(src || '');
  const parens = [];
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '/') {
      if (s[i + 1] === '/') {
        const j = s.indexOf('\n', i);
        i = j < 0 ? s.length : j;
        continue;
      }
      if (s[i + 1] === '*') {
        const j = s.indexOf('*/', i + 2);
        i = j < 0 ? s.length : j + 2;
        continue;
      }
      const before = out.replace(/\s+$/, '');
      const kwMatch = before.match(/([A-Za-z_$][\w$]*)$/);
      let isRegex;
      if (kwMatch) {
        isRegex = ['return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void', 'do', 'else', 'case', 'yield', 'await', 'match'].includes(kwMatch[1]);
      } else {
        isRegex = before.length === 0 || /[=(:,;!?{[&|^~+\-*%<>]$/.test(before);
      }
      if (!isRegex) {
        out += c;
        i++;
        continue;
      }
      {
        const q = c;
        out += c;
        i++;
        while (i < s.length) {
          if (s[i] === '\\') {
            out += s[i] + (s[i + 1] || '');
            i += 2;
            continue;
          }
          if (q !== '`' && s[i] === '\n') break;
          out += s[i];
          if (s[i] === q) {
            i++;
            break;
          }
          i++;
        }
        continue;
      }
    }
    if (c === '{') {
      if (parens.length) parens[parens.length - 1].curly = (parens[parens.length - 1].curly || 0) + 1;
      out += c;
      i++;
      continue;
    }
    if (c === '}') {
      if (parens.length) parens[parens.length - 1].curly = Math.max(0, (parens[parens.length - 1].curly || 0) - 1);
      out += c;
      i++;
      continue;
    }
    if (c === '(') {
      const before = out.replace(/\s+$/, '');
      const headerLike = /(?:function\s+[A-Za-z_$][\w$]*|=>)\s*$/.test(before);
      parens.push({ start: out.length, headerLike, curly: 0 });
      out += c;
      i++;
      continue;
    }
    if (c === ')') {
      const frame = parens.pop();
      out += c;
      i++;
      if (frame && frame.headerLike) {
        let k = i;
        while (k < s.length && /\s/.test(s[k])) k++;
        if (s[k] === ':') {
          let d = 0;
          let m = k + 1;
          for (; m < s.length; m++) {
            const ch = s[m];
            if (ch === '"' || ch === "'" || ch === '`') {
              const q2 = ch;
              m++;
              while (m < s.length && s[m] !== q2) {
                if (s[m] === '\\') m++;
                m++;
              }
              continue;
            }
            if (ch === '{' && d === 0) break;
            if ('(['.includes(ch)) d++;
            else if (')]'.includes(ch)) {
              if (d === 0) break;
              d--;
            }
          }
          i = m;
          continue;
        }
      }
      continue;
    }
    if (c === ':' && parens.length > 0 && !(parens[parens.length - 1].curly > 0)) {
      let j = i + 1;
      let d = 0;
      for (; j < s.length; j++) {
        const ch = s[j];
        if (ch === '"' || ch === "'" || ch === '`') {
          const q2 = ch;
          j++;
          while (j < s.length && s[j] !== q2) {
            if (s[j] === '\\') j++;
            j++;
          }
          continue;
        }
        if ('([{'.includes(ch)) d++;
        else if (')]}'.includes(ch)) {
          if (d === 0) break;
          d--;
        } else if (d === 0 && (ch === ',' )) break;
      }
      i = j;
      continue;
    }
    if (c === '?' && parens.length > 0 && !(parens[parens.length - 1].curly > 0)) {
      const nx = s[i + 1];
      if (nx && /[,:)\s]/.test(nx)) {
        i++;
        continue;
      }
    }
    out += c;
    i++;
  }
  void KEYWORD_WORDS;
  return out;
}
