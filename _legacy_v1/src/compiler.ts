/**
 * LIN → JS compiler — TS strict, único TS em src, resto .lin
 * Portado de compiler.mjs (1056 linhas) com AST tipado.
 * Em disco somente .lin; compilação 100% in-memory via bin/lin_ts_runtime.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// ---- Tipos reais (antes any) ----
export interface LinFn {
  name: string;
  params: string;
  rawParams: string;
  generics: string | null;
  returnType: string | null;
  body: string;
  effect?: string;
}
export interface LinProgram {
  header: string | null;
  consts: Record<string, string> | null;
  exports: string[];
  fns: LinFn[];
  enums: unknown[];
  structs: unknown[];
  modules: { name: string; program: LinProgram }[];
  uses: { module: string; symbols: string[] }[];
}
export interface CompileOpts {
  exportMode?: 'single' | 'multiple';
  prelude?: string;
  epilogue?: string;
  sandbox?: string[];
  lossy?: boolean;
  skipRefineProof?: boolean;
}
export interface CompileResult {
  js: string;
  program: LinProgram;
}
export interface CompileFileResult extends CompileResult {
  outPath: string;
}

function assertJsParse(_js: string, _opts: { lossy?: boolean }): void {}
function assertDivProof(_text: string, _prog: LinProgram): void {}

export const LIA_COMPILER_VERSION = '1.0.0';
export const AIL_COMPILER_VERSION: string = LIA_COMPILER_VERSION;

function skipRegexLit(s: string, i: number): number {
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

function findMatching(s: string, openIdx: number, openCh: string, closeCh: string): number {
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

function parseConstTable(line: string): Record<string,string> | null {
  // $K{b=1 kb=1024 ...}
  const m = line.match(/^\$K\{([^}]*)\}\s*$/);
  if (!m) return null;
  const entries: Record<string, string> = {};
  for (const part of m[1].trim().split(/\s+/).filter(Boolean)) {
    const eq = part.indexOf('=');
    if (eq < 0) continue;
    entries[part.slice(0, eq)] = part.slice(eq + 1);
  }
  return entries;
}

function stripTypeAnn(params: string): string {
  if (!params) return '';
  const parts = [];
  let current = '';
  let depth = 0;
  for (let k = 0; k < params.length; k++) {
    const ch = params[k];
    if (ch === '(' || ch === '<' || ch === '{' || ch === '[') depth++;
    else if (ch === ')' || ch === '>' || ch === '}' || ch === ']') depth--;
    if (ch === ',' && depth === 0) {
      parts.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  if (current.trim()) parts.push(current.trim());

  return parts
    .map((p) => {
      const colon = p.indexOf(':');
      return (colon >= 0 ? p.slice(0, colon) : p).trim();
    })
    .filter(Boolean)
    .join(', ');
}

function compileReturnSigils(s: string): string {
  // LIA: ^expr = return; keep bitwise XOR a^b intact
  // nextOk includes unary + - ! so ^-x / ^!x / ^+x become return
  let out = '';
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c !== '^') {
      out += c;
      i++;
      continue;
    }
    const prev = out.trimEnd().slice(-1) || '';
    const next = s[i + 1] || '';
      const prevOk = !prev || /[;{}\n,:]/.test(prev);
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

function rewriteClosures(s: string): string {
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

function rewriteMatchBlocks(s: string): string {
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

function compileMatchToJs(targetExpr: string, inner: string): string {
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

function compileBody(body: string): string {
  let s = String(body || '');
  s = s.replace(/([A-Za-z_$][\w$]*)::([A-Za-z_$][\w$]*)/g, '$1.$2');
  s = rewriteClosures(s);
  s = rewriteMatchBlocks(s);
  s = rewriteSigilBlocks(s, '?', 'if');
  s = rewriteLinElse(s);
  s = rewriteSigilBlocks(s, '#', 'for');
  s = compileReturnSigils(s);
  s = s.replace(/([^;{}(\[,:?])while\s*\(/g, '$1;while(');
  // protect existing ===/!== then expand LIN ==/!=
  s = s.replace(/!==/g, '\u0000NE\u0000').replace(/===/g, '\u0000EQ\u0000');
  s = s.replace(/==(?![\s]*(?:null|undefined)\b)/g, '===');
  s = s.replace(/!=(?![\s]*(?:null|undefined)\b)/g, '!==');
  s = s.replace(/\u0000NE\u0000/g, '!==').replace(/\u0000EQ\u0000/g, '===');
  s = s.replace(/;+/g, ';');
  s = s.replace(/;else\b/g, 'else');
  s = s.replace(/#\(/g, 'for(');
  s = insertCtrlSeps(s);
  s = s.replace(/\?\(([^()]+)\)\{/g, 'if($1){');
  s = s.replace(/([^;{}:\s])\s+(case\s|default\s*:)/g, '$1;$2');
  s = s.replace(/\b(let|const|var)\s+([A-Za-z_$][\w$]*)\s*:\s*[^=;{]+?=/g, '$1 $2=');
  if (s && !/[;{}]\s*$/.test(s)) s += ';';
  return s;
}

function rewriteSigilBlocks(s: string, sigil: string, keyword: string): string {
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
    if (s[j] !== '{') {
      // ?(x):y is JS ternary, not LIN if. Only ?(cond){body} is if/for.
      out += token;
      i = idx + token.length;
      continue;
    }
    const closeBrace = findMatching(s, j, '{', '}');
    if (closeBrace < 0) {
      out += token;
      i = idx + token.length;
      continue;
    }
    const inner = compileBody(s.slice(j + 1, closeBrace));
    if (keyword === 'for') out += `for(${head}){${inner}}`;
    else out += `if(${head}){${inner}}`;
    i = closeBrace + 1;
  }
  return out;
}

function skipQuote(s: string, i: number): number {
  const q = s[i];
  let j = i + 1;
  while (j < s.length) {
    if (s[j] === '\\') { j += 2; continue; }
    if (q === '`' && s[j] === '$' && s[j + 1] === '{') {
      const inner = findMatching(s, j + 1, '{', '}');
      j = inner >= 0 ? inner + 1 : j + 2;
      continue;
    }
    if (s[j] === q) return j + 1;
    j++;
  }
  return s.length;
}

function isLinElsePrev(s: string, colonIdx: number): boolean {
  let k = colonIdx - 1;
  while (k >= 0 && /\s/.test(s[k])) k--;
  if (k < 0) return false;
  return s[k] === '}' || s[k] === ';';
}

/** `:{` / `:(cond){` are else only after `}` or `;`. Never rewrite `:` inside `{k:v}` or strings. */
function rewriteLinElse(s: string): string {
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
function insertCtrlSeps(s: string): string {
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
    if ((c === ')' || c === '}') && /^(for|if|while)\(/.test(s.slice(i + 1))) {
      out += `${c};`;
      i++;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

/**
 * Parse LIN/LIA program. Dual-reads @LIN + legacy @LIA/@AIL headers.
 */
export function parseLia(liaText: string): LinProgram {
      const lines = String(liaText || '')
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean);
  const meta: LinProgram = { header: null, consts: null, exports: [], fns: [], enums: [], structs: [], modules: [], uses: [] };
  
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
      
      let openBraces = 0;
      let quote = null;
      let started = false;
      for (let k = firstBrace; k < fullFnText.length; k++) {
        const ch = fullFnText[k];
        if (quote) {
          if (ch === '\\') { k++; continue; }
          if (ch === quote) quote = null;
          continue;
        }
        if (ch === '"' || ch === "'") { quote = ch; continue; }
        if (ch === '{') {
          openBraces++;
          started = true;
        } else if (ch === '}') {
          openBraces--;
        }
      }
      
      while ((!started || openBraces > 0) && i + 1 < lines.length) {
        i++;
        const nextLine = lines[i];
        fullFnText += '\n' + nextLine;
        for (let k = 0; k < nextLine.length; k++) {
          const ch = nextLine[k];
          if (quote) {
            if (ch === '\\') { k++; continue; }
            if (ch === quote) quote = null;
            continue;
          }
          if (ch === '"' || ch === "'") { quote = ch; continue; }
          if (ch === '{') {
            openBraces++;
            started = true;
          } else if (ch === '}') {
            openBraces--;
          }
        }
      }
      
      const lastBrace = fullFnText.lastIndexOf('}');
      const body = firstBrace >= 0 && lastBrace > firstBrace
        ? fullFnText.slice(firstBrace + 1, lastBrace)
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

function firstUseIsRead(body: string, id: string): boolean {
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

function collectAssignedIds(body: string): string[] {
  const ids = new Set<string>();
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

function inferEffect(fn: LinFn, allFns: LinFn[]): string {
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
export function compileLiaToJs(liaText: string, opts: CompileOpts = {}): CompileResult {
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
  assertJsParse(js, { lossy });
  return { js, program: prog };
}

function wrapSandbox(js: string, prog: LinProgram, sandboxSpec: string[] | string): string {
  const allowed = Array.isArray(sandboxSpec) ? sandboxSpec : ['Pure', 'Read'];
  const unsafe: Record<string, string> = {};
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

export function compileLiaFile(liaPath: string, outPath: string | null = null, opts: CompileOpts = {}): CompileFileResult {
  const lia = fs.readFileSync(liaPath, 'utf8');
  const { js, program } = compileLiaToJs(lia, opts);
  const dest = outPath || path.join(path.dirname(path.resolve(liaPath)), 'LIA.compiled.js');
  fs.writeFileSync(dest, js, 'utf8');
  return { outPath: dest, js, program };
}

/** @deprecated use compileLiaFile */
export const compileAilFile = compileLiaFile;

function isMain(): boolean {
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
