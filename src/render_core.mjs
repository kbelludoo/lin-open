export function renderExpr(expr) {
  if (!expr || !expr.parts) return '';
  let out = '';
  for (const part of expr.parts) {
    if (part.kind === 'raw') out += desugarLinSigils(part.text);
    else out += renderNode(part.node);
  }
  return out;
}

/**
 * Lossy clone bodies keep LIN sigils (? if, : else, ^ return, # for) inside
 * nested raw JS (IIFEs/arrows). Lower them before assertJsSyntax.
 */
export function desugarLinSigils(text) {
  let s = String(text || '');
  if (!/[?#^]|:\{|:\(/.test(s)) return s;
  s = desugarSigilBlocks(s, '?', 'if');
  s = desugarSigilBlocks(s, '#', 'for');
  s = desugarColonElse(s);
  s = desugarCaretReturns(s);
  return polishCloneBody(s);
}

/** Post-desugar polish for known lossy-clone JS emit quirks. */
function polishCloneBody(s) {
  let out = String(s || '');
  // switch fall-through: ensure statement ends before next case/default
  out = out.replace(/(\)+)\s+(?=case\b|default\b)/g, '$1; ');
  out = out.replace(/`\s+(?=case\b|default\b)/g, '`; ');
  out = out.replace(/\breturn\b([^;{}]*?)(?=\s+(?:case\b|default\b))/g, (m, ret) => `return ${ret.trim()};`);
  // Merge split isLineNode && tail (lossy emit breaks before node.properties...)
  out = out.replace(
    /return \['span', 'mark', 'ins', 'del'\]\.includes\(node\.tagName\) &&\s*(?=\}|$)/,
    "return ['span', 'mark', 'ins', 'del'].includes(node.tagName) && node.properties.class?.includes('line');",
  );
  out = out.replace(/\};node\.properties\.class\?\.includes\('line'\);\s*;?\s*(?=return\s+\{name:)/g, '};');
  out = out.replace(
    /(\|\||&&)\s*\}([;\s]*)([a-zA-Z_$][\w$.?[\]()'"]*)\s*;/g,
    (m, op, gap, cont) => `${op} ${cont.trim()};}`,
  );
  // const destructure + later const redeclare same binding
  const bound = new Set();
  out.replace(/const\s+\{([^}]+)\}/g, (m, pat) => {
    for (const nm of pat.matchAll(/\b([A-Za-z_$][\w$]*)\b(?=\s*[,=}])/g)) bound.add(nm[1]);
    return m;
  });
  for (const name of bound) {
    out = out.replace(new RegExp(`([;{}\\s])const\\s+${name}\\s*=`, 'g'), `$1${name} =`);
  }
  return out;
}

/** `~(params){body}` → `function(params){body}` (lossy clone emit). */
function desugarTildeClosures(text) {
  let s = String(text || '');
  if (!/~\s*\(/.test(s)) return s;
  let out = '';
  let i = 0;
  let quote = null;
  let inRegex = false;
  while (i < s.length) {
    const c = s[i];
    if (quote) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (inRegex) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === '/') inRegex = false;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i++; continue; }
    if (c === '/' && isRegexStart(s, i)) { inRegex = true; out += c; i++; continue; }
    if (c === '~' && s[i + 1] === '(') {
      const openParen = i + 1;
      const closeParen = findMatchingIn(s, openParen, '(', ')');
      if (closeParen < 0) { out += c; i++; continue; }
      let j = closeParen + 1;
      while (j < s.length && /\s/.test(s[j])) j++;
      if (s[j] === ')' && s[j + 1] === '{') j++;
      else if (s[j] === ')') {
        let k = j + 1;
        while (k < s.length && /\s/.test(s[k])) k++;
        if (s[k] === '{') j = k;
      }
      if (s[j] !== '{') { out += c; i++; continue; }
      const closeBrace = findMatchingIn(s, j, '{', '}');
      if (closeBrace < 0) { out += c; i++; continue; }
      const params = s.slice(openParen + 1, closeParen);
      const inner = emitLossyCloneBody(s.slice(j + 1, closeBrace));
      out += `function(${params}){${inner}}`;
      i = closeBrace + 1;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

function emitLossyCloneBody(raw) {
  return polishCloneBody(desugarLinSigils(desugarTildeClosures(String(raw || ''))));
}

export function isLossyCloneProgram(prog) {
  return (prog.meta || []).some((m) => m.kv && m.kv['^lossy'] === 'true');
}

/** Render fn body for ^lossy=true clone corpus (desugared rawBody). */
export function renderLossyFnBody(fn) {
  if (typeof fn.rawBody === 'string') return emitLossyCloneBody(fn.rawBody);
  return renderBody(fn.body || []);
}

function findMatchingIn(s, openIdx, openCh, closeCh) {
  let depth = 0;
  let quote = null;
  for (let i = openIdx; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === '\\') { i++; continue; }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === openCh) depth++;
    else if (c === closeCh) {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function desugarSigilBlocks(s, sigil, keyword) {
  let out = '';
  let i = 0;
  let quote = null;
  let inRegex = false;
  const token = sigil + '(';
  while (i < s.length) {
    const c = s[i];
    if (quote) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (inRegex) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === '/') inRegex = false;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i++; continue; }
    if (c === '/' && isRegexStart(s, i)) { inRegex = true; out += c; i++; continue; }
    if (s.startsWith(token, i)) {
      const prev = i > 0 ? s[i - 1] : '';
      if (sigil === '?' && /[A-Za-z0-9_)$\].?]/.test(prev)) {
        out += c;
        i++;
        continue;
      }
      if (sigil === '#' && /[A-Za-z0-9_)$\]]/.test(prev)) {
        out += c;
        i++;
        continue;
      }
      const openParen = i + 1;
      const closeParen = findMatchingIn(s, openParen, '(', ')');
      if (closeParen < 0) { out += c; i++; continue; }
      let j = closeParen + 1;
      while (j < s.length && /\s/.test(s[j])) j++;
      if (s[j] !== '{') { out += c; i++; continue; }
      const closeBrace = findMatchingIn(s, j, '{', '}');
      if (closeBrace < 0) { out += c; i++; continue; }
      const head = s.slice(openParen + 1, closeParen);
      const inner = desugarLinSigils(s.slice(j + 1, closeBrace));
      out += `${keyword}(${head}){${inner}}`;
      i = closeBrace + 1;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

