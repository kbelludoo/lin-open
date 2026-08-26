// LIN Semantic Hash Engine (Dogfooding semantic_hash_core.lin)
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { canonicalize: linCanonicalize, escapeRe: linEscapeRe } = require('./semantic_hash_core.compiled.cjs');

export const canonicalize = linCanonicalize;
export const escapeRe = linEscapeRe;

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
