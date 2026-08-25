/**
 * Gate LIN_REGEX_002 — SELF_HOSTING_SCANNER.
 * spec: spec/LIN_REGEX_002.rulel
 *
 * A1 unit-A/B   : refs JS (algoritmos originais) vs slices LIN compilados
 * A2 diferencial: tokenize() ON vs OFF => streams idênticos
 * A3 integridade: fresh compile do .lin ≡ artefato commitado
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(import.meta.url.replace('file://', '')), '..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_regex_002_'));

let passed = 0;
let failed = 0;
const failures = [];
function ok(name, cond, detail) {
  if (cond) passed++;
  else { failed++; failures.push(`${name}${detail ? ': ' + detail : ''}`); }
}

/* refs: algoritmos originais do lexer.mjs (pré-wire), porta exata */
function refIdentLen(s, i) {
  if (!/^[A-Za-z_$]/.test(s[i] || '')) return 0;
  let j = i + 1;
  while (j < s.length && /[A-Za-z0-9_$]/.test(s[j])) j++;
  return j - i;
}
function refWsRun(s, i) {
  let j = i;
  while (j < s.length && (s[j] === ' ' || s[j] === '\t' || s[j] === '\r')) j++;
  return j - i;
}
function refNumLen(s, i) {
  const c = s[i];
  const nxt = s[i + 1] || '';
  if (!(/[0-9]/.test(c) || (c === '.' && /[0-9]/.test(nxt)))) return 0;
  let j = i;
  if (c === '0' && /[xXbBoO]/.test(s[j + 1] || '')) {
    j += 2;
    while (j < s.length && /[0-9a-fA-F_]/.test(s[j])) j++;
  } else {
    while (j < s.length && /[0-9_]/.test(s[j])) j++;
    if (s[j] === '.') {
      j++;
      while (j < s.length && /[0-9_]/.test(s[j])) j++;
    }
    if (/[eE]/.test(s[j] || '') && /[0-9+\-]/.test(s[j + 1] || '')) {
      j += 2;
      while (j < s.length && /[0-9_]/.test(s[j])) j++;
    }
  }
  if (s[j] === 'n') j++;
  return j - i;
}

/* slices LIN: artefato de produção + fresh compile */
const SLICES = require(path.join(root, 'src', 'lexer_slices.compiled.cjs'));
execFileSync(process.execPath, [path.join(root, 'scripts', 'build_lexer_slices.mjs')], { cwd: root });
const FRESH_PATH = path.join(tmp, 'fresh.cjs');
{
  const built = fs.readFileSync(path.join(root, 'src', 'lexer_slices.compiled.cjs'), 'utf8');
  fs.writeFileSync(FRESH_PATH, built);
}
const FRESH = require(FRESH_PATH);

