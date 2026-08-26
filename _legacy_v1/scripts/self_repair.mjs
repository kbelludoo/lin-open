#!/usr/bin/env node
/** LIA self-repair MVP. Spec: spec/LIA_SELF_REPAIR.dicel — verifier/hash immutable. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../src/compiler.mjs';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MAX_DET = 6;
const MAX_LLM = 2;
const REQUEST_TIMEOUT_MS = Number(process.env.NINEROUTER_TIMEOUT_MS || 45000);
const NINE_MODELS = (
  process.env.NINEROUTER_MODELS ||
  process.env.NINEROUTER_MODEL ||
  'kgw/kilo-auto/free,cf/@cf/meta/llama-3.2-3b-instruct,kr/deepseek-3.2,auto'
).split(',').map((s) => s.trim()).filter(Boolean);
/** ^R_9R: failover_on_timeout_or_empty; try_next_model; never_block_on_one */
const DEFAULT_HOLDOUT = [
  ['foo', 'foo'], ['foo', 'bar'], ['hello world', 'hello world'],
  ['hello world', 'not hello world'], ['prefix', 'pre'], ['pre', 'prefix'],
  ['', ''], ['a', 'ab'], ['timing', 'timein'], ['same', 'same'],
];

function maskSecret(s) {
  const t = String(s || '');
  return !t ? '' : t.length <= 8 ? '***' : `${t.slice(0, 2)}***${t.slice(-2)}`;
}
function hashOutputs(o) {
  return crypto.createHash('sha256').update(JSON.stringify(o.map(String))).digest('hex');
}

