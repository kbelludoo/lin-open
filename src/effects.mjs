import { renderBody } from './render_core.mjs';

const NATIVE_BUILTINS = /\b(String|Number|Math|Buffer|Array|Object|Error|JSON|console|process|require|globalThis|window|document|fetch|setTimeout|setInterval|crypto)\b/;

const BUILTIN_SET = new Set([
  'String', 'Number', 'Math', 'Buffer', 'Array', 'Object', 'Error', 'JSON', 'console',
  'process', 'require', 'globalThis', 'window', 'document', 'fetch', 'setTimeout',
  'setInterval', 'crypto', 'true', 'false', 'null', 'undefined',
]);

export function firstUseIsRead(body, id) {
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

export function collectAssignedIds(body) {
  const ids = new Set();
  const re = /(?:^|[;{,}])\s*([A-Za-z_$][\w$]*)\s*=(?!=)/g;
  let m;
  const s = `;${body}`;
  while ((m = re.exec(s)) !== null) {
    const id = m[1];
    if (!['return', 'if', 'for', 'else', 'function', 'var', 'let', 'const'].includes(id)) ids.add(id);
  }
  const forInit = /for\(([^;]*);/g;
  while ((m = forInit.exec(body)) !== null) {
    const im = m[1].match(/^([A-Za-z_$][\w$]*)\s*=/);
    if (im) ids.add(im[1]);
  }
  return [...ids];
}

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
