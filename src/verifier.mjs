import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { parseProgram } from './parser.mjs';
import { compile, REAL_TARGETS } from './compiler.mjs';
import { semanticHash } from './semantic_hash.mjs';
import { assertJsSyntax, runInMemory } from './vm.mjs';
import { parseRulel, validateComms } from './rulel.mjs';

export const GATES = {
  PARSE: 'G_PARSE',
  EXPORTS: 'G_EXPORTS',
  HASH_STABLE: 'G_HASH_STABLE',
  JS_SYNTAX: 'G_JS_SYNTAX',
  BEHAVIOR: 'G_BEHAVIOR',
  NUCLEUS_INTACT: 'G_NUCLEUS_INTACT',
  RULEL_COMMS: 'G_RULEL_COMMS',
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function sha256(text) {
  return createHash('sha256').update(String(text), 'utf8').digest('hex');
}

export function verify(source, opts = {}) {
  const report = {
    ok: true,
    gates: [],
    startedAt: new Date().toISOString(),
  };
  const gate = (name, passed, detail) => {
    report.gates.push({ gate: name, pass: !!passed, detail: detail || null });
    if (!passed) report.ok = false;
  };

  let prog = null;
  try {
    prog = parseProgram(source);
    gate(GATES.PARSE, true, `${prog.fns.length} fns`);
  } catch (e) {
    gate(GATES.PARSE, false, e.message);
    report.finishedAt = new Date().toISOString();
    return report;
  }

  try {
    const fnNames = new Set(prog.fns.map((f) => f.name));
    const missing = prog.exports.filter((e) => !fnNames.has(e.split(/\s+as\s+/)[0].trim()));
    gate(GATES.EXPORTS, missing.length === 0, missing.length ? `missing=${missing.join(',')}` : `${prog.exports.length} exports`);
  } catch (e) {
    gate(GATES.EXPORTS, false, e.message);
  }

  try {
    const renamed = prog.fns.map((f) => {
      const pairs = (f.params || []).map((p, i) => [p.name, `_p${i}`]);
      let body = String(f.rawBody || '');
      for (const [orig, rep] of pairs) {
        body = body.replace(new RegExp(`\\b${orig.replace(/[$]/g, '\\$')}\\b`, 'g'), rep);
      }
      const paramsRaw = pairs.map(([_, rep], i) => `${rep}${f.params[i].type ? `:${f.params[i].type}` : ''}`).join(',');
      return { paramsRaw, rawBody: body };
    });
    const h1 = JSON.stringify(prog.fns.map((f) => semanticHash(f.paramsRaw || '', f.rawBody)));
    const h2 = JSON.stringify(renamed.map((f) => semanticHash(f.paramsRaw, f.rawBody)));
    gate(GATES.HASH_STABLE, h1 === h2, 'rename-invariant canonicalization');
  } catch (e) {
    gate(GATES.HASH_STABLE, false, e.message);
  }

  let compiled = null;
  try {
    compiled = compile(source, { target: 'js' });
    assertJsSyntax(compiled.code);
    gate(GATES.JS_SYNTAX, true, `${compiled.code.length} chars`);
  } catch (e) {
    gate(GATES.JS_SYNTAX, false, e.message);
    report.finishedAt = new Date().toISOString();
    return report;
  }

  if (opts.behavior && typeof opts.behavior === 'object') {
    try {
      const mod = runInMemory(compiled.code);
      const cases = Array.isArray(opts.behavior) ? opts.behavior : [opts.behavior];
      let ran = 0;
      for (const c of cases) {
        const fnRef = mod[c.fn];
        if (typeof fnRef !== 'function') throw new Error(`export not callable: ${c.fn}`);
        const got = fnRef(...(c.args || []));
        const expected = c.want;
        const eq = deepEq(got, expected);
        if (!eq) throw new Error(`${c.fn}(${JSON.stringify(c.args)}) = ${JSON.stringify(got)} want ${JSON.stringify(expected)}`);
        ran++;
      }
      gate(GATES.BEHAVIOR, true, `${ran} cases`);
    } catch (e) {
      gate(GATES.BEHAVIOR, false, e.message);
    }
  } else {
    gate(GATES.BEHAVIOR, true, 'skipped (no fixtures)');
  }

  try {
    const lockPath = path.join(__dirname, '..', 'nucleus.lock.json');
    const lock = JSON.parse(readFileSync(lockPath, 'utf8'));
    const verifierSrc = readFileSync(path.join(__dirname, 'verifier.mjs'), 'utf8');
    const actual = sha256(verifierSrc);
    gate(GATES.NUCLEUS_INTACT, actual === lock.verifier_sha256, `expected=${lock.verifier_sha256.slice(0, 12)} actual=${actual.slice(0, 12)}`);
  } catch (e) {
    gate(GATES.NUCLEUS_INTACT, false, e.message);
  }

  if (opts.rulelSource) {
    try {
      const parsed = parseRulel(opts.rulelSource);
      const validation = validateComms(parsed);
      gate(GATES.RULEL_COMMS, validation.ok, validation.ok ? parsed.header?.id || '' : `missing=${validation.missing.join(',')}`);
    } catch (e) {
      gate(GATES.RULEL_COMMS, false, e.message);
    }
  }

  report.hashes = {};
  for (const [name, h] of Object.entries(compiled.hashes)) report.hashes[name] = h;
  report.targetsReady = REAL_TARGETS.filter((t) => ['js', 'ts'].includes(t));
  report.finishedAt = new Date().toISOString();
  return report;
}

function deepEq(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((x, i) => deepEq(x, b[i]));
  }
  if (typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    return ka.every((k) => deepEq(a[k], b[k]));
  }
  return Number.isNaN(a) && Number.isNaN(b);
}