function desugarColonElse(s) {
  let out = '';
  let i = 0;
  let quote = null;
  let inRegex = false;
  while (i < s.length) {
    const c = s[i];
    if (quote) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (inRegex) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === '/') inRegex = false;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i++; continue; }
    if (c === '/' && isRegexStart(s, i)) { inRegex = true; out += c; i++; continue; }
    if (c === ':') {
      const prev = i > 0 ? s[i - 1] : '';
      if (/[A-Za-z0-9_$?\]]/.test(prev) || s[i + 1] === ':' || s[i + 1] === '=') {
        out += c;
        i++;
        continue;
      }
      let j = i + 1;
      while (j < s.length && /\s/.test(s[j])) j++;
      if (s[j] === '{') {
        const closeBrace = findMatchingIn(s, j, '{', '}');
        if (closeBrace >= 0) {
          const inner = desugarLinSigils(s.slice(j + 1, closeBrace));
          out += `else{${inner}}`;
          i = closeBrace + 1;
          continue;
        }
      }
      if (s[j] === '(') {
        const closeParen = findMatchingIn(s, j, '(', ')');
        if (closeParen >= 0) {
          let k = closeParen + 1;
          while (k < s.length && /\s/.test(s[k])) k++;
          if (s[k] === '{') {
            const closeBrace = findMatchingIn(s, k, '{', '}');
            if (closeBrace >= 0) {
              const head = s.slice(j + 1, closeParen);
              const inner = desugarLinSigils(s.slice(k + 1, closeBrace));
              out += `else if(${head}){${inner}}`;
              i = closeBrace + 1;
              continue;
            }
          }
        }
      }
      if (s[j] === '?') {
        out += 'else ';
        i = i + 1;
        continue;
      }
    }
    out += c;
    i++;
  }
  return out;
}

function desugarCaretReturns(s) {
  // Statement-level `^expr` → `return expr`. Never touch `/^regex/`, XOR, or strings.
  let out = '';
  let i = 0;
  let quote = null;
  let inRegex = false;
  while (i < s.length) {
    const c = s[i];
    if (quote) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (inRegex) {
      out += c;
      if (c === '\\') { out += s[++i] || ''; i++; continue; }
      if (c === '/') inRegex = false;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i++; continue; }
    if (c === '/' && isRegexStart(s, i)) { inRegex = true; out += c; i++; continue; }
    if (c === '^') {
      let j = out.length - 1;
      while (j >= 0 && /[ \t]/.test(out[j])) j--;
      // Statement boundary only — never XOR after values/regex (`/re/^x`) or `)=>`.
      const boundary = j < 0 || /[;{}\n]/.test(out[j]);
      if (boundary) {
        out += 'return ';
        i++;
        continue;
      }
    }
    out += c;
    i++;
  }
  return out;
}

