import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { oracleFromFn } from '../scripts/clone_lia_oracle.mjs';
import {
  canPublishFullRepo, fileCoverage, isTypeOnlyModule, missedExtracts, normalizeSkipToFail, multiAllFull,
  honestNucleusMulti, formatStubIntel, defaultEmitTarget, futurePickBestLang, refuseStubBenchmark,
  rankQualityRows, allRowsFull, pickBestFromRows, benchRepeatCount,
  langMemoryKind, langIsMemorySafe, inMemoryHostLang, cMemoryLabel,
} from '../scripts/clone_lin_full_repo_gate.mjs';
import { writeIntel } from '../scripts/clone_lin_improve.mjs';
import { extractJsFunctions } from '../src/emitter.mjs';
import { compileLia } from '../src/multi_emit.mjs';

const remapped = normalizeSkipToFail([
  { status: 'pass', name: 'ok', srcRel: 'a.js' },
  { status: 'skip', name: 'hard', srcRel: 'a.js', reason: 'host_or_module_ref' },
]);
assert.equal(remapped.skip, 0);
assert.equal(remapped.pass, 1);
assert.equal(remapped.fail, 1);
assert.match(remapped.fail_names[0], /skip_eq_fail:host_or_module_ref/);

const cov = fileCoverage([
  { status: 'pass', name: 'ok', srcRel: 'a.js' },
  { status: 'fail', name: 'hard', srcRel: 'a.js' },
  { status: 'pass', name: 'b', srcRel: 'b.js' },
]);
assert.equal(cov.files_total, 2);
assert.equal(cov.files_ok, 1);
assert.equal(cov.full, false);

assert.equal(canPublishFullRepo({
  jsFull: true, allLangFull: true, filesFull: true, skip: 0, fail: 0, pass: 3,
}), true);
assert.equal(canPublishFullRepo({
  jsFull: true, allLangFull: true, filesFull: false, skip: 0, fail: 1, pass: 2,
}), false);
assert.equal(canPublishFullRepo({
  jsFull: true, allLangFull: false, filesFull: true, skip: 0, fail: 0, pass: 1,
}), false);

const missed = missedExtracts(
  'function keep(x){return x}\nfunction drop({a}){return a}\n',
  [{ name: 'keep' }],
);
assert.deepEqual(missed.map((m) => m.name), ['drop']);

const nestedSrc = 'function FileViewer(){function handleClick(){return 1}return handleClick()}';
assert.equal(missedExtracts(nestedSrc, [{ name: 'FileViewer' }]).length, 0);
const nestedFns = extractJsFunctions(nestedSrc);
assert.ok(nestedFns.some((f) => f.name === 'FileViewer'));
assert.equal(nestedFns.some((f) => f.name === 'handleClick'), false);
const genericFns = extractJsFunctions('export function foo<T extends Record<string, unknown>>(x){return x}');
assert.ok(genericFns.some((f) => f.name === 'foo'));

const reservedLin = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!bool(x){^!!x}
!assert(x){^x}
=ex{bool,assert}`;
const goRes = compileLia(reservedLin, { target: 'go', exportMode: 'multiple', withMain: false, package: 'clonefn' });
assert.match(goRes.code, /func bool_/);
assert.doesNotMatch(goRes.code, /func bool\(/);
const pyRes = compileLia(reservedLin, { target: 'py', exportMode: 'multiple', withMain: false });
assert.match(pyRes.code, /def assert_/);
assert.doesNotMatch(pyRes.code, /def assert\(/);
const cRes = compileLia(reservedLin, { target: 'c', exportMode: 'multiple', withMain: false });
assert.match(cRes.code, /bool_/);
assert.doesNotMatch(cRes.code, /long long bool\(/);

const dollarLin = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!$(){^null}
=ex{$}`;
const pyDollar = compileLia(dollarLin, { target: 'py', exportMode: 'multiple', withMain: false });
assert.match(pyDollar.code, /def dollar/);
assert.doesNotMatch(pyDollar.code, /def \$/);
const goDollar = compileLia(dollarLin, { target: 'go', exportMode: 'multiple', withMain: false, package: 'clonefn' });
assert.match(goDollar.code, /func dollar/);
assert.doesNotMatch(goDollar.code, /func \$/);

const destSrc = 'export function createTerminalService({ maxEvents = 2000 } = {}) { return 1 }';
assert.ok(extractJsFunctions(destSrc).some((f) => f.name === 'createTerminalService'));
assert.equal(missedExtracts(destSrc, extractJsFunctions(destSrc)).length, 0);

