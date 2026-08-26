/**
 * LIA → JS compiler (M1/M3) — dual-reads @LIA and legacy @AIL headers.
 * Spec: LIA_SEMANTIC_CORE.dicel + LIA_COMPILER_SPEC.dicel + spec/LIN_EMIT_FAIL_CLOSED.rulel
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertJsParse } from './js_syntax_check.compiled.cjs';
import { skipRegexLit, findMatching, parseConstTable, stripTypeAnn, skipQuote, insertCtrlSeps } from './compiler_core.compiled.cjs';
import { assertDivProof } from './lin_refine_div_load.mjs';

export const LIA_COMPILER_VERSION = '1.0.0';
export const AIL_COMPILER_VERSION = LIA_COMPILER_VERSION; // backcompat





function compileReturnSigils(s) {
  // LIA: ^expr = return; keep bitwise XOR a^b intact
  // nextOk includes unary + - ! so ^-x / ^!x / ^+x become return
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const end = skipQuote(s, i);
      out += s.slice(i, end);
      i = end;
      continue;
    }
    if (c === '/' && i + 1 < s.length && s[i + 1] === '/') {
      const end = s.indexOf('\n', i);
      const nextIdx = end < 0 ? s.length : end + 1;
      out += s.slice(i, nextIdx);
      i = nextIdx;
      continue;
    }
    if (c === '/' && i + 1 < s.length && s[i + 1] === '*') {
      const end = s.indexOf('*/', i + 2);
      const nextIdx = end < 0 ? s.length : end + 2;
      out += s.slice(i, nextIdx);
      i = nextIdx;
      continue;
    }
    if (c === '/' && i + 1 < s.length && s[i + 1] !== '/' && s[i + 1] !== '*') {
      let k = i - 1;
      while (k >= 0 && /\s/.test(s[k])) k--;
      const prev = k < 0 ? '' : s[k];
      if (!prev || /[=(:,;!?{[&|^~+\-*%<>]/.test(prev)) {
        const end = skipRegexLit(s, i);
        out += s.slice(i, end);
        i = end;
        continue;
      }
    }
    if (c !== '^') {
      out += c;
      i++;
      continue;
    }
    // Check backwards from out, stripping only horizontal whitespace
    let k = out.length - 1;
    while (k >= 0 && (out[k] === ' ' || out[k] === '\t' || out[k] === '\r')) k--;
    let prevOk = false;
    if (k < 0) {
      prevOk = true;
    } else {
      const prevCh = out[k];
      if (prevCh === '\n' || prevCh === ';' || prevCh === '{' || prevCh === '}' || prevCh === ',' || prevCh === ':') {
        prevOk = true;
      } else if (out.slice(0, k + 1).endsWith('*/')) {
        const commentStart = out.lastIndexOf('/*', k);
        if (commentStart >= 0) {
          let beforeComment = commentStart - 1;
          while (beforeComment >= 0 && /\s/.test(out[beforeComment])) beforeComment--;
          if (beforeComment < 0 || /[;{}\n,:]/.test(out[beforeComment])) {
            prevOk = true;
          }
        }
      }
    }
    const next = s[i + 1] || '';
    const nextOk = /[A-Za-z_$0-9(\[\-+!'"`{]/.test(next);
    if (prevOk && nextOk) {
      out += 'return ';
      i++;
      continue;
    }
    out += '^';
    i++;
  }
  return out;
}

function rewriteClosures(s) {
  // LIN closure syntax: ~(params){body} -> function(params){body}
  let out = '';
  let i = 0;
  while (i < s.length) {
    const idx = s.indexOf('~(', i);
    if (idx < 0) {
      out += s.slice(i);
      break;
    }
    // skip ~G grammar marker
    if (s[idx + 1] === 'G') {
      out += s.slice(i, idx + 2);
      i = idx + 2;
      continue;
    }
    // ~~(x) is JS double-bitwise-not, not a LIN closure
    if (idx > 0 && s[idx - 1] === '~') {
      out += s.slice(i, idx + 1);
      i = idx + 1;
      continue;
    }
    out += s.slice(i, idx);
    const openParen = idx + 1;
    const closeParen = findMatching(s, openParen, '(', ')');
    if (closeParen < 0) {
      out += '~(';
      i = idx + 2;
      continue;
    }
    const params = s.slice(openParen + 1, closeParen);
    let j = closeParen + 1;
    while (j < s.length && /\s/.test(s[j])) j++;
    if (s[j] !== '{') {
      out += `function(${stripTypeAnn(params)})`;
      i = closeParen + 1;
      continue;
    }
    let closeBrace = findMatching(s, j, '{', '}');
    if (closeBrace < 0) closeBrace = s.lastIndexOf('}');
    if (closeBrace < j) {
      out += `function(${stripTypeAnn(params)}){return void 0;}`;
      i = j + 1;
      continue;
    }
    const inner = compileBody(s.slice(j + 1, closeBrace));
    out += `function(${stripTypeAnn(params)}){${inner}}`;
    i = closeBrace + 1;
  }
  return out;
}

function rewriteMatchBlocks(s) {
  let out = '';
  let i = 0;
  while (i < s.length) {
    const idx = s.indexOf('match(', i);
    if (idx < 0) {
      out += s.slice(i);
      break;
    }
    out += s.slice(i, idx);
    const openParen = idx + 5;
    const closeParen = findMatching(s, openParen, '(', ')');
    if (closeParen < 0) {
      out += 'match(';
      i = idx + 6;
      continue;
    }
    const targetExpr = s.slice(openParen + 1, closeParen).trim();
    let j = closeParen + 1;
    while (j < s.length && /\s/.test(s[j])) j++;
    if (s[j] !== '{') {
      out += `match(${targetExpr})`;
      i = closeParen + 1;
      continue;
    }
    const closeBrace = findMatching(s, j, '{', '}');
    if (closeBrace < 0) {
      out += `match(${targetExpr}){`;
      i = j + 1;
      continue;
    }
    const inner = s.slice(j + 1, closeBrace);
    out += compileMatchToJs(targetExpr, inner);
    i = closeBrace + 1;
  }
  return out;
}

function compileMatchToJs(targetExpr, inner) {
  const parts = [];
  let i = 0;
  let first = true;
  while (i < inner.length) {
    while (i < inner.length && /[\s;]/.test(inner[i])) i++;
    if (i >= inner.length) break;
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
    while (bodyStart < inner.length && /\s/.test(inner[bodyStart])) bodyStart++;
    let bodyStr = '';
    let nextI = bodyStart;
    if (inner[bodyStart] === '{') {
      const closeB = findMatching(inner, bodyStart, '{', '}');
      if (closeB >= 0) {
        bodyStr = compileBody(inner.slice(bodyStart + 1, closeB));
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
      const raw = inner.slice(bodyStart, k).trim();
      if (raw) {
        bodyStr = compileBody(raw);
      }
      nextI = k < inner.length ? k + 1 : k;
    }

    let cond = '';
    let binds = '';
    if (pat === '_') {
      cond = guard ? `(${guard})` : 'true';
    } else if (pat.includes('|')) {
      const subPats = pat.split('|').map((p) => p.trim()).filter(Boolean);
      const subConds = subPats.map((p) => {
        if (p === 'true' || p === 'false') return `${targetExpr}===${p}`;
        if (/^-?\d+(\.\d+)?$/.test(p)) return `${targetExpr}===${p}`;
        if (/^["']/.test(p)) return `${targetExpr}===${p}`;
        return `${targetExpr}===${p}`;
      });
      cond = `(${subConds.join('||')})`;
      if (guard) cond += `&&(${guard})`;
    } else {
      const enumMatch = pat.match(/^([A-Za-z_$][\w$]*)\(([^)]+)\)$/);
      // Tuple destructuring: (a, b)
      const tupleMatch = pat.match(/^\(([^)]+)\)$/);
      // Struct destructuring: Point { x, y } or { x, y }
      const structDestruct = pat.match(/^(?:([A-Za-z_$][\w$]*)\s*)?\{([^}]+)\}$/);
      
      if (enumMatch) {
        const tag = enumMatch[1];
        const v = enumMatch[2].trim();
        let tagCheck = '';
        if (tag === 'Some') {
          tagCheck = `(${targetExpr}!=null && (typeof ${targetExpr}==='object'?('Some' in ${targetExpr}||${targetExpr}.tag==='Some'):true))`;
          binds = `let ${v}=typeof ${targetExpr}==='object'&&${targetExpr}!==null?(${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.Some):${targetExpr};`;
        } else if (tag === 'Ok' || tag === 'Err') {
          tagCheck = `(${targetExpr}!=null && typeof ${targetExpr}==='object' && (${targetExpr}.tag==='${tag}'||'${tag}' in ${targetExpr}))`;
          binds = `let ${v}=${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.${tag};`;
        } else {
          tagCheck = `(${targetExpr}!=null && typeof ${targetExpr}==='object' && (${targetExpr}.tag==='${tag}'||'${tag}' in ${targetExpr}))`;
          binds = `let ${v}=${targetExpr}.value!==undefined?${targetExpr}.value:${targetExpr}.${tag};`;
        }
        cond = tagCheck;
        if (guard) cond += `&&(${guard})`;
      } else if (tupleMatch) {
        const elements = tupleMatch[1].split(',').map((x) => x.trim());
        cond = `(Array.isArray(${targetExpr}) && ${targetExpr}.length >= ${elements.length})`;
        binds = elements.map((elem, idx) => `let ${elem}=${targetExpr}[${idx}];`).join('');
        if (guard) cond += `&&(${guard})`;
      } else if (structDestruct) {
        const structName = structDestruct[1];
        const fields = structDestruct[2].split(',').map((x) => x.trim()).filter(Boolean);
        cond = `(${targetExpr}!=null && typeof ${targetExpr}==='object'${structName ? ` && (${targetExpr} instanceof ${structName} || ${targetExpr}.__struct==='${structName}' || true)` : ''})`;
        binds = fields.map((f) => {
          const colon = f.indexOf(':');
          const prop = colon >= 0 ? f.slice(0, colon).trim() : f;
          const binding = colon >= 0 ? f.slice(colon + 1).trim() : f;
          return `let ${binding}=${targetExpr}.${prop};`;
        }).join('');
        if (guard) cond += `&&(${guard})`;
      } else if (/^[A-Za-z_$][\w$]*$/.test(pat) && pat === 'None') {
        cond = `(${targetExpr}==null||${targetExpr}===undefined||(typeof ${targetExpr}==='object'&&(${targetExpr}.tag==='None'||'None' in ${targetExpr})))`;
        if (guard) cond += `&&(${guard})`;
      } else {
        cond = `(${targetExpr}===${pat})`;
        if (guard) cond += `&&(${guard})`;
      }
    }

    if (first) {
      parts.push(`if(${cond}){${binds}${bodyStr}}`);
      first = false;
    } else {
      parts.push(`else if(${cond}){${binds}${bodyStr}}`);
    }
    i = nextI;
  }
  return parts.join('');
}

function maskLiterals(s) {
  const table = [];
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const end = skipQuote(s, i);
      const placeholder = `\u0000LIT_${table.length}\u0000`;
      table.push(s.slice(i, end));
      out += placeholder;
      i = end;
      continue;
    }
    if (c === '/' && i + 1 < s.length && s[i + 1] !== '/' && s[i + 1] !== '*') {
      let k = i - 1;
      while (k >= 0 && /\s/.test(s[k])) k--;
      const prev = k < 0 ? '' : s[k];
      if (!prev || /[=(:,;!?{[&|^~+\-*%<>]/.test(prev)) {
        const end = skipRegexLit(s, i);
        const placeholder = `\u0000LIT_${table.length}\u0000`;
        table.push(s.slice(i, end));
        out += placeholder;
        i = end;
        continue;
      }
    }
    out += c;
    i++;
  }
  return {
    masked: out,
    unmask: (str) => {
      let res = str;
      for (let idx = 0; idx < table.length; idx++) {
        res = res.replaceAll(`\u0000LIT_${idx}\u0000`, () => table[idx]);
      }
      return res;
    }
  };
}

function compileBody(body) {
  let s = String(body || '');
  s = s.replace(/([A-Za-z_$][\w$]*)::([A-Za-z_$][\w$]*)/g, '$1.$2');
  s = rewriteClosures(s);
  s = rewriteMatchBlocks(s);
  // Block ternary `?(c){a}:b` is resolved inside rewriteSigilBlocks; classic
  // else chains `:(c){}` / `:{}` remain the job of rewriteLinElse below.
  s = rewriteSigilBlocks(s, '?', 'if');
  s = rewriteLinElse(s);
  s = rewriteSigilBlocks(s, '#', 'for');
  s = compileReturnSigils(s);
  s = s.replace(/([^;{}(\[,:?])while\s*\(/g, '$1;while(');
  
  // Protect string and regex literals before operator normalization
  const { masked, unmask } = maskLiterals(s);
  let m = masked;
  m = m.replace(/!==/g, '\u0000NE\u0000').replace(/===/g, '\u0000EQ\u0000');
  m = m.replace(/==(?![s]*(?:null|undefined)\b)/g, '===');
  m = m.replace(/!=(?![s]*(?:null|undefined)\b)/g, '!==');
  m = m.replace(/\u0000NE\u0000/g, '!==').replace(/\u0000EQ\u0000/g, '===');
  m = m.replace(/;+/g, ';');
  m = m.replace(/;else\b/g, 'else');
  m = m.replace(/#\(/g, 'for(');
  m = insertCtrlSeps(m);
  m = m.replace(/\?\(([^()]+)\)\{/g, 'if($1){');
  m = m.replace(/([^;{}:\s])\s+(case\s|default\s*:)/g, '$1;$2');
  m = m.replace(/\b(let|const|var)\s+([A-Za-z_$][\w$]*)\s*:\s*[^=;{]+?=/g, '$1 $2=');
  if (m && !/[;{}]\s*$/.test(m)) m += ';';
  return unmask(m);
}

function rewriteSigilBlocks(s, sigil, keyword) {
  let out = '';
  let i = 0;
  const token = sigil + '(';
  while (i < s.length) {
    const idx = s.indexOf(token, i);
    if (idx < 0) {
      out += s.slice(i);
      break;
    }
    out += s.slice(i, idx);
    const openParen = idx + 1;
    const closeParen = findMatching(s, openParen, '(', ')');
    if (closeParen < 0) {
      out += token;
      i = idx + token.length;
      continue;
    }
    const head = s.slice(openParen + 1, closeParen);
    let j = closeParen + 1;
    while (j < s.length && /\s/.test(s[j])) j++;
    if (s[j] === '{') {
      const closeBrace = findMatching(s, j, '{', '}');
      if (closeBrace < 0) {
        out += token;
        i = idx + token.length;
        continue;
      }
      const inner = compileBody(s.slice(j + 1, closeBrace));
      let k = closeBrace + 1;
      while (k < s.length && /\s/.test(s[k])) k++;
      // Ternary tail only when ':' is NOT a LIN else-block form
      // (`:(cond){`, `:{`, `:else`) — those belong to rewriteLinElse.
      if (s[k] === ':' && !/^[:\s]*(\(|\{|else\b)/.test(s.slice(k + 1))) {
        let m = k + 1;
        while (m < s.length && /\s/.test(s[m])) m++;
        const elsePart = s.slice(m);
        if (elsePart) {
          out += `(${head}?${inner}:${compileBody(elsePart)})`;
          i = s.length;
          continue;
        }
      }
      if (keyword === 'for') {
        out += `for(${head}){${inner}}`;
      } else {
        out += `if(${head}){${inner}}`;
      }
      i = closeBrace + 1;
      continue;
    }
    out += token;
    i = idx + token.length;
  }
  return out;
}


function isLinElsePrev(s, colonIdx) {
  let k = colonIdx - 1;
  while (k >= 0 && /\s/.test(s[k])) k--;
  if (k < 0) return false;
  return s[k] === '}' || s[k] === ';';
}

/** `:{` / `:(cond){` are else only after `}` or `;`. Never rewrite `:` inside `{k:v}` or strings. */
function rewriteLinElse(s) {
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === '`') {
      const end = skipQuote(s, i);
      out += s.slice(i, end);
      i = end;
      continue;
    }
    if (c === '/' && i + 1 < s.length && s[i + 1] !== '/' && s[i + 1] !== '*') {
      let k = i - 1;
      while (k >= 0 && /\s/.test(s[k])) k--;
      const prev = k < 0 ? '' : s[k];
      if (!prev || /[=(:,;!?{[&|^~+\-*%<>]/.test(prev)) {
        const end = skipRegexLit(s, i);
        out += s.slice(i, end);
        i = end;
        continue;
      }
    }
    if (c === ':' && isLinElsePrev(s, i)) {
      let j = i + 1;
      while (j < s.length && /\s/.test(s[j])) j++;
      if (s[j] === '{') {
        const closeBrace = findMatching(s, j, '{', '}');
        if (closeBrace >= 0) {
          out += `else{${compileBody(s.slice(j + 1, closeBrace))}}`;
          i = closeBrace + 1;
          continue;
        }
      }
      if (s[j] === '?') {
        j++;
        while (j < s.length && /\s/.test(s[j])) j++;
      } else if (s.slice(j, j + 2) === 'if') {
        j += 2;
        while (j < s.length && /\s/.test(s[j])) j++;
      }
      if (s[j] === '(') {
        const closeParen = findMatching(s, j, '(', ')');
        if (closeParen >= 0) {
          let k = closeParen + 1;
          while (k < s.length && /\s/.test(s[k])) k++;
          if (s[k] === '{') {
            const closeBrace = findMatching(s, k, '{', '}');
            if (closeBrace >= 0) {
              const head = s.slice(j + 1, closeParen);
              out += `else if(${head}){${compileBody(s.slice(k + 1, closeBrace))}}`;
              i = closeBrace + 1;
              continue;
            }
          }
        }
      }
    }
    out += c;
    i++;
  }
  return out;
}

/** Keep `return ({k:v})for(...)` from gluing into one illegal statement. */

/**
 * Parse LIN/LIA program. Dual-reads @LIN + legacy @LIA/@AIL headers.
 */
export function parseLia(liaText) {
      const lines = String(liaText || '')
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean);
  const meta = { header: null, consts: null, exports: [], fns: [], enums: [], structs: [], modules: [], uses: [] };
  
  // Primeiro passo: coletar declarações de enum, struct, mod e use (podem spançar múltiplas linhas)
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    
    if (line.startsWith('@LIN:') || line.startsWith('@LIA:') || line.startsWith('@AIL:')) {
      meta.header = line;
      i++;
      continue;
    }
    else if (line.startsWith('^')) { i++; continue; }
    else if (line.startsWith('~G')) { i++; continue; }
    else if (line.startsWith('$K')) {
      const next = parseConstTable(line);
      if (next) meta.consts = Object.assign(meta.consts || {}, next);
      i++;
      continue;
    }
    else if (/^\s*=\s*ex\s*\{/.test(line)) {
      let rawExLine = line;
      if (!rawExLine.includes('}')) {
        while (i + 1 < lines.length) {
          i++;
          rawExLine += '\n' + lines[i];
          if (lines[i].includes('}')) break;
        }
      }
      const exBody = rawExLine
        .replace(/^\s*=\s*ex\s*\{/, '')
        .replace(/\}\s*$/, '')
        .replace(/\/\*[\s\S]*?\*\/|\/\/[^\r\n]*/g, '');
      meta.exports = (meta.exports || []).concat(
        exBody
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean)
      );
      i++;
      continue;
    }
    else if (line.startsWith('use ')) {
      // use Module::{sym1, sym2} or use Module::sym1
      const useMatch = line.match(/^use\s+([A-Za-z_$][\w$]*)::(?:\{([^}]+)\}|([A-Za-z_$][\w$]*))\s*;?$/);
      if (useMatch) {
        const modName = useMatch[1];
        const symbols = useMatch[2]
          ? useMatch[2].split(',').map((s) => s.trim()).filter(Boolean)
          : [useMatch[3].trim()];
        meta.uses.push({ module: modName, symbols });
      }
      i++;
      continue;
    }
    else if (line.startsWith('mod ')) {
      // Parse module block: mod Math { ... }
      const modMatch = line.match(/^mod\s+([A-Za-z_$][\w$]*)\s*\{?([\s\S]*)$/);
      if (modMatch) {
        const modName = modMatch[1];
        let body = modMatch[2] || '';
        let openBraces = 0;
        const firstBrace = line.indexOf('{');
        if (firstBrace >= 0) {
          for (let k = firstBrace; k < line.length; k++) {
            if (line[k] === '{') openBraces++;
            else if (line[k] === '}') openBraces--;
          }
        } else {
          openBraces = 1;
        }

        while (openBraces > 0 && i + 1 < lines.length) {
          i++;
          const nextLine = lines[i];
          body += '\n' + nextLine;
          for (const ch of nextLine) {
            if (ch === '{') openBraces++;
            else if (ch === '}') openBraces--;
          }
        }

        const lastBrace = body.lastIndexOf('}');
        const innerCode = lastBrace >= 0 ? body.slice(0, lastBrace) : body;
        
        // Recursively parse inner program of the module
        const modProg = parseLia(innerCode);
        meta.modules.push({ name: modName, program: modProg });
      }
      i++;
      continue;
    }
    else if (line.startsWith('struct ')) {
      // Parse struct declaration: struct Point { x: int, y: int }
      const structMatch = line.match(/^struct\s+([A-Za-z_$][\w$]*)(<[^>]*>)?\s*\{?([\s\S]*)$/);
      if (structMatch) {
        const structName = structMatch[1];
        const generics = structMatch[2] || null;
        let body = structMatch[3] || '';
        
        if (!body.includes('}')) {
          while (i + 1 < lines.length) {
            i++;
            const nextLine = lines[i];
            body += '\n' + nextLine;
            if (nextLine.includes('}')) break;
          }
        }
        
        const fields = [];
        const innerBody = body.replace(/^\{/, '').replace(/\}$/, '');
        const fieldLines = innerBody.split(/[\n,]/);
        for (const fLine of fieldLines) {
          const trimmed = fLine.trim();
          if (!trimmed) continue;
          const fMatch = trimmed.match(/^([A-Za-z_$][\w$]*)\s*:\s*([^,;]+)$/);
          if (fMatch) {
            fields.push({ name: fMatch[1], type: fMatch[2].trim() });
          }
        }
        
        meta.structs.push({ name: structName, generics, fields });
      }
      i++;
      continue;
    }
    else if (line.startsWith('enum ')) {
      // Parse enum declaration - pode spançar múltiplas linhas
      const enumMatch = line.match(/^enum\s+([A-Za-z_$][\w$]*)(<[^>]*>)?\s*\{?([\s\S]*)$/);
      if (enumMatch) {
        const enumName = enumMatch[1];
        const generics = enumMatch[2] || null;
        let body = enumMatch[3] || '';
        
        // Se não tem fechamento, continuar coletando linhas
        if (!body.includes('}')) {
          while (i + 1 < lines.length) {
            i++;
            const nextLine = lines[i];
            body += '\n' + nextLine;
            if (nextLine.includes('}')) break;
          }
        }
        
        // Extrair variantes do enum - cada linha dentro das chaves
        const variants = [];
        const innerBody = body.replace(/^\{/, '').replace(/\}$/, '');
        const variantLines = innerBody.split('\n');
        for (const vLine of variantLines) {
          const trimmed = vLine.trim().replace(/,$/, ''); // remove trailing comma
          if (!trimmed) continue;
          // Variante pode ser: Some(T), Some, None, etc.
          const vMatch = trimmed.match(/^([A-Za-z_$][\w$]*)(\([^)]*\))?$/);
          if (vMatch) {
            variants.push({ name: vMatch[1], params: vMatch[2]?.slice(1, -1) || null });
          }
        }
        
        meta.enums.push({ name: enumName, generics, variants });
      }
      i++;
      continue;
    }
    else if (line.startsWith('fn ') || line.startsWith('!')) {
      let openParenIdx = line.indexOf('(');
      let closeParenIdx = -1;
      let pDepth = 0;
      for (let k = openParenIdx; k < line.length; k++) {
        if (line[k] === '(') pDepth++;
        else if (line[k] === ')') {
          pDepth--;
          if (pDepth === 0) {
            closeParenIdx = k;
            break;
          }
        }
      }
      
      let fnHeader = line;
      let paramsRaw = '';
      let fnName = '';
      let generics = null;
      let returnType = null;
      
      if (openParenIdx >= 0 && closeParenIdx > openParenIdx) {
        const pre = line.slice(0, openParenIdx).trim();
        const nmMatch = pre.match(/^(?:fn|!)\s*([A-Za-z_$][\w$]*)(<[^>]*>)?$/);
        if (nmMatch) {
          fnName = nmMatch[1];
          generics = nmMatch[2] || null;
        }
        paramsRaw = line.slice(openParenIdx + 1, closeParenIdx);
        const post = line.slice(closeParenIdx + 1);
        const retMatch = post.match(/^\s*(?:->|:)\s*([^{]+)/);
        if (retMatch) {
          returnType = retMatch[1].trim();
        }
      } else {
        const fnStart = line.match(/^(?:fn|!)\s*([A-Za-z_$][\w$]*)(<[^>]*>)?\(([^)]*)\)(?:\s*(?:->|:)\s*([^{]+))?\s*\{?([\s\S]*)$/);
        if (!fnStart) throw new Error(`LIA_PARSE_FN_START: ${line.slice(0, 80)}`);
        fnName = fnStart[1];
        generics = fnStart[2] || null;
        paramsRaw = fnStart[3];
        returnType = fnStart[4]?.trim();
      }
      
      // Body '{' is after the param list, not a refinement like b:int{>0}
      let fullFnText = line;
      const braceFrom = closeParenIdx >= 0 ? closeParenIdx + 1 : 0;
      let firstBrace = fullFnText.indexOf('{', braceFrom);
      if (firstBrace < 0) {
        while (i + 1 < lines.length) {
          i++;
          fullFnText += '\n' + lines[i];
          firstBrace = fullFnText.indexOf('{', braceFrom);
          if (firstBrace >= 0) break;
        }
      }
      
      let closeBrace = findMatching(fullFnText, firstBrace, '{', '}');
      while (closeBrace < 0 && i + 1 < lines.length) {
        i++;
        fullFnText += '\n' + lines[i];
        closeBrace = findMatching(fullFnText, firstBrace, '{', '}');
      }
      
      const body = firstBrace >= 0 && closeBrace > firstBrace
        ? fullFnText.slice(firstBrace + 1, closeBrace)
        : '';
      
      meta.fns.push({ name: fnName, generics, params: stripTypeAnn(paramsRaw), rawParams: paramsRaw, returnType, body });
      i++;
      continue;
    }
    
    i++;
  }
  
  return meta;
}

/** @deprecated use parseLia */
export const parseAil = parseLia;

function firstUseIsRead(body, id) {
  const s = String(body || '');
  const re = new RegExp(`\\b${id}\\b`, 'g');
  let m;
  while ((m = re.exec(s))) {
    let j = m.index + id.length;
    while (j < s.length && /\s/.test(s[j])) j++;
    if (s[j] === '=' && s[j + 1] !== '=') return false;
    const before = s.slice(Math.max(0, m.index - 48), m.index);
    const after = s.slice(m.index + id.length, m.index + id.length + 48);
    if (/\{[^{}]*$/.test(before) && /\}\s*=/.test(after)) return false;
    return true;
  }
  return false;
}

function collectAssignedIds(body) {
  const ids = new Set();
  const re = /(?:^|[;{,])\s*([A-Za-z_$][\w$]*)\s*=/g;
  let m;
  const s = `;${body}`;
  while ((m = re.exec(s)) !== null) {
    const id = m[1];
    if (!['return', 'if', 'for', 'else', 'function', 'var', 'let', 'const'].includes(id)) ids.add(id);
  }
  // for-loop init i=0
  const forInit = /for\(([^;]*);/g;
  while ((m = forInit.exec(body)) !== null) {
    const im = m[1].match(/^([A-Za-z_$][\w$]*)\s*=/);
    if (im) ids.add(im[1]);
  }
  return [...ids];
}

const NATIVE_BUILTINS = /\b(String|Number|Math|Buffer|Array|Object|Error|JSON|console|process|require|globalThis|window|document|fetch|setTimeout|setInterval|crypto)\b/;

function inferEffect(fn, allFns) {
  const body = String(fn.body || '');
  const params = new Set((fn.params || '').split(',').map((p) => p.replace(/:[\w\[\]|,]+$/g, '').trim()).filter(Boolean));
  const locals = new Set(collectAssignedIds(body));
  for (const p of params) locals.add(p);
  const effects = new Set();

  if (/\bthrow\b/.test(body)) effects.add('Throw');
  if (NATIVE_BUILTINS.test(body)) effects.add('Native');

  // assignments to identifiers that are also referenced in other fns -> likely global Write
  const allOtherRefs = (allFns || [])
    .filter((g) => g.name !== fn.name)
    .map((g) => String(g.body || ''))
    .join('\n');
  const assignRe = /(?:^|[;{},])\s*([A-Za-z_$][\w$]*)\s*=(?!=)/g;
  let am;
  while ((am = assignRe.exec(body)) !== null) {
    const id = am[1];
    if (['return', 'if', 'for', 'else', 'function', 'var', 'let', 'const'].includes(id)) continue;
    if (!locals.has(id)) {
      effects.add('Write');
    } else if (new RegExp(`\\b${id}\\b`).test(allOtherRefs)) {
      effects.add('Write');
    }
  }

  // references to non-local / non-param identifiers -> Read (if not a builtin)
  const idRe = /\b([A-Za-z_$][\w$]*)\b/g;
  const builtinSet = new Set(['String', 'Number', 'Math', 'Buffer', 'Array', 'Object', 'Error', 'JSON', 'console', 'process', 'require', 'globalThis', 'window', 'document', 'fetch', 'setTimeout', 'setInterval', 'crypto', 'true', 'false', 'null', 'undefined']);
  let rm;
  while ((rm = idRe.exec(body)) !== null) {
    const id = rm[1];
    if (!params.has(id) && !locals.has(id) && !builtinSet.has(id)) {
      effects.add('Read');
    }
  }

  // calls to other fns in the program: propagate their effects (simple join)
  for (const other of allFns || []) {
    if (other.name === fn.name) continue;
    const callRe = new RegExp(`\\b${other.name}\\s*\\(`);
    if (callRe.test(body) && other.effect) {
      for (const e of other.effect.split(/\|/)) effects.add(e);
    }
  }

  if (effects.has('Write')) return 'Write';
  if (effects.has('Throw')) return 'Throw';
  if (effects.has('Native')) return 'Native';
  if (effects.has('Read')) return 'Read';
  return 'Pure';
}

/**
 * Compile LIA text → JS module source.
 */
export function compileLiaToJs(liaText, opts = {}) {
  const prog = parseLia(liaText);
  if (opts.skipRefineProof !== true) {
    assertDivProof(liaText, prog);
  }
  const fnNames = new Set(prog.fns.map((f) => f.name));
  for (const name of prog.exports) {
    const raw = name.includes(' as ') ? name.split(/\s+as\s+/)[0].trim() : name;
    if (!fnNames.has(raw)) throw new Error(`LIN_EXPORT_NO_FN: ${name}`);
  }
  const parts = [];
  parts.push(`/* generated by lia_compiler ${LIA_COMPILER_VERSION} */`);
  if (opts.prelude) parts.push(String(opts.prelude).trim());
  if (prog.consts) {
    const obj = Object.entries(prog.consts)
      .map(([k, v]) => `${JSON.stringify(k)}:${v}`)
      .join(',');
    parts.push(`var $K={${obj}};`);
  }

  // Emit nested modules as namespace objects
  for (const mod of prog.modules || []) {
    const modFns = [];
    for (const fn of mod.program.fns || []) {
      const body = compileBody(fn.body);
      modFns.push(`${fn.name}: function(${fn.params}){${body}}`);
    }
    parts.push(`const ${mod.name} = {\n  ${modFns.join(',\n  ')}\n};`);
  }

  // Handle use declarations
  for (const u of prog.uses || []) {
    for (const sym of u.symbols) {
      parts.push(`const ${sym} = ${u.module}.${sym};`);
    }
  }

  for (const fn of prog.fns) {
    fn.effect = inferEffect(fn, prog.fns);
    const body = compileBody(fn.body);
    const locals = collectAssignedIds(body).filter((id) => {
      const params = new Set(fn.params.split(',').map((p) => p.trim()).filter(Boolean));
      if (params.has(id)) return false;
      if (firstUseIsRead(body, id)) return false;
      return true;
    });
    const decl = locals.length ? `var ${locals.join(',')};` : '';
    parts.push(`/* effect:${fn.effect} */function ${fn.name}(${fn.params}){${decl}${body}}`);
  }
  if (opts.epilogue) {
    parts.push(String(opts.epilogue).trim());
  } else {
    const rawEx = prog.exports.length ? prog.exports : prog.fns.map((f) => f.name);
    const ex = rawEx.map((e) => {
      if (e.includes(' as ')) {
        const [src, alias] = e.split(/\s+as\s+/).map((s) => s.trim());
        return `${alias}:${src}`;
      }
      return e;
    });
    if (opts.exportMode === 'single' && ex[0]) {
      parts.push(`module.exports=${ex[0]};`);
    } else if (ex.length === 1 && !rawEx[0].includes(' as ')) {
      parts.push(`module.exports=${ex[0]};`);
    } else {
      parts.push(`module.exports={${ex.join(',')}};`);
    }
  }

  let js = parts.join('\n');
  if (opts.sandbox) {
    js = wrapSandbox(js, prog, opts.sandbox);
  }
  const lossy = opts.lossy === true || /\blossy\s*=\s*true\b/.test(String(liaText || ''));
  if (opts.debugPrint) console.log("--- DEBUG COMPILED JS ---\n" + js);
  assertJsParse(js, { lossy });
  return { js, program: prog };
}

function wrapSandbox(js, prog, sandboxSpec) {
  const allowed = Array.isArray(sandboxSpec) ? sandboxSpec : ['Pure', 'Read'];
  const unsafe = {};
  for (const fn of prog.fns) {
    const fx = fn.effect || 'Pure';
    if (!allowed.includes(fx)) unsafe[fn.name] = fx;
  }
  const unsafeNames = Object.keys(unsafe);
  if (!unsafeNames.length) return js;
  const guard = `
/* sandbox guard */
(function(){
  const _orig = module.exports;
  const _allowed = ${JSON.stringify(allowed)};
  const _unsafe = ${JSON.stringify(unsafe)};
  const _wrap = typeof _orig === 'function'
    ? function(){ throw new Error('LIN_SANDBOX: exported function is ' + Object.values(_unsafe)[0] + ', allowed=' + _allowed.join('|')); }
    : {};
  if (typeof _orig === 'object' && _orig) {
    for (const k of Object.keys(_orig)) {
      if (_unsafe[k]) {
        _wrap[k] = function(){ throw new Error('LIN_SANDBOX: ' + k + ' has effect ' + _unsafe[k] + ', allowed=' + _allowed.join('|')); };
      } else {
        _wrap[k] = _orig[k];
      }
    }
  }
  module.exports = _wrap;
})();
`;
  return js + guard;
}

/** @deprecated use compileLiaToJs */
export const compileAilToJs = compileLiaToJs;

export function compileLiaFile(liaPath, outPath = null, opts = {}) {
  const lia = fs.readFileSync(liaPath, 'utf8');
  const { js, program } = compileLiaToJs(lia, opts);
  const dest = outPath || path.join(path.dirname(path.resolve(liaPath)), 'LIA.compiled.js');
  fs.writeFileSync(dest, js, 'utf8');
  return { outPath: dest, js, program };
}

/** @deprecated use compileLiaFile */
export const compileAilFile = compileLiaFile;

function isMain() {
  try {
    return path.resolve(fileURLToPath(import.meta.url)) === path.resolve(process.argv[1] || '');
  } catch {
    return false;
  }
}

if (isMain()) {
  const inPath = process.argv[2];
  if (!inPath) {
    console.error('Usage: node lia_compiler.mjs <file.lia|file.ail|LIA.dicel> [out.js]');
    process.exit(2);
  }
  const r = compileLiaFile(inPath, process.argv[3] || null);
  console.log(JSON.stringify({ out: r.outPath, fns: r.program.fns.map((f) => f.name) }, null, 2));
}