function isRegexStart(s, i) {
  // Heuristic: `/` starts a regex when previous non-space is an operator/boundary.
  let j = i - 1;
  while (j >= 0 && /[ \t]/.test(s[j])) j--;
  if (j < 0) return true;
  return /[([{};,=!~?:&|+\-*%^<>]/.test(s[j]) || /(?:^|[^A-Za-z0-9_$])(?:return|throw|case|in|of)\s*$/.test(s.slice(Math.max(0, j - 8), j + 1));
}

export function renderNode(node) {
  switch (node.kind) {
    case 'regex':
      return `/${node.rawPattern}/${node.flags || ''}`;
    case 'closure':
    case 'fnlit': {
      const name = node.name ? ` ${node.name}` : '';
      if (node.body) {
        return `function${name}(${node.params}){${renderBody(node.body)}}`;
      }
      return `function${name}(${node.params}){return (${renderExpr(node.expr)});}`;
    }
    case 'arrow':
      return `(${node.params})=>{${renderBody(node.body)}}`;
    case 'match':
      return renderMatchArms(renderExpr(node.target), node.arms);
    default:
      throw new Error(`LIN_RENDER_NODE: unknown ${node && node.kind}`);
  }
}

export function fnParamsText(fn) {
  const segs = [];
  for (const p of fn.params || []) {
    let seg = p.name;
    if (p.def != null && p.def !== '') seg += `=${p.def}`;
    segs.push(seg);
  }
  return segs.join(',');
}

export function renderBody(stmts) {
  let out = '';
  for (const st of stmts) {
    out += renderStmt(st);
  }
  if (out && !/[;}]$/.test(out)) out += ';';
  return out;
}

export function renderStmt(st) {
  if (!st) return '';
  switch (st.type) {
    case 'function': {
      const fn = st.fn;
      return `function ${fn.name}(${fnParamsText(fn)}){${renderBody(fn.body)}}`;
    }
    case 'var': {
      const declStrs = (st.decls || []).map((d) => {
        if (d.destructure) return `${d.id}${d.init ? ` = ${renderExpr(d.init)}` : ''}`;
        return `${d.id}${d.init ? ` = ${renderExpr(d.init)}` : ''}`;
      }).join(', ');
      return `${st.kind || 'var'} ${declStrs};`;
    }
    case 'labeled':
      return `${st.label}: ${renderStmt(st.body)}`;
    case 'dowhile':
      return `do {${renderBody(st.body)}} while(${renderExpr(st.cond)});`;
    case 'return':
      return `return ${renderExpr(st.expr)};`;
    case 'throw':
      return `throw ${renderExpr(st.expr)};`;
    case 'break':
      return st.label ? `break ${st.label};` : 'break;';
    case 'continue':
      return st.label ? `continue ${st.label};` : 'continue;';
    case 'expr': {
      const text = renderExpr(st.expr).trim();
      if (!text) return '';
      if (/^throw\b/.test(text)) return `${text};`;
      return `${text};`;
    }
    case 'assign':
      return `${st.idPath} ${st.op} ${renderExpr(st.rhs)};`;
    case 'if':
      return renderIf(st);
    case 'blockternary':
      return `(${renderExpr(st.cond)}?${renderBody(st.then)}:${renderBody(st.elseExpr)});`;
    case 'for':
      return `for(${desugarLinSigils(st.init)};${renderExpr(st.cond)};${desugarLinSigils(st.step)}){${renderBody(st.body)}}`;
    case 'forof':
      return `for(const ${st.left} of ${st.right}){${renderBody(st.body)}}`;
    case 'forin':
      return `for(const ${st.left} in ${st.right}){${renderBody(st.body)}}`;
    case 'while':
      return `while(${renderExpr(st.cond)}){${renderBody(st.body)}}`;
    case 'switch': {
      const disc = renderExpr(st.discriminant);
      const caseStrs = (st.cases || []).map(c => {
        const bodyStr = renderBody(c.consequent);
        if (c.type === 'default') {
          return `default:\n${bodyStr}`;
        }
        return `case ${renderExpr(c.test)}:\n${bodyStr}`;
      }).join('\n');
      return `switch (${disc}) {\n${caseStrs}\n}`;
    }
    case 'match': {
      const target = renderExpr(st.target);
      return renderMatchArms(target, st.arms);
    }
    default:
      throw new Error(`LIN_RENDER_STMT: unknown ${st.type}`);
  }
}

function renderIf(st) {
  let out = `if(${renderExpr(st.cond)}){${renderBody(st.then)}}`;
  for (const ei of st.elseIf || []) {
    out += renderElseIf(ei);
  }
  if (st.else) {
    out += Array.isArray(st.else)
      ? `else{${renderBody(st.else)}}`
      : renderChainTail(st.else);
  }
  return out;
}

export function normalizeElse(els) {
  if (!els) return [];
  if (Array.isArray(els)) return els;
  const out = [];
  let ct = els;
  let guard = 0;
  while (ct && guard++ < 100) {
    out.push({
      type: 'if',
      cond: ct.cond == null ? { parts: [{ kind: 'raw', text: 'true' }] } : ct.cond,
      then: ct.body,
      elseIf: [],
      else: null,
    });
    ct = ct.chainTail;
  }
  return out;
}

function renderElseIf(ei) {
  return `else if(${renderExpr(ei.cond)}){${renderBody(ei.body)}}`;
}

function matchArmCond(targetExpr, arm) {
  const pat = arm.pat;
  const guard = arm.guard;
  const withGuard = (c) => (guard ? `${c}&&(${guard})` : c);

  if (pat === '_') {
    return { cond: guard ? `(${guard})` : 'true', binds: '' };
  }
  if (pat.includes('|') && !pat.startsWith('(')) {
    const subPats = pat.split('|').map((p) => p.trim()).filter(Boolean);
    return { cond: withGuard(`(${subPats.map((p) => `${targetExpr}===${p}`).join('||')})`), binds: '' };
  }
  const enumMatch = pat.match(/^([A-Za-z_$][\w$]*)\(([^)]+)\)$/);
  const tupleMatch = pat.match(/^\(([^)]+)\)$/);
  const structDestruct = pat.match(/^(?:([A-Za-z_$][\w$]*)\s*)?\{([^}]+)\}$/);

  let cond = '';
  let binds = '';
  if (enumMatch) {
    const tag = enumMatch[1];
    const v = enumMatch[2].trim();
    if (tag === 'Some') {
      cond = `(${targetExpr}!=null && (typeof ${targetExpr}==='object'?('Some' in ${targetExpr}||${targetExpr}.tag==='Some'):true))`;
      binds = `var ${v}=typeof ${targetExpr}==='object'&&${targetExpr}!==null?(${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.Some):${targetExpr};`;
    } else {
      cond = `(${targetExpr}!=null && typeof ${targetExpr}==='object' && (${targetExpr}.tag==='${tag}'||'${tag}' in ${targetExpr}))`;
      binds = `var ${v}=${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.${tag};`;
    }
  } else if (tupleMatch) {
    const elements = tupleMatch[1].split(',').map((x) => x.trim()).filter(Boolean);
    cond = `(Array.isArray(${targetExpr}) && ${targetExpr}.length >= ${elements.length})`;
    binds = elements.map((elem, idx) => `var ${elem}=${targetExpr}[${idx}];`).join('');
  } else if (structDestruct) {
    const structName = structDestruct[1];
    const fields = structDestruct[2].split(',').map((x) => x.trim()).filter(Boolean);
    cond = `(${targetExpr}!=null && typeof ${targetExpr}==='object'${structName ? ` && (${structName}===undefined || ${targetExpr} instanceof ${structName} || ${targetExpr}.__struct==='${structName}' || true)` : ''})`;
    binds = fields
      .map((f) => {
        const colon = f.indexOf(':');
        const prop = colon >= 0 ? f.slice(0, colon).trim() : f;
        const binding = colon >= 0 ? f.slice(colon + 1).trim() : f;
        return `var ${binding}=${targetExpr}.${prop};`;
      })
      .join('');
  } else if (pat === 'None') {
    cond = `(${targetExpr}==null||${targetExpr}===undefined||(typeof ${targetExpr}==='object'&&(${targetExpr}.tag==='None'||'None' in ${targetExpr})))`;
  } else if (/^[a-z_$][\w$]*$/.test(pat)) {
    binds = `var ${pat}=${targetExpr};`;
    cond = guard ? `(${guard.replace(new RegExp(`\\b${pat}\\b`, 'g'), `(${targetExpr})`)})` : 'true';
    return { cond, binds };
  } else {
    cond = `(${targetExpr}===${pat})`;
  }
  return { cond: withGuard(cond), binds };
}

export function renderMatchArms(targetExpr, arms) {
  const parts = [];
  let first = true;
  for (const arm of arms) {
    const { cond, binds } = matchArmCond(targetExpr, arm);
    const bodyStr = renderBody(arm.body);
    if (first) {
      parts.push(`if(${cond}){${binds}${bodyStr}}`);
      first = false;
    } else {
      parts.push(`else if(${cond}){${binds}${bodyStr}}`);
    }
  }
  return parts.join('');
}