const nestedGen = oracleFromFn({
  name: 'createArtifactParser',
  params: [],
  body: 'const state: ParserState = {x:1}; function* feed(delta: string): Generator { yield delta; } return {feed};',
});
assert.equal(nestedGen.status, 'ok');

const uuidFn = oracleFromFn({
  name: 'randomUuid',
  params: [],
  body: 'const c = globalThis.crypto; if (c && c.randomUUID) return c.randomUUID(); return "x";',
});
assert.equal(uuidFn.status, 'ok');
assert.equal(uuidFn.outputs[0], '00000000-0000-4000-8000-000000000001');

const easy = oracleFromFn({ name: 'add', params: ['a', 'b'], body: 'return a+b', bindings: {}, siblings: [] });
assert.equal(easy.status, 'ok');
assert.equal(typeof easy.hash, 'string');
assert.equal(easy.hash.length, 64);

const host = oracleFromFn({
  name: 'load',
  params: [],
  body: 'yield 1',
  bindings: {},
  siblings: [],
});
assert.equal(host.status, 'fail');
assert.notEqual(host.status, 'skip');

const awaited = oracleFromFn({
  name: 'rainbow',
  params: ['string', 'offset'],
  body: 'return string;',
  bindings: {},
  siblings: [{ name: 'animateString', params: ['string'], body: 'await delay(2);' }],
});
assert.equal(awaited.status, 'ok');

assert.equal(isTypeOnlyModule('export type Foo = string;'), true);
assert.equal(isTypeOnlyModule('function add(a,b){return a+b}'), false);
assert.equal(isTypeOnlyModule('suite("x", () => { bench("y", () => {}); });'), true);

const nucleusOk = {
  js: { PASS: 2, SKIP: 0, FAIL: 0 },
  ts: { PASS: 2, SKIP: 0, FAIL: 0 },
  py: { PASS: 2, SKIP: 0, FAIL: 0 },
  go: { PASS: 2, SKIP: 0, FAIL: 0 },
  rust: { PASS: 2, SKIP: 0, FAIL: 0 },
  c: { PASS: 0, SKIP: 2, FAIL: 0 },
  java: { PASS: 2, SKIP: 0, FAIL: 0 },
};
assert.equal(multiAllFull(nucleusOk), true);
assert.equal(multiAllFull({ ...nucleusOk, java: { PASS: 0, SKIP: 2, FAIL: 0 } }), false);
assert.equal(multiAllFull({ ...nucleusOk, c: { PASS: 0, SKIP: 0, FAIL: 2 } }), false);
assert.equal(multiAllFull({ ...nucleusOk, js: { PASS: 2, SKIP: 0, FAIL: 1 } }), false);
assert.equal(multiAllFull({
  ...nucleusOk,
  cs: { PASS: 2, SKIP: 0, FAIL: 0 },
  asm: { PASS: 2, SKIP: 0, FAIL: 0 },
}), true, 'stub langs must not enter the gate');

assert.equal(defaultEmitTarget(), 'ts');
assert.equal(futurePickBestLang().status, 'NOT_RUN');
assert.equal(refuseStubBenchmark('asm'), true);
assert.equal(refuseStubBenchmark('ts'), false);
assert.ok(Number(benchRepeatCount()) >= 5);

const rankIn = [
  { lang: 'ts', compileOk: true, runOk: true, ms: 10, bytes: 100 },
  { lang: 'c', compileOk: true, runOk: true, ms: 2, bytes: 200 },
  { lang: 'js', compileOk: true, runOk: true, ms: 2, bytes: 50 },
];
assert.equal(allRowsFull(rankIn), true);
const ranked = rankQualityRows(rankIn);
assert.equal(ranked[0].lang, 'js');
assert.equal(ranked[1].lang, 'c');
assert.equal(ranked[2].lang, 'ts');
assert.equal(ranked[0].rank, 1);
const picked = pickBestFromRows(rankIn);
assert.equal(picked.status, 'MEASURED');
assert.equal(picked.lang, 'js');
assert.equal(picked.fastest, 'js');
assert.equal(picked.best_in_memory, 'js');
assert.equal(picked.in_memory_host, 'rust');
assert.equal(picked.c_memory, 'unsafe');
assert.equal(futurePickBestLang({ rows: rankIn }).lang, 'js');
assert.equal(pickBestFromRows([{ lang: 'ts', compileOk: true, runOk: false, ms: 1, bytes: 1 }]).status, 'NOT_FULL');
assert.equal(futurePickBestLang([{ lang: 'go', compileOk: true, runOk: true, ms: 3, bytes: 10 }]).status, 'MEASURED');

