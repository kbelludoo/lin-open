/**
 * LIN emitter (ex-LIA/AIL) — lingua ia nativa compact IR.
 * Spec: LIN_CLONE_LIN_LOOP + LIA_CODE_LANG_SPEC (transition)
 *
 * Paths:
 *   source JS/TS-ish → LIN (preferred compact path)
 *   PROJECT.dicel L0 → LIN (named_only, strip_tests, L0-op desugar)
 *
 * Lossy. Does not overwrite L0 archive.
 * Headers: emit @LIN; compiler dual-reads @LIN/@LIA/@AIL.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const LIN_VERSION = '0.2';
export const LIN_HEADER = `@LIN:L1c:${LIN_VERSION}`;
export const LIA_VERSION = LIN_VERSION; // transition alias
export const LIA_HEADER = LIN_HEADER; // transition: value is @LIN
export const AIL_VERSION = LIN_VERSION;
export const AIL_HEADER = LIN_HEADER;

const DEFAULT_OPS = 'strip_tests+sigil_ops+named_only+const_table';
const GRAMMAR = '~G{?=if #=for ^=ret :else}';

const BYTES_K = '$K{b=1 kb=1024 mb=1048576 gb=1073741824 tb=1099511627776 pb=1125899906842624}';

const OP_INFIX = {
  '===': '==',
  '!==': '!=',
  '==': '==',
  '!=': '!=',
  '&&': '&&',
  '||': '||',
  '+': '+',
  '-': '-',
  '*': '*',
  '/': '/',
  '%': '%',
  '<': '<',
  '>': '>',
  '<=': '<=',
  '>=': '>=',
  '|': '|',
  '&': '&',
  '^': '^',
  '<<': '<<',
  '>>': '>>',
  '|=': '|=',
  '=': '=',
};

export function estTokens(s) {
  return Math.ceil(String(s).length / 4);
}

function isTestishBody(stmts) {
  const body = (stmts || []).join(';');
  // require call/member form so comments like "ditch it" are not tests
  return /\b(describe|it|bench)\s*\(|\b(assert|strictEqual)\s*[.(]/.test(body);
}

/** Parse ~Fn records from PROJECT.dicel text. */
export function parseProjectFns(dicelText) {
  const fns = [];
  const re =
    /~Fn\{name:"([^"]*)",\s*kind:"([^"]*)",\s*params:\[([^\]]*)\],\s*return_type:"([^"]*)",\s*body:FnBody\{statements:\[((?:[^\[\]]|\[[^\]]*\])*)\],\s*supported:(true|false)\}\}/g;
  let m;
  while ((m = re.exec(dicelText)) !== null) {
    const name = m[1];
    const kind = m[2];
    const params = [...m[3].matchAll(/name:"([^"]*)"/g)].map((x) => x[1]);
    const stmtsRaw = m[5];
    const stmts = [];
    const sre = /"((?:[^"\\]|\\.)*)"/g;
    let sm;
    while ((sm = sre.exec(stmtsRaw)) !== null) {
      stmts.push(sm[1].replace(/\\"/g, '"').replace(/\\\\/g, '\\'));
    }
    fns.push({ name, kind, params, stmts, supported: m[6] === 'true' });
  }
  return fns;
}

function splitTopArgs(s) {
  const out = [];
  let cur = '';
  let depth = 0;
  let quote = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      cur += c;
      if (c === '\\' && i + 1 < s.length) {
        cur += s[++i];
        continue;
      }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      cur += c;
      continue;
    }
    if (c === '(' || c === '[' || c === '{') {
      depth++;
      cur += c;
      continue;
    }
    if (c === ')' || c === ']' || c === '}') {
      depth--;
      cur += c;
      continue;
    }
    if (c === ',' && depth === 0) {
      out.push(cur.trim());
      cur = '';
      continue;
    }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function matchCallArgs(s, openIdx) {
  // openIdx points at '('
  let depth = 0;
  for (let i = openIdx; i < s.length; i++) {
    const c = s[i];
    if (c === '(') depth++;
    else if (c === ')') {
      depth--;
      if (depth === 0) return { args: s.slice(openIdx + 1, i), end: i };
    }
  }
  return null;
}