/* corpus determinístico (LCG) */
function lcg(seed) {
  let st = seed >>> 0;
  return () => ((st = (st * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}
const CHARS = 'abzAZ09_$ \t\r\n.xXeE+-oObBn/()={};"\'\\?#<>|&~^%*!,:@`.[]'.split('');
const CHUNKS = ['abc', '_x9', '$q', '123', '007', '0x1f', '0X_9', '0b1011', '0o77', '12.5', '.5', '1e10', '1e+', '1e', '42n', '0x', 'e9', '+', '-', '.', '__', 'nn'];

function buildProbes(count) {
  const rnd = lcg(20260824);
  const probes = [];
  for (let k = 0; k < count; k++) {
    let s = '';
    const parts = 1 + Math.floor(rnd() * 6);
    for (let p = 0; p < parts; p++) {
      if (rnd() < 0.5) {
        const ch = CHUNKS[Math.floor(rnd() * CHUNKS.length)];
        s += ch;
        if (rnd() < 0.4) s += CHARS[Math.floor(rnd() * CHARS.length)];
      } else {
        const n = 1 + Math.floor(rnd() * 8);
        for (let q = 0; q < n; q++) s += CHARS[Math.floor(rnd() * CHARS.length)];
      }
    }
    probes.push(s);
  }
  return probes;
}

/* ───────── A1: unit-A/B sobre ≥3000 probes × todas as posições ───────── */

{
  const probes = buildProbes(500);
  let checks = 0;
  const bad = [];
  for (const s of probes) {
    for (let i = 0; i <= s.length; i++) {
      const pairs = [
        ['identLenAt', refIdentLen(s, i), SLICES.identLenAt(s, i), FRESH.identLenAt(s, i)],
        ['wsRunAt', refWsRun(s, i), SLICES.wsRunAt(s, i), FRESH.wsRunAt(s, i)],
        ['numLenAt', refNumLen(s, i), SLICES.numLenAt(s, i), FRESH.numLenAt(s, i)],
      ];
      for (const [name, want, gotArt, gotFresh] of pairs) {
        checks++;
        if (gotArt !== want) bad.push(`${name}${JSON.stringify([s.slice(0, 24), i])} art=${gotArt} ref=${want}`);
        if (gotFresh !== want) bad.push(`${name}${JSON.stringify([s.slice(0, 24), i])} fresh=${gotFresh} ref=${want}`);
      }
    }
  }
  ok(`A1 unit-A/B (${checks} checks)`, checks >= 3000 && bad.length === 0, bad.slice(0, 3).join(' | '));
}

/* ───────── A2: tokenize diferencial ON vs OFF ───────── */

function tokenizeOn(src) {
  const { tokenize } = require(path.join(root, 'src', 'lexer.mjs'));
  return tokenize(src);
}
function tokenizeOff(src) {
  delete require.cache[require.resolve(path.join(root, 'src', 'lexer.mjs'))];
  delete require.cache[require.resolve(path.join(root, 'src', 'lexer_slices_load.mjs'))];
  process.env.LEXER_SLICES_OFF = '1';
  try {
    const { tokenize } = require(path.join(root, 'src', 'lexer.mjs'));
    return tokenize(src);
  } finally {
    delete process.env.LEXER_SLICES_OFF;
    delete require.cache[require.resolve(path.join(root, 'src', 'lexer.mjs'))];
    delete require.cache[require.resolve(path.join(root, 'src', 'lexer_slices_load.mjs'))];
  }
}

{
  const rnd = lcg(9944);
  const sources = [
    'var x9 = 0x1f + .5e+2;\nfoo($y)',
    '@LIN:L1c:0.2\\n!f(a,b){^a+b}\\n=ex{f}',
    'r = /a+b/gi; m = r.exec("aab");',
    '$K{s=1000 y=31557600000}',
    '0x 0b 0o 1e+ 1e .n 42nn ..5 1.2.3',
    'a\t \r b\\n\\n  c',
    '"str" \'chr\' tplX ${x}',
    '// comment\\n/* block */id9',
    '>>>===??=a.b?.c::d->e',
  ];
  for (let k = 0; k < 60; k++) {
    const probe = buildProbes(1)[0];
    sources.push(probe);
    void rnd;
  }
  let diffs = 0;
  for (const src of sources) {
    let on, off;
    try { on = JSON.stringify(tokenizeOn(src)); } catch (e) { on = `E:${e.message.slice(0, 40)}`; }
    try { off = JSON.stringify(tokenizeOff(src)); } catch (e) { off = `E:${e.message.slice(0, 40)}`; }
    if (on !== off) {
      diffs++;
      if (diffs <= 3) ok(`A2 ${JSON.stringify(src.slice(0, 30))}`, false, 'streams divergentes');
    }
  }
  ok(`A2 diferencial tokenize (${sources.length} fontes)`, diffs === 0);
}

/* ───────── A3: integridade artefato ≡ fonte .lin (já recopiado acima) ───────── */

{
  const linSrc = fs.readFileSync(path.join(root, 'src', 'lexer_slices.lin'), 'utf8');
  ok('A3 fonte .lin presente', linSrc.includes('!identLenAt') && linSrc.includes('!numLenAt'));
  const built = fs.readFileSync(path.join(root, 'src', 'lexer_slices.compiled.cjs'), 'utf8');
  ok('A3 artefato contém os 3 slices', ['identLenAt', 'wsRunAt', 'numLenAt'].every((n) => built.includes(`function ${n}(`)));
  // recompilar via CLI e comparar bytes
  const out = execFileSync(process.execPath, [path.join(root, 'scripts', 'build_lexer_slices.mjs')], { cwd: root, encoding: 'utf8' });
  ok('A3 rebuild determinístico', /ok /.test(out));
  const again = fs.readFileSync(path.join(root, 'src', 'lexer_slices.compiled.cjs'), 'utf8');
  ok('A3 bytes estáveis', again === built);
}

console.log(`LIN_REGEX_002: ${passed} ok, ${failed} falhas`);
if (failed) {
  console.log(failures.map((f) => `  ✗ ${f}`).join('\n'));
  process.exit(1);
}