assert.equal(langMemoryKind('c'), 'unsafe');
assert.equal(langIsMemorySafe('c'), false);
assert.equal(langIsMemorySafe('rust'), true);
assert.equal(inMemoryHostLang(), 'rust');
assert.equal(cMemoryLabel(), 'unsafe');
assert.equal(defaultEmitTarget(), 'ts');

const seven = [
  { lang: 'c', compileOk: true, runOk: true, ms: 32.46, bytes: 1798 },
  { lang: 'rust', compileOk: true, runOk: true, ms: 35.20, bytes: 2270 },
  { lang: 'go', compileOk: true, runOk: true, ms: 35.46, bytes: 3267 },
  { lang: 'py', compileOk: true, runOk: true, ms: 105.27, bytes: 1736 },
  { lang: 'ts', compileOk: true, runOk: true, ms: 113.98, bytes: 487 },
  { lang: 'js', compileOk: true, runOk: true, ms: 115.27, bytes: 447 },
  { lang: 'java', compileOk: true, runOk: true, ms: 197.86, bytes: 2579 },
];
assert.equal(rankQualityRows(seven)[0].lang, 'c');
const hostPick = pickBestFromRows(seven);
assert.equal(hostPick.fastest, 'c');
assert.equal(hostPick.best_in_memory, 'rust');
assert.equal(hostPick.systems_pick, 'rust');
assert.equal(hostPick.memory_winner, 'rust');
assert.equal(hostPick.in_memory_host, 'rust');
assert.equal(hostPick.runtime_winner, 'rust');
assert.equal(hostPick.lang, 'rust');
assert.notEqual(hostPick.lang, 'c');
assert.equal(hostPick.c_memory, 'unsafe');
assert.match(String(hostPick.note), /CLI emit stays ts/);

assert.doesNotMatch(honestNucleusMulti({ js: { PASS: 1, SKIP: 0, FAIL: 0 }, asm: { PASS: 15, SKIP: 0, FAIL: 0 } }), /asm:P/);
assert.match(formatStubIntel(), /EXPERIMENTAL_NOT_PASS/);
assert.doesNotMatch(formatStubIntel(), /:P\d+/);

const intelDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_intel_'));
const intelPath = writeIntel(intelDir, {
  slug: 'honesty',
  status: 'PASS',
  suite_rate: 1,
  pass: 1,
  fail: 0,
  skip: 0,
  coverage: { files_ok: 1, files_total: 1 },
  source: 'https://example.com/x.git',
  multi: {
    js: { PASS: 1, SKIP: 0, FAIL: 0 },
    ts: { PASS: 1, SKIP: 0, FAIL: 0 },
    py: { PASS: 1, SKIP: 0, FAIL: 0 },
    go: { PASS: 1, SKIP: 0, FAIL: 0 },
    rust: { PASS: 1, SKIP: 0, FAIL: 0 },
    c: { PASS: 0, SKIP: 1, FAIL: 0 },
    java: { PASS: 1, SKIP: 0, FAIL: 0 },
    asm: { PASS: 15, SKIP: 0, FAIL: 0 },
    prolog: { PASS: 15, SKIP: 0, FAIL: 0 },
  },
  multi_line: 'js:P1/S0/F0 asm:P15/S0/F0 prolog:P15/S0/F0',
  stub_line: 'asm:P15/S0/F0',
  note_pt: 'DONE all-lang 1.0 asm:P15/S0/F0 prolog:P15/S0/F0',
  pass_names: ['index.js:fn'],
  improve_lin: 'loop_mode_no_improve',
});
const intelText = fs.readFileSync(intelPath, 'utf8');
assert.doesNotMatch(intelText, /\b(cs|lua|elixir|crystal|kotlin|hcl|julia|scala|haskell|prolog|zig|nim|asm):P\d+/);
assert.match(intelText, /multi="ts:P1\/S0\/F0 js:P1\/S0\/F0 py:P1\/S0\/F0 go:P1\/S0\/F0 rust:P1\/S0\/F0 c:P0\/S1\/F0 java:P1\/S0\/F0"/);
assert.match(intelText, /EXPERIMENTAL_NOT_PASS/);
assert.match(intelText, /stub_not_suite=true/);
fs.rmSync(intelDir, { recursive: true, force: true });

console.log('ok clone_full_repo_gate');
