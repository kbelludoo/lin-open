// LIN Effects Engine (Dogfooding effects_core.lin)
import { createRequire } from 'node:module';
import { renderBody } from './render_core.mjs';

const require = createRequire(import.meta.url);
const { firstUseIsRead: linFirstUseIsRead, collectAssignedIds: linCollectAssignedIds } = require('./effects_core.compiled.cjs');

export const firstUseIsRead = linFirstUseIsRead;
export const collectAssignedIds = linCollectAssignedIds;

const NATIVE_BUILTINS = /\b(String|Number|Math|Buffer|Array|Object|Error|JSON|console|process|require|globalThis|window|document|fetch|setTimeout|setInterval|crypto)\b/;

const BUILTIN_SET = new Set([
  'String', 'Number', 'Math', 'Buffer', 'Array', 'Object', 'Error', 'JSON', 'console',
  'process', 'require', 'globalThis', 'window', 'document', 'fetch', 'setTimeout',
  'setInterval', 'crypto', 'true', 'false', 'null', 'undefined',
]);

function fnBodyText(fn) {
  if (typeof fn.body === 'string') return fn.body;
  return renderBody(fn.body || []);
}

export function inferEffect(fn, allFns) {
  const body = fnBodyText(fn);
  const paramNames = Array.isArray(fn.params)
    ? fn.params.map((p) => (typeof p === 'string' ? p : p.name))
    : String(fn.params || '').split(',').map((p) => p.replace(/:[\w\[\]|,]+$/g, '').trim()).filter(Boolean);
  const params = new Set(paramNames);
  const locals = new Set(collectAssignedIds(body));
  for (const p of params) locals.add(p);
  const effects = new Set();

  if (/\bthrow\b/.test(body)) effects.add('Throw');
  if (NATIVE_BUILTINS.test(body)) effects.add('Native');

  const allOtherRefs = (allFns || [])
    .filter((g) => g.name !== fn.name)
    .map((g) => fnBodyText(g))
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

  const idRe = /\b([A-Za-z_$][\w$]*)\b/g;
  let rm;
  while ((rm = idRe.exec(body)) !== null) {
    const id = rm[1];
    if (!params.has(id) && !locals.has(id) && !BUILTIN_SET.has(id)) {
      effects.add('Read');
    }
  }

  for (const other of allFns || []) {
    if (other.name === fn.name) continue;
    const callRe = new RegExp(`\\b${other.name}\\s*\\(`);
    if (callRe.test(body)) {
      for (const e of String(other.effect || inferEffectOnce(other, allFns)).split(/\|/)) {
        if (e) effects.add(e);
      }
    }
  }

  if (effects.has('Write')) return 'Write';
  if (effects.has('Throw')) return 'Throw';
  if (effects.has('Native')) return 'Native';
  if (effects.has('Read')) return 'Read';
  return 'Pure';
}

function inferEffectOnce(fn, allFns) {
  const body = fnBodyText(fn);
  const params = new Set(
    Array.isArray(fn.params)
      ? fn.params.map((p) => (typeof p === 'string' ? p : p.name))
      : String(fn.params || '').split(',').map((p) => p.trim()).filter(Boolean),
  );
  const locals = new Set(collectAssignedIds(body));
  for (const p of params) locals.add(p);
  if (/\bthrow\b/.test(body)) return 'Throw';
  if (NATIVE_BUILTINS.test(body)) return 'Native';
  const assignRe = /(?:^|[;{},])\s*([A-Za-z_$][\w$]*)\s*=(?!=)/g;
  let am;
  while ((am = assignRe.exec(body)) !== null) {
    const id = am[1];
    if (['return', 'if', 'for', 'else', 'function', 'var', 'let', 'const'].includes(id)) continue;
    if (!locals.has(id)) return 'Write';
  }
  const idRe = /\b([A-Za-z_$][\w$]*)\b/g;
  let rm;
  while ((rm = idRe.exec(body)) !== null) {
    const id = rm[1];
    if (!params.has(id) && !locals.has(id) && !BUILTIN_SET.has(id)) return 'Read';
  }
  return 'Pure';
}
