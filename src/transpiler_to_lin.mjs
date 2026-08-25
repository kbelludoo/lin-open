// LIN Universal Polyglot Transpiler (Dogfooding transpiler_to_lin_core.lin)
// Spec: spec/LIN_IR_CROSS_BACKEND.rulel & spec/LIN_CORE_ARCH.rulel

import { createRequire } from 'node:module';
import { emitLinFromJs } from './emit_from_js.mjs';

const require = createRequire(import.meta.url);
const {
  detectLanguage: linDetectLanguage,
  transpileRustToLin: linTranspileRustToLin,
  transpileGoToLin: linTranspileGoToLin,
  transpileCToLin: linTranspileCToLin,
  transpileZigToLin: linTranspileZigToLin,
} = require('./transpiler_to_lin_core.compiled.cjs');

export const detectLanguage = linDetectLanguage;
export const transpileRustToLin = linTranspileRustToLin;
export const transpileGoToLin = linTranspileGoToLin;
export const transpileCToLin = linTranspileCToLin;
export const transpileZigToLin = linTranspileZigToLin;

export function transpileToLin(sourceCode, opts = {}) {
  const lang = String(opts.lang || detectLanguage(sourceCode, opts.filename || '')).toLowerCase();

  switch (lang) {
    case 'js':
    case 'javascript':
    case 'ts':
    case 'typescript':
      return transpileJsTsToLin(sourceCode, opts);

    case 'py':
    case 'python':
      return transpilePythonToLin(sourceCode, opts);

    case 'rs':
    case 'rust':
      return transpileRustToLin(sourceCode);

    case 'go':
    case 'golang':
      return transpileGoToLin(sourceCode);

    case 'c':
    case 'cpp':
      return transpileCToLin(sourceCode);

    case 'zig':
      return transpileZigToLin(sourceCode);

    default:
      return transpileJsTsToLin(sourceCode, opts);
  }
}

function transpilePythonToLin(pySource, opts = {}) {
  const lines = pySource.split('\n');
  const fns = [];
  let currentFn = null;
  let fnBodyLines = [];

  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const defMatch = line.match(/^def\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)\s*:/);
    if (defMatch) {
      if (currentFn) {
        fns.push({ name: currentFn.name, params: currentFn.params, body: processPythonBody(fnBodyLines) });
      }
      currentFn = { name: defMatch[1], params: defMatch[2].split(',').map(p => p.trim()).filter(Boolean).join(',') };
      fnBodyLines = [];
      continue;
    }

    if (currentFn) {
      fnBodyLines.push(line);
    }
  }

  if (currentFn) {
    fns.push({ name: currentFn.name, params: currentFn.params, body: processPythonBody(fnBodyLines) });
  }

  const exportNames = fns.map(f => f.name);
  const outLines = ['@LIN:L1c:0.2'];

  for (const fn of fns) {
    outLines.push(`!${fn.name}(${fn.params}){`);
    outLines.push(fn.body);
    outLines.push('}');
  }

  outLines.push(`=ex{${exportNames.join(', ')}}`);
  return outLines.join('\n');
}

function processPythonBody(lines) {
  const out = [];
  const indentStack = [0];

  for (let l of lines) {
    if (!l.trim() || l.trim().startsWith('#')) continue;
    const indent = l.match(/^\s*/)[0].length;
    const isElseOrElif = /^(elif\b|else\s*:)/.test(l.trim());

    if (!isElseOrElif) {
      while (indentStack.length > 1 && indent < indentStack[indentStack.length - 1]) {
        indentStack.pop();
        out.push('  }');
      }
    }

    let s = l.trim();
    const isBlockHeader = s.endsWith(':');

    s = s.replace(/^elif\s+(.+):/, ':($1){');
    s = s.replace(/^else\s*:/, '}:{');
    s = s.replace(/^if\s+(.+):/, '?($1){');
    s = s.replace(/^while\s+(.+):/, ';while($1){');
    s = s.replace(/^return\s+(.+)$/, '^$1');
    s = s.replace(/^return$/, '^null');
    s = s.replace(/\band\b/g, '&&').replace(/\bor\b/g, '||').replace(/\bnot\b/g, '!');
    s = s.replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false').replace(/\bNone\b/g, 'null');

    if (isBlockHeader && !isElseOrElif) {
      indentStack.push(indent + 4);
    } else if (!s.endsWith('{') && !s.endsWith('}')) {
      s += ';';
    }
    out.push('  ' + s);
  }

  while (indentStack.length > 1) {
    indentStack.pop();
    out.push('  }');
  }

  return out.join('\n');
}

function transpileJsTsToLin(jsSource, opts = {}) {
  try {
    return emitLinFromJs(jsSource, opts);
  } catch (err) {
    let s = jsSource;
    s = s.replace(/function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)\s*\{/g, '!$1($2){');
    s = s.replace(/\breturn\s+([^;]+);/g, '^$1;');
    s = s.replace(/\bif\s*\(([^)]+)\)\s*\{/g, '?($1){');
    return `@LIN:L1c:0.2\n${s}`;
  }
}