function loadFnFromJs(js, exportName) {
  const tmp = path.join(os.tmpdir(), `lia_sr_${Date.now()}_${Math.random().toString(16).slice(2)}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  try {
    delete require.cache[tmp];
    const mod = require(tmp);
    const fn = typeof mod === 'function' ? mod : mod[exportName] || mod.default;
    if (typeof fn !== 'function') throw new Error(`no_fn:${exportName}`);
    return { fn, tmp };
  } catch (e) {
    fs.rmSync(tmp, { force: true });
    throw e;
  }
}

function runHoldout(fn, holdout) {
  return holdout.map((args) => {
    try { return String(fn(...args)); }
    catch (e) { return `ERROR:${e.message || e}`; }
  });
}

export function semanticHashFromJs(js, holdout, exportName = 'safeCompare') {
  const { fn, tmp } = loadFnFromJs(js, exportName);
  try {
    const outputs = runHoldout(fn, holdout);
    return { hash: hashOutputs(outputs), outputs, ok: true };
  } finally { fs.rmSync(tmp, { force: true }); }
}

export function verifyLia(ailText, oracle, opts = {}) {
  // param name kept for call-site clarity; body is LIA text (@LIA or legacy @AIL)
  const holdout = opts.holdout || DEFAULT_HOLDOUT;
  const exportName = opts.exportName || 'safeCompare';
  let compiled;
  try { compiled = compileLiaToJs(ailText, { exportMode: 'single' }); }
  catch (e) {
    return { ok: false, stage: 'compile', behavior_eq: 0, hash: null, error: String(e.message || e), js: null };
  }
  let got;
  try { got = semanticHashFromJs(compiled.js, holdout, exportName); }
  catch (e) {
    return { ok: false, stage: 'runtime', behavior_eq: 0, hash: null, error: String(e.message || e), js: compiled.js };
  }
  let match = 0;
  for (let i = 0; i < oracle.outputs.length; i++) if (got.outputs[i] === oracle.outputs[i]) match++;
  const behavior_eq = oracle.outputs.length ? match / oracle.outputs.length : 0;
  const hash_match = got.hash === oracle.hash;
  const ok = behavior_eq === 1.0 && hash_match;
  return {
    ok, stage: 'verify', behavior_eq, hash: got.hash, oracle_hash: oracle.hash, hash_match,
    error: ok ? null : 'holdout_mismatch', js: compiled.js, outputs: got.outputs,
  };
}

/** @deprecated use verifyLia */
export const verifyAil = verifyLia;

function mapFnBodies(ail, fn) {
  let out = '';
  let i = 0;
  while (i < ail.length) {
    if (ail[i] !== '!') { out += ail[i++]; continue; }
    const head = ail.slice(i).match(/^!([A-Za-z_$][\w$]*)\(([^)]*)\)(?:->[\w\[\]|,]+)?\{/);
    if (!head) { out += ail[i++]; continue; }
    const openBrace = i + head[0].length - 1;
    let depth = 0; let close = -1;
    for (let j = openBrace; j < ail.length; j++) {
      if (ail[j] === '{') depth++;
      else if (ail[j] === '}') { depth--; if (depth === 0) { close = j; break; } }
    }
    if (close < 0) { out += ail[i++]; continue; }
    const ann = head[0].slice(head[0].indexOf(')') + 1, head[0].length - 1);
    out += `!${head[1]}(${head[2]})${ann}{${fn(ail.slice(openBrace + 1, close), head[1], head[2])}}`;
    i = close + 1;
  }
  return out;
}

function lastTopStmtStart(b) {
  let depth = 0; let lastStart = 0;
  for (let i = 0; i < b.length; i++) {
    const c = b[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) lastStart = i + 1; }
    else if (c === '(') depth++;
    else if (c === ')') depth = Math.max(0, depth - 1);
    else if (c === ';' && depth === 0) lastStart = i + 1;
  }
  return lastStart;
}

/** Roslyn-style CodeFixes: diagnostic id → deterministic rewrite. */
export const FIXERS = [
  {
    id: 'F1_strip_comments',
    apply: (ail) => ail.replace(/\/\*[\s\S]*?\*\//g, '').split(/\r?\n/).map((l) => l.replace(/\/\/.*$/, '')).join('\n'),
  },
  {
    id: 'F2_return_keyword_to_sigil',
    apply: (ail) => mapFnBodies(ail, (body) => body.replace(/(^|[;{}\n])\s*return\s+/g, '$1^')),
  },
  {
    id: 'F3_ensure_terminal_return',
    apply: (ail) => mapFnBodies(ail, (body) => {
      const b = body.trim();
      if (!b) return body;
      const start = lastTopStmtStart(b);
      const last = b.slice(start).trim();
      if (!last || last.startsWith('^') || /^\s*return[\s\t]/.test(last) || /^[?#:]/.test(last)) return body;
      return `${b.slice(0, start)}^${last}`;
    }),
  },
  {
    id: 'F4_strip_js_decls',
    apply: (ail) => mapFnBodies(ail, (body) => body.replace(/(^|[;{}\n])\s*(?:var|let|const)\s+/g, '$1')),
  },
  {
    id: 'F5_strip_padding_lines',
    apply: (ail) => ail.split(/\r?\n/).filter((l) => {
      const t = l.trim();
      if (!t) return false;
      if (/^(@AIL:|\^|~G|\$K|=ex\{|!)/.test(t)) return true;
      return /[?!#^=]/.test(t) && !/^[A-Za-z]/.test(t);
    }).join('\n'),
  },
];

function applyFixers(ail, memory) {
  let cur = ail;
  const applied = [];
  for (const f of FIXERS) {
    const next = f.apply(cur);
    if (next !== cur) { applied.push(f.id); memory.push({ kind: 'fixer', id: f.id, note: `applied ${f.id}` }); cur = next; }
  }
  return { ail: cur, applied };
}

async function optionalNineRouterPatch(ail, verifyFail, memory) {
  const base = process.env.NINEROUTER_URL;
  if (!base) return { ail, used: false, reason: 'NINEROUTER_URL_absent' };
  const key = process.env.NINEROUTER_KEY || '';
  const url = `${base.replace(/\/$/, '')}/v1/chat/completions`;
  const messages = [
    { role: 'system', content: 'AIL repair. Never change hash/verifier. JSON only: {"patches":[{"op":"replace","old":"...","new":"...","reason":"..."}],"reflection":"..."}' },
    { role: 'user', content: JSON.stringify({ ail, fail: { stage: verifyFail.stage, error: verifyFail.error, behavior_eq: verifyFail.behavior_eq, hash_match: verifyFail.hash_match }, memory: memory.slice(-4) }) },
  ];
  const headers = { 'content-type': 'application/json' };
  if (key) headers.authorization = `Bearer ${key}`;

  let respText = '';
  let usedModel = null;
  const errors = [];
  for (const model of NINE_MODELS) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ model, temperature: 0.2, messages }),
        signal: ac.signal,
      });
      respText = await res.text();
      if (!res.ok) {
        const retryable = res.status === 408 || res.status === 429 || res.status >= 500;
        errors.push(`${model}:http_${res.status}`);
        memory.push({ kind: 'llm', note: `http_${res.status}`, model, key_masked: maskSecret(key) });
        if (!retryable) break;
        continue;
      }
      if (!String(respText || '').trim()) {
        errors.push(`${model}:empty`);
        memory.push({ kind: 'llm', note: 'empty_body', model });
        continue;
      }
      usedModel = model;
      break;
    } catch (e) {
      const note = e?.name === 'AbortError' ? 'timeout' : String(e.message || e);
      errors.push(`${model}:${note}`);
      memory.push({ kind: 'llm', note, model, key_masked: maskSecret(key) });
    } finally {
      clearTimeout(timer);
    }
  }
  if (!usedModel) {
    return { ail, used: true, reason: errors.join('|') || 'all_models_failed' };
  }

  let parsed;
  try {
    const outer = JSON.parse(respText);
    const content = outer.choices?.[0]?.message?.content || respText;
    const m = String(content).match(/\{[\s\S]*\}/);
    parsed = JSON.parse(m ? m[0] : content);
  } catch {
    memory.push({ kind: 'llm', note: 'unstructured_reject', model: usedModel });
    return { ail, used: true, reason: 'unstructured' };
  }
  let next = ail;
  for (const p of parsed.patches || []) {
    if (p?.op === 'replace' && p.old && typeof p.new === 'string' && next.includes(p.old)) next = next.replace(p.old, p.new);
  }
  if (parsed.reflection) memory.push({ kind: 'reflexion', note: String(parsed.reflection).slice(0, 240) });
  memory.push({ kind: 'llm', note: `ok:${usedModel}` });
  return { ail: next, used: true, reason: next === ail ? 'no_effect' : `patched:${usedModel}` };
}

export async function selfRepair(ailText, oracle, opts = {}) {
  const memory = [];
  let cur = ailText;
  let v = verifyLia(cur, oracle, opts);
  if (v.ok) return { status: 'ALREADY_OK', ail: cur, verify: v, memory, attempts: 0 };
  memory.push({ kind: 'detect', note: `${v.stage}:${v.error}`, behavior_eq: v.behavior_eq });

  for (let i = 0; i < MAX_DET; i++) {
    const { ail: fixed, applied } = applyFixers(cur, memory);
    if (!applied.length && i > 0) break;
    cur = fixed;
    v = verifyLia(cur, oracle, opts);
    if (v.ok) return { status: 'ACCEPTED', ail: cur, verify: v, memory, attempts: i + 1, path: 'deterministic' };
    memory.push({ kind: 'reject', note: `after_fixers behavior_eq=${v.behavior_eq} hash_match=${v.hash_match}` });
    if (!applied.length) break;
  }

  for (let i = 0; i < MAX_LLM; i++) {
    const patch = await optionalNineRouterPatch(cur, v, memory);
    if (!patch.used) break;
    cur = applyFixers(patch.ail, memory).ail;
    v = verifyLia(cur, oracle, opts);
    if (v.ok) return { status: 'ACCEPTED', ail: cur, verify: v, memory, attempts: MAX_DET + i + 1, path: '9router' };
    memory.push({ kind: 'reflexion', note: `llm_attempt_${i + 1}_${patch.reason}_still_fail` });
  }
  return { status: 'REJECTED', ail: cur, verify: v, memory, attempts: MAX_DET + MAX_LLM, path: 'none' };
}

function injectBugs(goodAil) {
  let broken = goodAil.replace(/\^r==0/, 'r==0');
  if (broken === goodAil) throw new Error('inject_failed: no ^r==0');
  broken = broken.replace('@AIL:L1c:0.2', '@AIL:L1c:0.2\n// INJECTED_BUG comment should not exist\nPAD_THIS_LINE_IS_PROSE');
  return broken.replace(/\^crypto\.timingSafeEqual/, 'return crypto.timingSafeEqual');
}

function writeReport(reportPath, data) {
  fs.writeFileSync(reportPath, [
    '@DICEL:AIL_SELF_REPAIR_MVP:1.0.0', '',
    '^repo="C:/Users/k/Documents/ail"',
    `^status="${data.status}"`, '^smoke="true"',
    `^behavior_eq=${data.behavior_eq}`, `^hash_match=${data.hash_match}`,
    `^oracle_hash="${data.oracle_hash}"`, `^repaired_hash="${data.repaired_hash || ''}"`,
    `^path="${data.path || ''}"`, `^attempts=${data.attempts}`, '',
    '@WHY_GAP {',
    '  reason: "LIA extracted as lingua/compiler first; P200 evolution stayed on Dicel L0 path"',
    '  note_pt: "Nao havia self-repair porque o loop mutation→verify→accept ficou no Dicel; LIA so tinha emit+compile+oracle"',
    '}', '',
    '@MVP {',
    '  detect: "compile_fail | hash_mismatch"',
    '  fixers: "F1..F5 deterministic"',
    '  llm: "optional_9router if NINEROUTER_URL"',
    '  accept: "behavior_eq==1.0 AND exact_hash"',
    '  immutable: "verifier/hash never mutated"',
    '}', '',
    '@SMOKE {',
    `  injected_bugs: ${JSON.stringify(data.injected)}`,
    `  before_ok: ${data.before_ok}`, `  after_ok: ${data.after_ok}`, `  pass: ${data.pass}`,
    '}', '',
    '@PRIOR_ART_TAKEAWAYS {',
    '  retry_verifier_feedback: "LangGraph+DSPy+Self-Debugging"',
    '  deterministic_first: "Roslyn CodeFix"',
    '  structured_patch: "Outlines/Guidance schema"',
    '  reflexion_memory: "failed repair notes"',
    '  detail: "spec/LIA_SELF_REPAIR_PRIOR_ART.dicel"',
    '}', '',
    '@FILES {',
    '  spec: "spec/LIA_SELF_REPAIR.dicel"',
    '  prior_art: "spec/LIA_SELF_REPAIR_PRIOR_ART.dicel"',
    '  script: "scripts/self_repair.mjs"',
    '  report: "INTEL_LIA_SELF_REPAIR_MVP.dicel"',
    '}', '',
    '@VERDICT_PT {',
    `  smoke: "${data.pass ? 'PASS' : 'FAIL'}"`,
    `  summary: "${data.summary_pt}"`,
    '}', '',
  ].join('\n'), 'utf8');
}

async function main() {
  const args = process.argv.slice(2);
  const smoke = args.includes('--smoke') || args.length === 0;
  const goodAil = fs.readFileSync(path.join(ROOT, 'examples', 'safe-compare.lia'), 'utf8');
  const { js: oracleJs } = compileLiaToJs(goodAil, { exportMode: 'single' });
  const oracle = semanticHashFromJs(oracleJs, DEFAULT_HOLDOUT, 'safeCompare');

  if (smoke) {
    const broken = injectBugs(goodAil);
    const before = verifyLia(broken, oracle);
    const result = await selfRepair(broken, oracle);
    const pass = result.status === 'ACCEPTED' && result.verify.ok && result.verify.hash === oracle.hash;
    const reportPath = path.join(ROOT, 'INTEL_LIA_SELF_REPAIR_MVP.dicel');
    writeReport(reportPath, {
      status: pass ? 'PASS' : 'FAIL', behavior_eq: result.verify?.behavior_eq ?? 0,
      hash_match: result.verify?.hash === oracle.hash, oracle_hash: oracle.hash,
      repaired_hash: result.verify?.hash, path: result.path, attempts: result.attempts,
      injected: ['missing_return_sigil', 'comment_line', 'padding_prose', 'return_keyword_on_native'],
      before_ok: before.ok, after_ok: result.verify?.ok ?? false, pass,
      summary_pt: pass
        ? 'Smoke PASS: bug injetado detectado, fixers deterministicos repararam, hash exacto behavior_eq=1.0'
        : `Smoke FAIL: status=${result.status} behavior_eq=${result.verify?.behavior_eq}`,
    });
    console.log(JSON.stringify({
      smoke: pass ? 'PASS' : 'FAIL', status: result.status, before_ok: before.ok,
      after_ok: result.verify?.ok, behavior_eq: result.verify?.behavior_eq,
      hash_match: result.verify?.hash === oracle.hash, oracle_hash: oracle.hash,
      repaired_hash: result.verify?.hash, path: result.path, report: reportPath,
      ninerouter: Boolean(process.env.NINEROUTER_URL),
    }, null, 2));
    process.exit(pass ? 0 : 1);
  }

  const ailIdx = args.indexOf('--ail') >= 0 ? args.indexOf('--ail') : args.indexOf('--lia');
  if (ailIdx < 0 || !args[ailIdx + 1]) {
    console.error('Usage: node scripts/self_repair.mjs --smoke | --lia file.lia');
    process.exit(2);
  }
  const result = await selfRepair(fs.readFileSync(args[ailIdx + 1], 'utf8'), oracle);
  console.log(JSON.stringify({ status: result.status, verify: result.verify, attempts: result.attempts }, null, 2));
  process.exit(result.status === 'ACCEPTED' || result.status === 'ALREADY_OK' ? 0 : 1);
}

if (path.resolve(fileURLToPath(import.meta.url)) === path.resolve(process.argv[1] || '')) {
  main().catch((e) => { console.error(String(e.message || e)); process.exit(1); });
}
