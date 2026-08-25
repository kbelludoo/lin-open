import { createHash } from 'node:crypto';

const RESERVED = ['var', 'let', 'const', 'return', 'if', 'else', 'while', 'for', 'in', 'of', 'null', 'true', 'false', 'undefined', 'void', 'typeof'];

export function canonicalize(params, body) {
  let canon = String(body || '').trim();
  canon = canon.replace(/\/\*[\s\S]*?\*\/|\/\/[^\r\n]*/g, '');
  canon = canon.replace(/\s+/g, ' ').replace(/\s*([=+\-*/%&|^<>(),;!?:{}\[\]])\s*/g, '$1').trim();
  const rawParams = String(params || '').split(',').map((p) => p.trim()).filter(Boolean);
  const paramTypes = rawParams.map((p) => (p.includes(':') ? p.split(':')[1].trim() : '')).join(',');
  const paramList = rawParams.map((p) => p.replace(/:.+$/, '').trim());
  for (let i = 0; i < paramList.length; i++) {
    const re = new RegExp(`\\b${escapeRe(paramList[i])}\\b`, 'g');
    canon = canon.replace(re, `$${i}`);
  }
  const locals = [];
  const assignRe = /(?:^|[;{(])\s*([a-zA-Z_$][\w$]*)\s*=(?!=)/g;
  let match;
  while ((match = assignRe.exec(canon)) !== null) {
    const id = match[1];
    if (!locals.includes(id) && !id.startsWith('$') && !RESERVED.includes(id)) {
      locals.push(id);
    }
  }
  for (let i = 0; i < locals.length; i++) {
    const re = new RegExp(`\\b${escapeRe(locals[i])}\\b`, 'g');
    canon = canon.replace(re, `_l${i}`);
  }
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '==').replace(/!==/g, '!=');
  canon = canon.replace(/;+/g, ';').replace(/;+$/, '');
  return `(${paramList.length}:${paramTypes})${canon}`;
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function semanticHash(params, body) {
  const canonical = canonicalize(params, body);
  return createHash('sha256').update(canonical, 'utf8').digest('hex').slice(0, 16);
}

export function programHashes(prog) {
  const out = {};
  for (const fn of prog.fns) {
    const paramsText = Array.isArray(fn.params)
      ? fn.params.map((p) => (p.type ? `${p.name}:${p.type}` : p.name)).join(',')
      : String(fn.paramsRaw || fn.params || '');
    out[fn.name] = semanticHash(paramsText, fn.rawBody ?? fn.body);
  }
  return out;
}

export { createHash };