function rewritePrefixedCalls(s, prefix, replacer) {
  let out = '';
  let i = 0;
  while (i < s.length) {
    const idx = s.indexOf(prefix, i);
    if (idx < 0) {
      out += s.slice(i);
      break;
    }
    out += s.slice(i, idx);
    const after = s.slice(idx + prefix.length);
    const m = after.match(/^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\(/);
    if (!m) {
      out += prefix;
      i = idx + prefix.length;
      continue;
    }
    const name = m[1];
    const openIdx = idx + prefix.length + m[0].length - 1;
    const matched = matchCallArgs(s, openIdx);
    if (!matched) {
      out += prefix;
      i = idx + prefix.length;
      continue;
    }
    out += replacer(name, matched.args);
    i = matched.end + 1;
  }
  return out;
}

/** Desugar one L0 expression/statement fragment to JS-like. */
export function desugarL0Expr(expr) {
  let s = String(expr || '').trim();
  if (!s || s === '?' || s.startsWith('GAP:')) return '';

  for (let n = 0; n < 50; n++) {
    const before = s;

    s = rewritePrefixedCalls(s, 'call:member:', (name, args) => {
      const a = splitTopArgs(args).map(desugarL0Expr).join(',');
      return `${name}(${a})`;
    });
    s = rewritePrefixedCalls(s, 'call:', (name, args) => {
      if (name.includes('.')) return `call:member:${name}(${args})`; // shouldn't happen
      const a = splitTopArgs(args).map(desugarL0Expr).join(',');
      return `${name}(${a})`;
    });

    s = s.replace(/member:([A-Za-z_$][\w$]*)\.\[([^\]]+)\]/g, (_, obj, idx) => `${obj}[${desugarL0Expr(idx)}]`);
    s = s.replace(/member:([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)/g, '$1');
    s = s.replace(/unary:typeof\(([^()]*)\)/g, (_, e) => `typeof ${desugarL0Expr(e)}`);
    s = s.replace(/unary:!\(([^()]*)\)/g, (_, e) => `!${desugarL0Expr(e)}`);
    s = s.replace(/unary:-\(([^()]*)\)/g, (_, e) => `-(${desugarL0Expr(e)})`);

    // op:OP(args) with nested parens
    let opOut = '';
    let i = 0;
    while (i < s.length) {
      const idx = s.indexOf('op:', i);
      if (idx < 0) {
        opOut += s.slice(i);
        break;
      }
      opOut += s.slice(i, idx);
      const rest = s.slice(idx + 3);
      const om = rest.match(/^([=!<>&|^+\-*/%]+)\(/);
      if (!om) {
        opOut += 'op:';
        i = idx + 3;
        continue;
      }
      const op = om[1];
      const openIdx = idx + 3 + om[0].length - 1;
      const matched = matchCallArgs(s, openIdx);
      if (!matched) {
        opOut += 'op:';
        i = idx + 3;
        continue;
      }
      const parts = splitTopArgs(matched.args).map(desugarL0Expr);
      const infix = OP_INFIX[op] || op;
      if (op === '=' || op === '|=') opOut += `${parts[0]}${infix}${parts[1]}`;
      else if (parts.length === 1) opOut += `${infix}${parts[0]}`;
      else if (parts.length === 2) opOut += `${parts[0]}${infix}${parts[1]}`;
      else opOut += parts.join(infix);
      i = matched.end + 1;
    }
    s = opOut;

    if (s === before) break;
  }

  s = s.replace(/\bexpr=/g, '');
  s = s.replace(/\breturn=/g, '^');
  s = s.replace(/\bvar\s+/g, '');
  s = s.replace(/\s+/g, '');
  return s;
}

function hoistClosureAssigns(s) {
  const assigns = [];
  let out = '';
  let i = 0;
  const text = String(s || '');
  while (i < text.length) {
    const m = text.slice(i).match(/^([A-Za-z_$][\w$]*)=~\(/);
    const atStmt = i === 0 || /[;{}]/.test(text[i - 1]);
    if (m && atStmt) {
      const openP = i + m[0].length - 1;
      const closeP = findMatching(text, openP, '(', ')');
      if (closeP >= 0) {
        let j = closeP + 1;
        while (j < text.length && /\s/.test(text[j])) j++;
        if (text[j] === '{') {
          const closeB = findMatching(text, j, '{', '}');
          if (closeB >= 0) {
            assigns.push(text.slice(i, closeB + 1));
            i = closeB + 1;
            if (text[i] === ';') i++;
            continue;
          }
        }
      }
    }
    out += text[i];
    i++;
  }
  if (!assigns.length) return text;
  return `${assigns.join(';')};${out}`;
}

function skipRegexLit(s, i) {
  let j = i + 1;
  let inClass = false;
  while (j < s.length) {
    if (s[j] === '\\') { j += 2; continue; }
    if (s[j] === '[' && !inClass) { inClass = true; j++; continue; }
    if (s[j] === ']' && inClass) { inClass = false; j++; continue; }
    if (s[j] === '/' && !inClass) {
      j++;
      while (j < s.length && /[gimsuy]/.test(s[j])) j++;
      return j;
    }
    if (s[j] === '\n') return i + 1;
    j++;
  }
  return i + 1;
}

function findMatching(s, openIdx, openCh, closeCh) {
  let depth = 0;
  let quote = null;
  for (let i = openIdx; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === '\\') { i++; continue; }
      if (quote === '`' && c === '$' && s[i + 1] === '{') {
        const inner = findMatching(s, i + 1, '{', '}');
        if (inner >= 0) i = inner;
        continue;
      }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '/' && openCh !== '/') {
      let k = i - 1;
      while (k >= 0 && /\s/.test(s[k])) k--;
      const prev = k < 0 ? '' : s[k];
      if (!prev || /[=(:,;!?{[&|^~+\-*%<>]/.test(prev)) {
        i = skipRegexLit(s, i) - 1;
        continue;
      }
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

function rewriteControlBlocks(s, keyword, sigil) {
  let out = '';
  let i = 0;
  const token = keyword + '(';
  while (i < s.length) {
    const idx = s.indexOf(token, i);
    if (idx < 0) {
      out += s.slice(i);
      break;
    }
    // word boundary before keyword
    if (idx > 0 && /[A-Za-z0-9_$]/.test(s[idx - 1])) {
      out += s.slice(i, idx + 1);
      i = idx + 1;
      continue;
    }
    out += s.slice(i, idx);
    const openParen = idx + keyword.length;
    const closeParen = findMatching(s, openParen, '(', ')');
    if (closeParen < 0) {
      out += token;
      i = idx + token.length;
      continue;
    }
    const head = s.slice(openParen + 1, closeParen);
    let j = closeParen + 1;
    while (j < s.length && s[j] === ' ') j++;
    if (s[j] !== '{') {
      out += `${sigil}(${desugarL0Expr(head)})`;
      i = closeParen + 1;
      continue;
    }
    const closeBrace = findMatching(s, j, '{', '}');
    if (closeBrace < 0) {
      out += token;
      i = idx + token.length;
      continue;
    }
    const body = s.slice(j + 1, closeBrace);
    const b = splitSemi(body).map(desugarL0Stmt).filter(Boolean).join(';');
    if (keyword === 'for') {
      const parts = head.split(';').map((p) => desugarL0Expr(p.trim()));
      out += `#(${parts.join(';')}){${b}}`;
    } else {
      out += `${sigil}(${desugarL0Expr(head)}){${b}}`;
    }
    i = closeBrace + 1;
  }
  return out;
}

function desugarL0Stmt(stmt) {
  let s = String(stmt || '').trim();
  if (!s || s === '?' || s.startsWith('GAP:')) return '';

  s = rewriteControlBlocks(s, 'if', '?');
  s = rewriteControlBlocks(s, 'for', '#');
  s = s.replace(/\belse\{/g, ':{');

  let out = desugarL0Expr(s);
  out = out.replace(/^return(?=[A-Za-z_$0-9(])/, '^');
  out = out.replace(/^return/, '^');
  return out;
}

function splitSemi(body) {
  const out = [];
  let cur = '';
  let depth = 0;
  let quote = null;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (quote) {
      cur += c;
      if (c === '\\' && i + 1 < body.length) {
        cur += body[++i];
        continue;
      }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      cur += c;
      continue;
    }
    if (c === '{' || c === '(') {
      depth++;
      cur += c;
      continue;
    }
    if (c === '}' || c === ')') {
      depth--;
      cur += c;
      continue;
    }
    if (c === ';' && depth === 0) {
      if (cur.trim()) out.push(cur.trim());
      cur = '';
      continue;
    }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function shortenLocals(body) {
  // Compress locals; never rewrite property names after `.`
  const map = [
    ['strA', 'A'],
    ['strB', 'B'],
    ['lenA', 'n'],
    ['result', 'r'],
    ['aLen', 'aL'],
    ['bLen', 'bL'],
    ['bufA', 'ba'],
    ['bufB', 'bb'],
    ['value', 'v'],
    ['options', 'o'],
    ['floatValue', 'f'],
    ['results', 'r'],
    ['mag', 'm'],
    ['unit', 'u'],
    ['val', 'v'],
  ];
  let s = body;
  for (const [from, to] of map) {
    const re = new RegExp(`(?<!\\.)\\b${from}\\b`, 'g');
    s = s.replace(re, to);
  }
  return s;
}

function braceSingleStmtControls(s) {
  // ?(cond)stmt; → ?(cond){stmt};  (same for # and :)
  // Depth-aware: do not stop at `{` inside exprs like ^(((__c)=>{...})(x))
  const apply = (sigilChar) => {
    let out = '';
    let i = 0;
    while (i < s.length) {
      const idx = s.indexOf(sigilChar + '(', i);
      if (idx < 0) {
        out += s.slice(i);
        break;
      }
      out += s.slice(i, idx);
      const open = idx + 1; // '('
      const matched = matchCallArgs(s, open);
      if (!matched) {
        out += sigilChar;
        i = idx + 1;
        continue;
      }
      let j = matched.end + 1;
      while (j < s.length && s[j] === ' ') j++;
      if (s[j] === '{') {
        out += s.slice(idx, j);
        i = j;
        continue;
      }
      let k = j;
      let depth = 0;
      while (k < s.length) {
        const ch = s[k];
        if (ch === "'" || ch === '"' || ch === '`') {
          const q = ch;
          k++;
          while (k < s.length) {
            if (s[k] === '\\') { k += 2; continue; }
            if (s[k] === q) { k++; break; }
            k++;
          }
          continue;
        }
        if (ch === '(' || ch === '{' || ch === '[') depth++;
        else if (ch === ')' || ch === '}' || ch === ']') {
          if (depth === 0) break;
          depth--;
        } else if (ch === ';' && depth === 0) break;
        k++;
      }
      const stmt = s.slice(j, k).trim();
      out += `${sigilChar}(${matched.args}){${stmt}}`;
      i = k;
    }
    return out;
  };
  s = apply('?');
  s = apply('#');
  s = apply(':');
  s = s.replace(/\belse\s+(?!\{)([^;{}]+);/g, (_m, stmt) => `:{${stmt.trim()}};`);
  s = s.replace(/\belse\s+(?!\{)([^;{}]+)$/g, (_m, stmt) => `:{${stmt.trim()}}`);
  s = s.replace(/\belse\s+(?!\{)([^;{}]+)(?=\})/g, (_m, stmt) => `:{${stmt.trim()}}`);
  return s;
}

/**
 * Peripheral: desugar `a${x}b` → ("a"+x+"b") so LIN emit never sees backticks.
 * Does not touch verifier / semantic_hash / behavior_eq nucleus.
 */
export function desugarTemplateLiterals(src) {
  const s = String(src || '');
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "'" || c === '"') {
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
    if (c !== '`') {
      out += c;
      i++;
      continue;
    }
    // template literal
    i++;
    const parts = [];
    let lit = '';
    while (i < s.length) {
      if (s[i] === '\\' && i + 1 < s.length) {
        const n = s[i + 1];
        if (n === '`') { lit += '`'; i += 2; continue; }
        if (n === '$') { lit += '$'; i += 2; continue; }
        if (n === '\\') { lit += '\\'; i += 2; continue; }
        if (n === 'n') { lit += '\n'; i += 2; continue; }
        if (n === 'r') { lit += '\r'; i += 2; continue; }
        if (n === 't') { lit += '\t'; i += 2; continue; }
        lit += n;
        i += 2;
        continue;
      }
      if (s[i] === '`') {
        i++;
        break;
      }
      if (s[i] === '$' && s[i + 1] === '{') {
        parts.push(JSON.stringify(lit));
        lit = '';
        i += 2;
        let depth = 1;
        let expr = '';
        while (i < s.length && depth > 0) {
          if (s[i] === '{') depth++;
          else if (s[i] === '}') {
            depth--;
            if (depth === 0) {
              i++;
              break;
            }
          }
          if (depth > 0) expr += s[i];
          i++;
        }
        parts.push(`String(${desugarTemplateLiterals(expr)})`);
        continue;
      }
      lit += s[i];
      i++;
    }
    parts.push(JSON.stringify(lit));
    const joined = parts.filter((p) => p !== '""').join('+') || '""';
    out += `(${joined})`;
  }
  return out;
}

/**
 * Peripheral: desugar cond?a:b → ((__c)=>{if(__c){return(a);}return(b);})(cond)
 * so ternary `?(` never collides with LIN if-sigil `?(`.
 */
export function desugarTernaries(src) {
  let s = String(src || '');
  for (let pass = 0; pass < 64; pass++) {
    const next = desugarOneTernary(s);
    if (next === s) break;
    s = next;
  }
  return s;
}

function desugarOneTernary(s) {
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "'" || c === '"' || c === '`') {
      const q = c;
      i++;
      while (i < s.length) {
        if (s[i] === '\\') { i += 2; continue; }
        if (s[i] === q) { i++; break; }
        i++;
      }
      continue;
    }
    if (c !== '?') { i++; continue; }
    // skip ?? and ?.
    if (s[i + 1] === '?' || s[i + 1] === '.') { i += 2; continue; }
    // find start of condition: walk left over expr
    let condEnd = i;
    let condStart = i - 1;
    let depth = 0;
    while (condStart >= 0) {
      const ch = s[condStart];
      if (ch === ')' || ch === '}' || ch === ']') depth++;
      else if (ch === '(' || ch === '{' || ch === '[') {
        if (depth === 0) break;
        depth--;
      } else if (depth === 0 && /[;{},:]/.test(ch)) break;
      else if (
        depth === 0 && ch === '='
        && s[condStart + 1] !== '=' && s[condStart + 1] !== '>'
        && !/[=!<>]/.test(s[condStart - 1] || '')
      ) break;
      else if (depth === 0 && /\s/.test(ch)) {
        // keep `return|throw|yield` OUTSIDE ternary so
        // `return cond?a:b` → `return IIFE(cond)` (not IIFE(return cond))
        const before = s.slice(0, condStart + 1).replace(/\s+$/u, '');
        if (/\b(return|throw|yield)$/u.test(before)) break;
      }
      condStart--;
    }
    condStart++;
    while (condStart < condEnd && /\s/.test(s[condStart])) condStart++;
    // find colon at depth 0
    let j = i + 1;
    depth = 0;
    let colon = -1;
    while (j < s.length) {
      const ch = s[j];
      if (ch === "'" || ch === '"' || ch === '`') {
        const q = ch;
        j++;
        while (j < s.length) {
          if (s[j] === '\\') { j += 2; continue; }
          if (s[j] === q) { j++; break; }
          j++;
        }
        continue;
      }
      if (ch === '(' || ch === '{' || ch === '[') depth++;
      else if (ch === ')' || ch === '}' || ch === ']') {
        if (depth === 0) break;
        depth--;
      } else if (ch === '?' && depth === 0) {
        // nested ternary — skip this ? for now (process inner later via outer loop... actually process rightmost)
        // let outer loop handle; for nested, find matching : for THIS ?
      } else if (ch === ':' && depth === 0) {
        colon = j;
        break;
      }
      j++;
    }
    if (colon < 0) { i++; continue; }
    // else branch until ; , ) } ] or end at depth 0
    let k = colon + 1;
    depth = 0;
    while (k < s.length) {
      const ch = s[k];
      if (ch === "'" || ch === '"' || ch === '`') {
        const q = ch;
        k++;
        while (k < s.length) {
          if (s[k] === '\\') { k += 2; continue; }
          if (s[k] === q) { k++; break; }
          k++;
        }
        continue;
      }
      if (ch === '(' || ch === '{' || ch === '[') depth++;
      else if (ch === ')' || ch === '}' || ch === ']') {
        if (depth === 0) break;
        depth--;
      } else if (depth === 0 && /[;,]/.test(ch)) break;
      else if (depth === 0) {
        const prev = k > 0 ? s[k - 1] : '';
        const rest = s.slice(k).replace(/^\s+/, '');
        if (!/[\w$.]/.test(prev) && /^(case\b|default\s*:|const\b|let\b|var\b)/.test(rest)) break;
        if ((ch === '\n' || ch === '\r') && /^(return\b|if\b|break\b|switch\b|\})/.test(rest)) break;
      }
      k++;
    }
    const cond = s.slice(condStart, condEnd).trim();
    const thenP = s.slice(i + 1, colon).trim();
    const elseP = s.slice(colon + 1, k).trim();
    if (!cond || !thenP || !elseP) { i++; continue; }
    // avoid rewriting already-desugared or LIN if-sigils (?(...){)
    if (/^[\s]*\(/.test(thenP) && s[colon + 1] === undefined) { i++; continue; }
    const repl = `(((__c)=>{if(__c){return(${thenP});}return(${elseP});})(${cond}))`;
    return s.slice(0, condStart) + repl + s.slice(k);
  }
  return s;
}

function protectRegexLiterals(s) {
  const held = [];
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "'" || c === '"' || c === '`') {
      const q = c;
      out += c;
      i++;
      while (i < s.length) {
        if (s[i] === '\\') { out += s[i] + (s[i + 1] || ''); i += 2; continue; }
        out += s[i];
        if (s[i] === q) { i++; break; }
        i++;
      }
      continue;
    }
    if (c === '/') {
      const prev = out.replace(/\s+$/, '');
      const prevCh = prev[prev.length - 1] || '';
      const canBeRegex = !prevCh || /[=(:,;!?{[&|^~+\-*%<>]/.test(prevCh)
        || /\b(return|throw|case|in|of)$/.test(prev);
      if (canBeRegex && prevCh !== '/') {
        let j = i + 1;
        let closed = false;
        while (j < s.length) {
          if (s[j] === '\\') { j += 2; continue; }
          if (s[j] === '\n') break;
          if (s[j] === '/') { j++; closed = true; break; }
          if (s[j] === '[') {
            j++;
            while (j < s.length && s[j] !== ']') {
              if (s[j] === '\\') j += 2;
              else j++;
            }
            j++;
            continue;
          }
          j++;
        }
        if (closed) {
          while (j < s.length && /[a-z]/i.test(s[j])) j++;
          const tok = `\u0000RX${held.length}\u0000`;
          held.push(s.slice(i, j));
          out += tok;
          i = j;
          continue;
        }
      }
    }
    out += c;
    i++;
  }
  return { text: out, held };
}

function restoreHeld(s, held) {
  let out = s;
  for (let i = 0; i < held.length; i++) {
    out = out.split(`\u0000RX${i}\u0000`).join(held[i]);
  }
  return out;
}

/** Peripheral: hold '...' / "..." so space/punct compaction cannot mutate string meaning. */
function protectQuotedStrings(s) {
  let out = '';
  const held = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "'" || c === '"') {
      let j = i + 1;
      while (j < s.length) {
        if (s[j] === '\\') { j += 2; continue; }
        if (s[j] === c) { j++; break; }
        j++;
      }
      const tok = `\u0000ST${held.length}\u0000`;
      held.push(s.slice(i, j));
      out += tok;
      i = j;
      continue;
    }
    out += c;
    i++;
  }
  return { text: out, held };
}

function restoreQuoted(s, held) {
  let out = s;
  for (let i = 0; i < held.length; i++) {
    out = out.split(`\u0000ST${i}\u0000`).join(held[i]);
  }
  return out;
}

function scanArrowExpr(s, start) {
  // s starts after '=>'. Returns the expression text and the index where it ends.
  let i = start;
  while (i < s.length && /\s/.test(s[i])) i++;
  let depthParen = 0;
  let depthBrace = 0;
  let depthBracket = 0;
  let inTemplate = false;
  let quote = null;
  const exprStart = i;
  while (i < s.length) {
    const c = s[i];
    if (quote) {
      if (c === '\\') { i += 2; continue; }
      if (c === quote) { quote = null; }
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      if (c === '`') inTemplate = true;
      quote = c;
      i++;
      continue;
    }
    if (c === '$' && s[i + 1] === '{' && inTemplate) {
      i += 2;
      depthBrace++;
      continue;
    }
    if (c === '(') { depthParen++; i++; continue; }
    if (c === ')') {
      if (depthParen === 0 && depthBrace === 0 && depthBracket === 0) break;
      depthParen--;
      i++;
      continue;
    }
    if (c === '{') {
      if (depthBrace === 0 && depthParen === 0 && depthBracket === 0) break; // block handled elsewhere
      depthBrace++;
      i++;
      continue;
    }
    if (c === '}') {
      if (depthBrace === 0) break;
      depthBrace--;
      i++;
      continue;
    }
    if (c === '[') { depthBracket++; i++; continue; }
    if (c === ']') {
      if (depthBracket === 0 && depthParen === 0 && depthBrace === 0) break;
      depthBracket--;
      i++;
      continue;
    }
    if ((c === ';' || c === ',' || c === '?' || c === ':') && depthParen === 0 && depthBrace === 0 && depthBracket === 0) break;
    if ((c === '\n' || c === '\r') && depthParen === 0 && depthBrace === 0 && depthBracket === 0) {
      const rest = s.slice(i + 1).replace(/^\s+/, '');
      if (/^(const\b|let\b|var\b|function\b|if\b|for\b|while\b|return\b|switch\b|[A-Za-z_$][\w$]*\s*[=.])/.test(rest)) break;
    }
    i++;
  }
  return { expr: s.slice(exprStart, i).trim(), end: i };
}

function desugarClosures(src) {
  // Convert anonymous function expressions and arrow functions inside a body
  // to LIN closure syntax ~(params){body} so they remain lexical closures.
  let s = String(src || '');
  // protect strings so we do not rewrite inside literals
  const qs = protectQuotedStrings(s);
  s = qs.text;

  // const/let/var x = function(p){...}  ->  x=~(p){...}
  // also: x = async function(p){...}
  s = s.replace(
    /(^|[;=,({\[]\s*)\b(var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function(?:\s+[A-Za-z_$][\w$]*)?\s*\(([^)]*)\)\s*\{/g,
    (_m, before, _decl, name, params) => `${before}${name}=~(${params}){`,
  );

  // bare assignment / return / argument: = function(p){ -> = ~(p){
  s = s.replace(
    /([=,:;({\[]\s*)(?:async\s+)?function(?:\s+[A-Za-z_$][\w$]*)?\s*\(([^)]*)\)\s*\{/g,
    (_m, before, params) => `${before}~(${params}){`,
  );

  // return (p)=>{...}  — prefix class [=,:;({\[] misses `return`
  s = s.replace(
    /\breturn\s+\(([^)]*)\)\s*=>\s*\{/g,
    (_m, params) => `return ~(${params}){`,
  );
  s = s.replace(
    /\breturn\s+([A-Za-z_$][\w$]*)\s*=>\s*\{/g,
    (_m, param) => `return ~(${param}){`,
  );
  // arrow block: (p)=>{...}  and p=>{...}
  s = s.replace(
    /([=,:;({\[]\s*)(?:async\s*)?\(([^)]*)\)\s*=>\s*\{/g,
    (_m, before, params) => `${before}~(${params}){`,
  );
  s = s.replace(
    /([=,:;({\[]\s*)(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>\s*\{/g,
    (_m, before, param) => `${before}~(${param}){`,
  );

  function rewriteArrows(pattern, isParens) {
    for (let pass = 0; pass < 32; pass++) {
      let out = '';
      let i = 0;
      let changed = false;
      while (i < s.length) {
        pattern.lastIndex = i;
        const m = pattern.exec(s);
        if (!m) {
          out += s.slice(i);
          break;
        }
        out += s.slice(i, m.index);
        const before = m[1];
        const paramPart = m[2];
        const arrowOffset = m.index + m[0].length;
        const scanned = scanArrowExpr(s, arrowOffset);
        out += `${before}~(${paramPart}){^${scanned.expr}}`;
        i = scanned.end;
        changed = true;
      }
      s = out;
      if (!changed) break;
    }
  }

  // arrow expression body with balanced parens/brackets/braces/strings.
  rewriteArrows(/(\breturn\s+)(?:async\s*)?\(([^)]*)\)\s*=>/g, true);
  rewriteArrows(/(\breturn\s+)(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>/g, false);
  rewriteArrows(/([=,:;({\[]\s*)(?:async\s*)?\(([^)]*)\)\s*=>/g, true);
  rewriteArrows(/([=,:;({\[]\s*)(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>/g, false);

  return restoreQuoted(s, qs.held);
}

function protectClosuresForSigils(s) {
  // Replace closure bodies with placeholders so later ASI/space compaction
  // does not break multi-line arrow expressions that were folded into closures.
  const held = [];
  let out = '';
  let i = 0;
  while (i < s.length) {
    const idx = s.indexOf('~(', i);
    if (idx < 0) {
      out += s.slice(i);
      break;
    }
    out += s.slice(i, idx);
    const openParen = idx + 1;
    const closeParen = findMatching(s, openParen, '(', ')');
    if (closeParen < 0) {
      out += '~(';
      i = idx + 2;
      continue;
    }
    let j = closeParen + 1;
    while (j < s.length && /\s/.test(s[j])) j++;
    if (s[j] !== '{') {
      out += s.slice(idx, j);
      i = j;
      continue;
    }
    const closeBrace = findMatching(s, j, '{', '}');
    if (closeBrace < 0) {
      out += '~(';
      i = idx + 2;
      continue;
    }
    const tok = `\u0000CL${held.length}\u0000`;
    const bodyNorm = insertJsAsi(stripTsFromJs(s.slice(j + 1, closeBrace)))
      .replace(/\s+/g, ' ')
      .replace(/\{;/g, '{')
      .replace(/;\}/g, '}')
      .trim();
    held.push(`{${bodyNorm}}`);
    out += s.slice(idx, j) + tok;
    i = closeBrace + 1;
  }
  return { text: out, held };
}

function restoreClosuresForSigils(s, held) {
  let out = s;
  for (let i = 0; i < held.length; i++) {
    out = out.split(`\u0000CL${i}\u0000`).join(held[i]);
  }
  return out;
}

function stripTsFromJs(s) {
  let t = String(s || '');
  t = t.replace(/\b(let|const|var)\s+([A-Za-z_$][\w$]*)\s*:\s*[^=;{]+?=/g, '$1 $2=');
  t = t.replace(/\):\s*[A-Za-z_$][\w$<>|&\[\]\s]+\s*=>/g, ')=>');
  t = t.replace(/([A-Za-z_$][\w$]*)\?\s*:\s*[A-Za-z_$][\w$<>|&\[\]\s]+/g, '$1');
  t = t.replace(/([A-Za-z_$][\w$]*)\s*:\s*[A-Za-z_$][\w$<>|&\[\]]+(?:\s*[|&]\s*[A-Za-z_$][\w$<>|&\[\]]+)*\s*(?=[,)=])/g, '$1');
  return t;
}

function insertJsAsi(s) {
  let t = String(s || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  t = t.replace(/\n\s*(?=if\b|for\b|while\b|return\b|const\b|let\b|var\b|else\b|throw\b|break\b|continue\b)/g, ';\n');
  t = t.replace(/([^\s])(\n\s*)(?=[A-Za-z_$][\w$]*\s*(?:[+\-*/%^|&]=|[=(.\[]))/g, (all, prev, ws) => {
    if (/[|&+,([?:=+\-*/%<>!.{]/.test(prev)) return prev + ws;
    return `${prev};${ws}`;
  });
  return t;
}

function applySourceSigils(jsBody) {
  let s = String(jsBody || '');
  // strip comments before compaction (otherwise // eats the rest of the AIL/JS line)
  s = s.replace(/\/\*[\s\S]*?\*\//g, '');
  s = s.replace(/(^|[^:])\/\/.*$/gm, '$1');
  // preserve closures before stripping var/let/const and other sigils
  s = s.replace(/\bfunction\s+[A-Za-z_$][\w$]*\s*\([^;{]*\)\s*:\s*[^;{]+;/g, '');
  s = s.replace(/\):\s*[A-Za-z_$][\w$<>|&\[\]\s]+\s*=>/g, ')=>');
  s = s.replace(
    /(^|[;{}]\s*)function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{/g,
    '$1$2=~($3){',
  );
  s = desugarClosures(s);
  s = s.replace(/\{([^{}]*)\}/g, (full, inner) => {
    let depth = 0;
    for (let i = 0; i < inner.length; i++) {
      const ch = inner[i];
      if (ch === '(' || ch === '[') depth++;
      else if ((ch === ')' || ch === ']') && depth) depth--;
      else if (depth === 0 && ch === '.' && inner[i + 1] === '.' && inner[i + 2] === '.') {
        let p = i - 1;
        while (p >= 0 && /\s/.test(inner[p])) p--;
        if (p < 0 || inner[p] === ',') return '_lia_obj()';
      }
    }
    return full;
  });
  // protect closure bodies from ASI insertion and whitespace compaction
  const protectedClosures = protectClosuresForSigils(s);
  s = protectedClosures.text;
  // peripheral: templates → concat before sigil compaction
  s = desugarTemplateLiterals(s);
  const qs = protectQuotedStrings(s);
  s = qs.text;
  s = insertJsAsi(s);
  const rx = protectRegexLiterals(s);
  s = rx.text;
  s = s.replace(/\s+/g, ' ').trim();
  // peripheral: ternaries before if→?( so `c?(x):(y)` never becomes if-sigil
  s = desugarTernaries(s);
  s = s.replace(/\breturn\s+/g, '^');
  s = s.replace(/\belse\s+if\s*\(/g, ':(');
  s = s.replace(/\bif\s*\(/g, '?(');
  s = s.replace(/\bfor\s*\(/g, '#(');
  // expand `var a=1, b, c=2` so comma decls are not leftover reads
  s = s.replace(/\b(var|let|const)\s+([^;]+);/g, (full, kw, list, offset, src) => {
    const before = src.slice(Math.max(0, offset - 10), offset);
    if (/(?:#|\bfor)\(\s*$/.test(before)) return full;
    const parts = [];
    let buf = '';
    let d = 0;
    let q = null;
    for (let i = 0; i < list.length; i++) {
      const c = list[i];
      if (q) {
        if (c === '\\') { buf += c + (list[i + 1] || ''); i++; continue; }
        buf += c;
        if (c === q) q = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') { q = c; buf += c; continue; }
      if (c === '(' || c === '{' || c === '[') d++;
      else if (c === ')' || c === '}' || c === ']') d--;
      if (c === ',' && d === 0) { parts.push(buf.trim()); buf = ''; continue; }
      buf += c;
    }
    if (buf.trim()) parts.push(buf.trim());
    if (parts.length <= 1) return full;
    return parts.map((p) => (
      /^[A-Za-z_$][\w$]*$/.test(p) ? `${kw} ${p}=undefined;` : `${kw} ${p};`
    )).join('');
  });
  // decl-only becomes assign so compileLiaToJs emits `var id`
  s = s.replace(/\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*;/g, '$1=undefined;');
  s = s.replace(/\bvar\s+/g, '');
  s = s.replace(/\blet\s+/g, '');
  s = s.replace(/\bconst\s+/g, '');
  // destructure assign after const-strip: {a,b=x}=y → ({a,b=x}=y)
  s = s.replace(
    /(^|[;{])\s*(\{[^{}]*\}|\[[^[\]]*\])\s*=\s*([^;]+)/g,
    '$1($2=$3)',
  );
  s = braceSingleStmtControls(s);
  s = s.replace(/\belse\s*\{/g, ':{');
  s = s.replace(/\s*([{};,?=|&<>!+\-*/%^])\s*/g, '$1');
  s = s.replace(/([^;{}(\[,:?])while\(/g, '$1;while(');
  s = restoreHeld(s, rx.held);
  s = s.replace(/;+/g, ';');
  s = s.replace(/;\}/g, '}');
  s = s.replace(/\{;/g, '{');
  s = s.replace(/!==\s*(null|undefined)\b/g, '\u0000NE_$1\u0000');
  s = s.replace(/===\s*(null|undefined)\b/g, '\u0000EQ_$1\u0000');
  s = s.replace(/===/g, '==').replace(/!==/g, '!=');
  s = s.replace(/\u0000EQ_(null|undefined)\u0000/g, '===$1');
  s = s.replace(/\u0000NE_(null|undefined)\u0000/g, '!==$1');
  s = restoreQuoted(s, qs.held);
  s = restoreClosuresForSigils(s, protectedClosures.held);
  s = desugarTernaries(s);
  s = s.replace(/~~\(/g, '\u0000DNOT(');
  s = s.replace(/~\(([^)]*)\)/g, (_, p) => {
    const cleaned = String(p).split(',').map((x) => {
      const t = x.trim();
      if (!t) return '';
      const def = t.match(/^([A-Za-z_$][\w$]*)\s*=\s*(.+)$/);
      if (def) return `${def[1]}=${def[2].trim()}`;
      const rest = t.startsWith('...');
      const id = t.replace(/^\.\.\./, '').replace(/:\s*[\s\S]+$/, '').trim();
      return id && /^[A-Za-z_$][\w$]*$/.test(id) ? `${rest ? '...' : ''}${id}` : '';
    }).filter(Boolean);
    return `~(${cleaned.join(',')})`;
  });
  s = s.replace(/\u0000DNOT\(/g, '~~(');
  s = hoistClosureAssigns(s);
  const earlyRet = [];
  s = s.replace(/\^([A-Za-z_$][\w$]*);(?=[^;]*\1=~)/g, (_, id) => {
    earlyRet.push(id);
    return '';
  });
  for (const id of earlyRet) {
    if (!new RegExp(`\\^${id}\\b`).test(s)) s += `;^${id}`;
  }
  s = s.replace(/[\r\n]+/g, ' ');
  return s;
}

function splitParams(raw) {
  let s = String(raw || '').trim();
  if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
    s = s.slice(1, -1);
  }
  return s
    .split(',')
    .map((p) => p.trim())
    .map((p) => p.replace(/^\.\.\./, '').replace(/\?$/, '').replace(/:\s*[\s\S]+$/, '').trim())
    .filter((p) => p && /^[A-Za-z_$][\w$]*$/.test(p));
}

function extractBraceBody(text, openBraceIdx) {
  let depth = 1;
  let i = openBraceIdx + 1;
  let quote = null;
  let inRe = false;
  let inClass = false;
  for (; i < text.length; i++) {
    const c = text[i];
    if (inRe) {
      if (c === '\\') { i++; continue; }
      if (c === '[' && !inClass) inClass = true;
      else if (c === ']' && inClass) inClass = false;
      else if (c === '/' && !inClass) inRe = false;
      continue;
    }
    if (quote) {
      if (c === '\\') { i++; continue; }
      if (quote === '`' && c === '$' && text[i + 1] === '{') {
        i += 2;
        const inner = extractBraceBody(text, i - 1);
        i = inner.end;
        continue;
      }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '/') {
      const next = text[i + 1];
      if (next === '/') {
        while (i < text.length && text[i] !== '\n') i++;
        continue;
      }
      if (next === '*') {
        i += 2;
        while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++;
        i++;
        continue;
      }
      const before = text.slice(Math.max(0, i - 24), i).trimEnd();
      const last = before[before.length - 1];
      if (!last || /[({[=,:;!&|?+~\-*%^<>]/.test(last) || /\b(return|throw)$/.test(before)) {
        inRe = true;
        continue;
      }
    }
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) break;
    }
  }
  return { body: text.slice(openBraceIdx + 1, i), end: i };
}

function skipWsComments(text, i) {
  while (i < text.length) {
    while (i < text.length && /\s/.test(text[i])) i++;
    if (text[i] === '/' && text[i + 1] === '/') {
      while (i < text.length && text[i] !== '\n') i++;
      continue;
    }
    if (text[i] === '/' && text[i + 1] === '*') {
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++;
      i += 2;
      continue;
    }
    break;
  }
  return i;
}

function matchParen(text, openIdx) {
  if (text[openIdx] !== '(') return -1;
  let d = 0;
  let q = null;
  for (let i = openIdx; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '\\') { i++; continue; }
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { q = c; continue; }
    if (c === '/' && text[i + 1] === '/') {
      while (i < text.length && text[i] !== '\n') i++;
      continue;
    }
    if (c === '/' && text[i + 1] === '*') {
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++;
      i += 1;
      continue;
    }
    if (c === '(') d++;
    else if (c === ')') {
      d--;
      if (d === 0) return i;
    }
  }
  return -1;
}

/** Extract expression after `=>` until ; , newline, or unbalanced closer. */
function extractArrowExpr(text, start) {
  let i = skipWsComments(text, start);
  let depthParen = 0;
  let depthBrace = 0;
  let depthBracket = 0;
  let quote = null;
  let inRe = false;
  let inClass = false;
  while (i < text.length) {
    const c = text[i];
    if (inRe) {
      if (c === '\\') { i += 2; continue; }
      if (c === '[' && !inClass) inClass = true;
      else if (c === ']' && inClass) inClass = false;
      else if (c === '/' && !inClass) inRe = false;
      i++;
      continue;
    }
    if (quote) {
      if (c === '\\') { i += 2; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; i++; continue; }
    if (c === '/') {
      const next = text[i + 1];
      if (next === '/') {
        while (i < text.length && text[i] !== '\n') i++;
        continue;
      }
      if (next === '*') {
        i += 2;
        while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++;
        i += 2;
        continue;
      }
      const before = text.slice(Math.max(0, start), i).trimEnd();
      const last = before[before.length - 1];
      if (!last || /[({[=,:;!&|?+~\-*%^<>]/.test(last) || /\b(return|throw)$/.test(before)) {
        inRe = true;
        i++;
        continue;
      }
    }
    if ((c === '\n' || c === '\r') && depthParen === 0 && depthBrace === 0 && depthBracket === 0) break;
    if (c === '(') depthParen++;
    else if (c === ')') {
      if (depthParen === 0) break;
      depthParen--;
    } else if (c === '{') depthBrace++;
    else if (c === '}') {
      if (depthBrace === 0) break;
      depthBrace--;
    } else if (c === '[') depthBracket++;
    else if (c === ']') {
      if (depthBracket === 0) break;
      depthBracket--;
    } else if ((c === ';' || c === ',') && depthParen === 0 && depthBrace === 0 && depthBracket === 0) {
      break;
    }
    i++;
  }
  return { expr: text.slice(start, i).trim().replace(/\s*\/\/[^\n]*$/, ''), end: i };
}

function fnInterval(text, startIdx) {
  // startIdx points at the opening '{' of the function body
  const { body, end } = extractBraceBody(text, startIdx);
  return { body, start: startIdx, end };
}

function intervalsOverlap(a, b) {
  return a.start < b.end && b.start < a.end;
}

/** Extract top-level named functions from JS source (classic + arrow const/let/var). */
export function extractJsFunctions(source) {
  const text = String(source || '');
  const fns = [];
  const push = (name, params, body, extra = {}) => {
    if (!name || fns.some((f) => f.name === name)) return;
    let ps = Array.isArray(params) ? params.slice() : [];
    if (/[{[]/.test(ps.join(','))) ps = ['opts'];
    fns.push({ name, params: ps, body, async: !!extra.async });
  };

  const candidates = [];

  const classic = [
    /(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?::[^{=]+)?\s*\{/g,
    /(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function(?:\s+[A-Za-z_$][\w$]*)?(?:\s*<[^>]*>)?\s*\(([^)]*)\)\s*(?::[^{=]+)?\s*\{/g,
    /(?:module\.)?exports(?:\.([A-Za-z_$][\w$]*))?\s*=\s*(?:async\s+)?function(?:\s+([A-Za-z_$][\w$]*))?(?:\s*<[^>]*>)?\s*\(([^)]*)\)\s*(?::[^{=]+)?\s*\{/g,
  ];
  for (const re of classic) {
    let m;
    while ((m = re.exec(text)) !== null) {
      const open = m.index + m[0].length - 1;
      const iv = fnInterval(text, open);
      const isExports = re.source.includes('exports');
      const name = isExports ? (m[1] || m[2] || 'defaultExport') : m[1];
      const paramsRaw = isExports ? m[3] : m[2];
      const async = /\basync\s+function\b/.test(m[0]);
      candidates.push({
        name,
        params: splitParams(paramsRaw),
        body: iv.body,
        async,
        start: m.index,
        end: iv.end + 1,
      });
    }
  }

  const fnHead = /(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g;
  let fh;
  while ((fh = fnHead.exec(text)) !== null) {
    const name = fh[1];
    if (candidates.some((c) => c.name === name)) continue;
    let hi = skipWsComments(text, fh.index + fh[0].length);
    if (text[hi] === '<') {
      let ad = 0;
      for (; hi < text.length; hi++) {
        const hc = text[hi];
        if (hc === '<') ad++;
        else if (hc === '>') {
          ad--;
          if (ad === 0) { hi++; break; }
        }
      }
      hi = skipWsComments(text, hi);
    }
    if (text[hi] !== '(') continue;
    const open = hi;
    const closed = matchParen(text, open);
    if (closed < 0) continue;
    let i = skipWsComments(text, closed + 1);
    if (text[i] === ':') {
      i++;
      let d = 0;
      while (i < text.length) {
        const c = text[i];
        if (c === '{' && d === 0) break;
        if (c === '{' || c === '(' || c === '[') d++;
        else if (c === '}' || c === ')' || c === ']') d--;
        i++;
      }
    }
    i = skipWsComments(text, i);
    if (text[i] !== '{') continue;
    const iv = fnInterval(text, i);
    candidates.push({
      name,
      params: splitParams(text.slice(open + 1, closed)),
      body: iv.body,
      async: /async\s+function/.test(fh[0]),
      start: fh.index,
      end: iv.end + 1,
    });
  }

  // export default function name?(params) { ... }
  const defFn = /export\s+default\s+(?:async\s+)?function(?:\s+([A-Za-z_$][\w$]*))?\s*\(([^)]*)\)\s*\{/g;
  let dfm;
  while ((dfm = defFn.exec(text)) !== null) {
    const open = dfm.index + dfm[0].length - 1;
    const iv = fnInterval(text, open);
    candidates.push({
      name: dfm[1] || 'defaultExport',
      params: splitParams(dfm[2]),
      body: iv.body,
      async: /\basync\s+function\b/.test(dfm[0]),
      start: dfm.index,
      end: iv.end + 1,
    });
  }

  // export default (a,b) => { ... } | export default a => expr
  const defArrow =
    /export\s+default\s+(?:async\s*)?(?:(\([^)]*\))|([A-Za-z_$][\w$]*))\s*=>\s*/g;
  let dam;
  while ((dam = defArrow.exec(text)) !== null) {
    const params = splitParams((dam[1] || dam[2] || '').replace(/^\(|\)$/g, ''));
    let i = dam.index + dam[0].length;
    i = skipWsComments(text, i);
    let body;
    let end;
    if (text[i] === '{') {
      const iv = fnInterval(text, i);
      body = iv.body;
      end = iv.end + 1;
    } else {
      const expr = extractArrowExpr(text, i);
      body = `return ${expr.expr}`;
      end = expr.end;
    }
    candidates.push({
      name: 'defaultExport',
      params,
      body,
      async: /default\s+async\s*/.test(dam[0]),
      start: dam.index,
      end,
    });
  }

  // object methods: name: (a) => ..., name: a => ..., name: function (...) {, name() {
  const objArrow =
    /(?:^|[,{\n])\s*([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:(\([^)]*\))|([A-Za-z_$][\w$]*))\s*=>\s*/g;
  let oam;
  while ((oam = objArrow.exec(text)) !== null) {
    const name = oam[1];
    const params = splitParams((oam[2] || oam[3] || '').replace(/^\(|\)$/g, ''));
    let i = oam.index + oam[0].length;
    i = skipWsComments(text, i);
    let body;
    let end;
    if (text[i] === '{') {
      const iv = fnInterval(text, i);
      body = iv.body;
      end = iv.end + 1;
    } else {
      const expr = extractArrowExpr(text, i);
      body = `return ${expr.expr}`;
      end = expr.end;
    }
    candidates.push({
      name,
      params,
      body,
      async: /:\s*async\s*/.test(oam[0]),
      start: oam.index,
      end,
    });
  }
  const objFn =
    /(?:^|[,{\n])\s*([A-Za-z_$][\w$]*)\s*:\s*(?:async\s+)?function(?:\s+[A-Za-z_$][\w$]*)?\s*\(([^)]*)\)\s*\{/g;
  let ofm;
  while ((ofm = objFn.exec(text)) !== null) {
    const open = ofm.index + ofm[0].length - 1;
    const iv = fnInterval(text, open);
    candidates.push({
      name: ofm[1],
      params: splitParams(ofm[2]),
      body: iv.body,
      async: /\basync\s+function\b/.test(ofm[0]),
      start: ofm.index,
      end: iv.end + 1,
    });
  }
  const objMethod =
    /(?:^|[,{\n])\s*(?!if\b|for\b|while\b|switch\b|catch\b|function\b)([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{/g;
  let omm;
  while ((omm = objMethod.exec(text)) !== null) {
    const open = omm.index + omm[0].length - 1;
    const iv = fnInterval(text, open);
    candidates.push({
      name: omm[1],
      params: splitParams(omm[2]),
      body: iv.body,
      async: false,
      start: omm.index,
      end: iv.end + 1,
    });
  }

  // const name = (a,b) => { ... }  |  const name = (a,b) => expr  |  const name = a => expr
  const arrowRe =
    /(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:(\([^)]*\))|([A-Za-z_$][\w$]*))\s*=>\s*/g;
  let am;
  while ((am = arrowRe.exec(text)) !== null) {
    const name = am[1];
    const params = splitParams((am[2] || am[3] || '').replace(/^\(|\)$/g, ''));
    let i = am.index + am[0].length;
    i = skipWsComments(text, i);
    let body;
    let end;
    if (text[i] === '{') {
      const iv = fnInterval(text, i);
      body = iv.body;
      end = iv.end + 1;
    } else {
      const expr = extractArrowExpr(text, i);
      body = `return ${expr.expr}`;
      end = expr.end;
    }
    const async = /=\s*async\s*/.test(am[0]);
    candidates.push({
      name,
      params,
      body,
      async,
      start: am.index,
      end,
    });
  }

  const classSpans = [];
  const classRe = /\bclass\s+[A-Za-z_$][\w$]*[^{]*\{/g;
  let cm;
  while ((cm = classRe.exec(text)) !== null) {
    const open = cm.index + cm[0].length - 1;
    const iv = fnInterval(text, open);
    classSpans.push({ start: cm.index, end: iv.end + 1 });
  }

  // Keep only candidates that are not nested inside another candidate's full span.
  for (let i = 0; i < candidates.length; i++) {
    const c = candidates[i];
    let nested = false;
    for (const cs of classSpans) {
      if (c.start > cs.start && c.end < cs.end) {
        nested = true;
        break;
      }
    }
    for (let j = 0; j < candidates.length; j++) {
      if (i === j) continue;
      const other = candidates[j];
      if (c.start > other.start && c.end < other.end) {
        nested = true;
        break;
      }
    }
    const slice = text.slice(c.start, Math.min(text.length, c.start + 64));
    const isFnDecl = /^(?:export\s+)?(?:async\s+)?function\s/.test(slice);
    if (nested && braceDepthAt(text, c.start) === 0 && isFnDecl) nested = false;
    if (nested) continue;
    push(c.name, c.params, c.body, { async: c.async });
  }

  return fns;
}

function detectBytesMap(source) {
  if (/kb\s*:\s*1\s*<<\s*10/.test(source) || /map\s*=\s*\{[^}]*kb/.test(source)) return BYTES_K;
  return null;
}

/** Harvest top-level numeric const/let/var into $K (peripheral; not nucleus). */
function braceDepthAt(s, idx) {
  let depth = 0;
  let quote = null;
  for (let i = 0; i < idx && i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === '\\') { i++; continue; }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '{') depth++;
    else if (c === '}') depth--;
  }
  return depth;
}

export function harvestTopNumConsts(source) {
  const env = {};
  const s = String(source || '');
  const re = /(?:^|[\n;])\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)/g;
  let m;
  while ((m = re.exec(s))) {
    if (braceDepthAt(s, m.index) !== 0) continue;
    const expr = m[2].trim();
    if (!/^[-+\d.\s/*()A-Za-z_$]+$/.test(expr)) continue;
    try {
      const keys = Object.keys(env);
      const val = new Function(...keys, `return (${expr});`)(...keys.map((k) => env[k]));
      if (typeof val === 'number' && Number.isFinite(val)) env[m[1]] = val;
    } catch { /* skip */ }
  }
  return env;
}

function formatConstTable(env) {
  const parts = Object.entries(env || {}).map(([k, v]) => `${k}=${v}`);
  return parts.length ? `$K{${parts.join(' ')}}` : null;
}

/**
 * Emit LIA from JS source (default compact path).
 */
export function emitAilFromSource(source, opts = {}) {
  const fns = extractJsFunctions(source).filter((f) => {
    if (!f.name) return false;
    if (opts.namedOnly === false) return true;
    return !isTestishBody([f.body]);
  });
  const lines = [
    LIN_HEADER,
    `^schema_once ^lossy=true ^ops=${opts.ops || DEFAULT_OPS}`,
    GRAMMAR,
  ];
  const k = opts.constTable || formatConstTable(harvestTopNumConsts(source)) || detectBytesMap(source);
  if (k) lines.push(k);

  const importIds = [...String(source || '').matchAll(/\bimport\s*\{([^}]+)\}/g)]
    .flatMap((m) => m[1].split(',').map((s) => s.trim().split(/\s+as\s+/).pop().trim()))
    .filter((id) => id && /^[A-Za-z_$][\w$]*$/.test(id) && !fns.some((f) => f.name === id));
  const importPrelude = importIds.map((id) => `${id}=''`).join(';');
  const names = [];
  for (const f of fns) {
    let body = applySourceSigils(f.body);
    const usedImports = importIds.filter((id) => new RegExp(`\\b${id}\\b`).test(f.body));
    if (usedImports.length) body = `${usedImports.map((id) => `${id}=''`).join(';')};${body}`;
    if (opts.shortenLocals !== false) body = shortenLocals(body);
    if (k) body = body.replace(/\bmap\[/g, '$K[').replace(/\bmap\./g, '$K.');
    // drop trailing semicolon noise
    body = body.replace(/;+$/g, '');
    const params = f.params.map((p) => (opts.shortenLocals === false ? p : shortenLocals(p))).join(',');
    lines.push(`!${f.name}(${params}){${body}}`);
    names.push(f.name);
  }
  if (names.length) lines.push(`=ex{${names.join(',')}}`);
  return lines.join('\n');
}

/**
 * Emit LIA from PROJECT.dicel L0 text.
 */
export function emitAilFromProject(dicelText, opts = {}) {
  const all = parseProjectFns(dicelText);
  const fns = all.filter((f) => {
    if (!f.name) return false;
    if (opts.stripTests !== false && isTestishBody(f.stmts)) return false;
    return true;
  });
  const lines = [
    LIN_HEADER,
    `^schema_once ^lossy=true ^ops=${opts.ops || DEFAULT_OPS}`,
    GRAMMAR,
  ];
  const k = opts.constTable || (/\bmap\b|kb|mb|gb/.test(dicelText) ? BYTES_K : null);
  if (k) lines.push(k);

  const names = [];
  for (const f of fns) {
    const parts = f.stmts.map(desugarL0Stmt).filter(Boolean);
    let body = parts.join(';');
    if (opts.shortenLocals !== false) body = shortenLocals(body);
    if (k) body = body.replace(/\bmap\[/g, '$K[').replace(/\bmap\./g, '$K.');
    // drop L0 holes "?" / "?;" but keep LIA if-sigil "?("
    body = body
      .replace(/;\?(?!\()/g, ';')
      .replace(/^\?(?!\()/g, '')
      .replace(/;+/g, ';')
      .replace(/;\}/g, '}')
      .replace(/\{;/g, '{');
    const params = f.params.join(',');
    lines.push(`!${f.name}(${params}){${body}}`);
    names.push(f.name);
  }
  if (names.length) lines.push(`=ex{${names.join(',')}}`);
  return lines.join('\n');
}

/**
 * Auto-detect input kind and Emit LIA.
 */
export function emitAil(input, opts = {}) {
  const text = String(input || '');
  if (text.includes('@DICE-L:project') || text.includes('~Fn{')) {
    return emitAilFromProject(text, opts);
  }
  return emitAilFromSource(text, opts);
}

export function emitLiaFile(inPath, outPath = null, opts = {}) {
  const abs = path.resolve(inPath);
  const text = fs.readFileSync(abs, 'utf8');
  const lia = emitAil(text, opts);
  const dest = outPath || path.join(path.dirname(abs), 'LIA.dicel');
  fs.writeFileSync(dest, lia, 'utf8');
  return { outPath: dest, chars: lia.length, tokens_est: estTokens(lia), ail: lia, lia };
}

/** @deprecated use emitLiaFile */
export function emitAilFile(inPath, outPath = null, opts = {}) {
  return emitLiaFile(inPath, outPath, opts);
}

function isMain() {
  try {
    const self = path.resolve(fileURLToPath(import.meta.url));
    const argv1 = process.argv[1] ? path.resolve(process.argv[1]) : '';
    return self === argv1;
  } catch {
    return false;
  }
}

if (isMain()) {
  const inPath = process.argv[2];
  if (!inPath) {
    console.error('Usage: node lia_emitter.mjs <source.js|PROJECT.dicel> [out.LIA.dicel]');
    process.exit(2);
  }
  const r = emitLiaFile(inPath, process.argv[3] || null);
  console.log(JSON.stringify({ out: r.outPath, chars: r.chars, tokens_est: r.tokens_est }, null, 2));
}
