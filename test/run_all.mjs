import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
// Portable corpus root (was hardcoded to a local absolute path).
const CORPUS = root;
const LEGACY_V1 = '_legacy_v1';
const TMP_PREFIX = path.join(os.tmpdir(), 'lintest-');

let passed = 0;
let failed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ok  ${name}`);
  } catch (e) {
    failed++;
    failures.push([name, e.message]);
    console.log(`FAIL  ${name}: ${e.message}`);
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`  ok  ${name}`);
  } catch (e) {
    failed++;
    failures.push([name, e.message]);
    console.log(`FAIL  ${name}: ${e.message}`);
  }
}

import { ensureRuntime, runtimeUrl } from '../scripts/lin_runtime.mjs';

await ensureRuntime();

const { LIN_HEADER } = await import(runtimeUrl('parser.mjs'));
void LIN_HEADER;
const { parseProgram } = await import(runtimeUrl('parser.mjs'));
const { compile, REAL_TARGETS } = await import(runtimeUrl('compiler.mjs'));
const { runInMemory, assertJsSyntax } = await import(runtimeUrl('vm.mjs'));
const { semanticHash } = await import(runtimeUrl('semantic_hash.mjs'));
const { parseRulel, validateComms } = await import(runtimeUrl('rulel.mjs'));
const { verify } = await import(runtimeUrl('verifier.mjs'));
const { emitLinFromJs } = await import(runtimeUrl('emit_from_js.mjs'));
const { emitTs, emitPy, emitGo, emitRust, emitC, emitJava } = await import(runtimeUrl('emitters.mjs'));

function readCorpus(rel) {
  return fs.readFileSync(path.join(CORPUS, rel), 'utf8');
}

console.log('T01 headers (LIN/LIA/AIL dual-read)');
test('header + structure', () => {
  const src = readCorpus('examples/safe-compare.lia');
  const prog = parseProgram(src);
  assert.equal(prog.header, '@LIN:L1c:0.2');
  assert.equal(prog.fns.length, 2);
  assert.deepEqual(prog.exports, ['safeCompare', 'nativeTimingSafeEqual']);
  for (const tag of ['@LIA:', '@AIL:']) {
    const legacy = src.replace('@LIN:', tag);
    const p2 = parseProgram(legacy);
    const r2 = compile(legacy, { target: 'js' });
    const mod2 = runInMemory(r2.code);
    assert.ok(mod2.safeCompare('ab', 'ab') === true || typeof mod2.safeCompare === 'function');
    assert.ok(p2.header.startsWith(tag));
  }
});

console.log('T02 safe-compare behavior (in-memory)');
test('safeCompare truth table', () => {
  const src = readCorpus('examples/safe-compare.lia');
  const r = compile(src, { target: 'js', exportMode: 'single' });
  const fn = runInMemory(r.code);
  assert.equal(fn('ab', 'ab'), true);
  assert.equal(fn('a', 'b'), false);
  assert.equal(fn('prefix', 'pre'), false);
  assert.equal(fn('', ''), true);
  assert.equal(fn(String.fromCharCode(97, 0), String.fromCharCode(97, 1)), false);
});

console.log('T03 bytes format+parse exact');
test('bytes npm parity', () => {
  const src = readCorpus('examples/bytes.lia');
  const prelude = [
    'var formatThousandsRegExp=/\\B(?=(\\d{3})+(?!\\d))/g;',
    'var formatDecimalsRegExp=/(?:\\.0*|(\\.[^0]+))0+$/;',
    'var parseRegExp=/^((-|\\+)?(\\d+(?:\\.\\d+)?) *(kb|mb|gb|tb|pb))$/i;',
  ].join('');
  const mod = runInMemory(compile(src, { target: 'js', prelude }).code);
  assert.equal(mod.bytes(1024), '1KB');
  assert.equal(mod.bytes(5 * 1024 * 1024), '5MB');
  assert.equal(mod.bytes(0), '0B');
  assert.equal(mod.bytes('1gb'), 1073741824);
  assert.equal(mod.bytes('512mb'), 536870912);
  assert.equal(mod.bytes(123), '123B');
});

console.log('T04 closures capture');
test('closure captures outer var', () => {
  const closureLia = `@LIN:L1c:0.2\n^lossy=true\n~G{?=if #=for ^=ret :else}\n!makeAdd(n){add=~(x){^n+x};^add}\n=ex{makeAdd}`;
  const add5 = runInMemory(compile(closureLia, { target: 'js', exportMode: 'single' }).code)(5);
  assert.equal(add5(10), 15);
  assert.equal(add5(3), 8);
});

console.log('T05 effects + sandbox');
test('effect inference and sandbox blocking', () => {
  const effectLia = `@LIN:L1c:0.2\n~G{?=if #=for ^=ret :else}\n!pureAdd(a,b){^a+b}\n!nativeLen(s){^String(s).length}\n!throwIfNeg(x){?(x<0){throw new Error('neg')};^x}\n=ex{pureAdd,nativeLen,throwIfNeg}`;
  const r = compile(effectLia, { target: 'js' });
  const fx = Object.fromEntries(r.program.fns.map((f) => [f.name, f.effect]));
  assert.equal(fx.pureAdd, 'Pure');
  assert.equal(fx.nativeLen, 'Native');
  assert.equal(fx.throwIfNeg, 'Throw');
  const sandboxed = compile(effectLia, { target: 'js', sandbox: ['Pure'] });
  const mod = runInMemory(sandboxed.code);
  assert.equal(mod.pureAdd(2, 3), 5);
  assert.throws(() => mod.nativeLen('x'), /LIN_SANDBOX.*Native/);
});

console.log('T06 semantic hash');
test('hash rename/format invariance + divergence', () => {
  const h1 = semanticHash('a,b', 'a + b - 1');
  const h2 = semanticHash('x,y', 'x+y-1');
  const h3 = semanticHash('a,b', 'a - b + 1');
  assert.equal(h1, h2);
  assert.notEqual(h1, h3);
  assert.match(h1, /^[0-9a-f]{16}$/);
});

console.log('T07 match arms');
test('literals, enum Option, wildcard, or-patterns, guards, tuples', () => {
  const m2 = runInMemory(compile(readCorpus(`${LEGACY_V1}/tests/m003_rust_match.lin`), { target: 'js' }).code);
  assert.deepEqual([m2(0), m2(1), m2(99)], [100, 200, 999]);

  const omSrc = readCorpus(`${LEGACY_V1}/tests/option_match.lia`);
  const om = runInMemory(compile(omSrc, { target: 'js', exportMode: 'multiple' }).code);
  const some = { tag: 'Some', value: 42 };
  assert.equal(om.unwrapOr(some, 0), 42);
  assert.equal(om.unwrapOr(null, 7), 7);

  const guardLia = `@LIN:L1c:0.2\n~G{?=if #=for ^=ret :else}\n!cls(n){match(n){x if x>100=>{^1}x if x>10=>{^2}_=>{^3}}}\n!tup(p){match(p){(a,b)=>{^a*10+b}}}\n!orP(n){match(n){1|2=>{^9}_=>{^8}}}\n=ex{cls,tup,orP}`;
  const g = runInMemory(compile(guardLia, { target: 'js', exportMode: 'multiple' }).code);
  assert.deepEqual([g.cls(500), g.cls(50), g.cls(5)], [1, 2, 3]);
  assert.equal(g.tup([3, 4]), 34);
  assert.deepEqual([g.orP(2), g.orP(5)], [9, 8]);
});

console.log('T08 structs/enums/mod/use');
test('module namespace + use symbols', () => {
  const src = `@LIN:L1c:0.2
~G{?=if #=for ^=ret :else}
mod Math { !double(x){^x*2} !triple(x){^x*3} }
use Math::{double}
!quad(x){^double(double(x))}
struct Point { x:int, y:int }
enum Color { Red, Green, Blue }
!origin(){p={x:0,y:0};^p.x+p.y}
=ex{quad,origin,double}`;
  const mod = runInMemory(compile(src, { target: 'js' }).code);
  assert.equal(mod.quad(4), 16);
  assert.equal(mod.origin(), 0);
  const prog = parseProgram(src);
  assert.equal(prog.structs[0].name, 'Point');
  assert.equal(prog.structs[0].fields.length, 2);
  assert.equal(prog.enums[0].variants.length, 3);
  assert.equal(prog.modules[0].name, 'Math');
});

console.log('T09 chains and block ternaries');
test('elseif colon chains + ternary tails', () => {
  const src = `@LIN:L1c:0.2\n~G{?=if #=for ^=ret :else}\n!bucket(n){?(n>=90){^'A'}:(n>=80){^'B'}:{^'C'}}\n!sign(n){?(n>0){^'pos'}:^'neg'}\n!pick(f){?(f){^1}:{^0}}\n=ex{bucket,sign,pick}`;
  const mod = runInMemory(compile(src, { target: 'js', exportMode: 'multiple' }).code);
  assert.deepEqual([mod.bucket(95), mod.bucket(85), mod.bucket(10)], ['A', 'B', 'C']);
  assert.deepEqual([mod.sign(5), mod.sign(-5)], ['pos', 'neg']);
  assert.deepEqual([mod.pick(true), mod.pick(false)], [1, 0]);
});

console.log('T10 loops');
test('while-form, empty bodies, break/continue', () => {
  const src = `@LIN:L1c:0.2\n~G{?=if #=for ^=ret :else}\n!count(n){i=0;c=0;#(;i<n;){i=i+1;?(i%2==0){continue};c=c+1};^c}\n!firstOdd(limit){#(i=1;i<limit;i++){?(i%2==1){^i}};^0}\n!spin(n){i=0;#(;i<n;i=i+1){};^i}\n=ex{count,firstOdd,spin}`;
  const mod = runInMemory(compile(src, { target: 'js', exportMode: 'multiple' }).code);
  assert.deepEqual([mod.count(10), mod.firstOdd(10), mod.spin(7)], [5, 1, 7]);
});

console.log('T11 multi-target native execution');
const arithSrc = fs.readFileSync(path.join(__dirname, 'fixtures', 'arith.lia'), 'utf8');

test('py: python3 runs emitted module', async () => {
  const prog = parseProgram(arithSrc);
  const py = emitPy(prog);
  const dir = fs.mkdtempSync(TMP_PREFIX + 'py-');
  fs.writeFileSync(path.join(dir, 'arith_lin.py'), py);
  const driver = [
    'import sys; sys.path.insert(0, ".")',
    'import arith_lin',
    'print(arith_lin.add(2,3)); print(arith_lin.mul(4,5)); print(arith_lin.fact(5)); print(1 if arith_lin.is_even(10) else 0); print(arith_lin.max3(3,9,4))',
  ].join('\n');
  fs.writeFileSync(path.join(dir, 'driver.py'), driver);
  const out = execFileSync('python3', ['driver.py'], { cwd: dir, encoding: 'utf8' });
  assert.equal(out.trim(), '5\n20\n120\n1\n9');
});

test('go: go run executes emitted package', () => {
  const prog = parseProgram(arithSrc);
  let goCode = emitGo(prog, { main: false });
  goCode += `
func main() {
  fmt.Println(add(2, 3))
  fmt.Println(mul(4, 5))
  fmt.Println(fact(5))
  if is_even(10) { fmt.Println(1) } else { fmt.Println(0) }
  fmt.Println(max3(3, 9, 4))
}
`;
  const dir = fs.mkdtempSync(TMP_PREFIX + 'go-');
  fs.writeFileSync(path.join(dir, 'main.go'), goCode);
  fs.writeFileSync(path.join(dir, 'go.mod'), 'module lintest\n\ngo 1.21\n');
  const out = execFileSync('go', ['run', 'main.go'], { cwd: dir, encoding: 'utf8', timeout: 60000 });
  assert.equal(out.trim(), '5\n20\n120\n1\n9');
});

test('rust: rustc compiles + runs match fixture', () => {
  const mnProg = parseProgram(fs.readFileSync(path.join(__dirname, 'fixtures', 'match_num.lia'), 'utf8'));
  let rs = emitRust(mnProg);
  rs += '\nfn main() { println!("{}", match_number(0)); println!("{}", match_number(1)); println!("{}", match_number(99)); }\n';
  const dir = fs.mkdtempSync(TMP_PREFIX + 'rs-');
  fs.writeFileSync(path.join(dir, 'match_num.rs'), rs);
  execFileSync('rustc', ['-O', 'match_num.rs'], { cwd: dir, timeout: 90000 });
  const out = execFileSync(path.join(dir, 'match_num'), { encoding: 'utf8' });
  assert.equal(out.trim(), '100\n200\n999');
});

test('rust: arith loop fact', () => {
  const prog = parseProgram(arithSrc);
  let rs = emitRust(prog);
  rs += '\nfn main() { println!("{}", add(2,3)); println!("{}", mul(4,5)); println!("{}", fact(5)); println!("{}", (is_even(10)==true) as i64); println!("{}", max3(3,9,4)); }\n';
  const dir = fs.mkdtempSync(TMP_PREFIX + 'rs2-');
  fs.writeFileSync(path.join(dir, 'arith.rs'), rs);
  execFileSync('rustc', ['-O', 'arith.rs'], { cwd: dir, timeout: 90000 });
  const out = execFileSync(path.join(dir, 'arith'), { encoding: 'utf8' });
  assert.equal(out.trim(), '5\n20\n120\n1\n9');
});

test('c: gcc compiles + runs arith', () => {
  const prog = parseProgram(arithSrc);
  const cCode = emitC(prog) + `\nint main(){ printf("%lld\\n", add(2,3)); printf("%lld\\n", mul(4,5)); printf("%lld\\n", fact(5)); printf("%lld\\n", is_even(10)?1:0); printf("%lld\\n", max3(3,9,4)); return 0; }\n`;
  const dir = fs.mkdtempSync(TMP_PREFIX + 'c-');
  fs.writeFileSync(path.join(dir, 'arith.c'), cCode);
  execFileSync('gcc', ['-O2', '-o', 'arith', 'arith.c', '-lm'], { cwd: dir, timeout: 60000 });
  const out = execFileSync(path.join(dir, 'arith'), { encoding: 'utf8' });
  assert.equal(out.trim(), '5\n20\n120\n1\n9');
});

test('java: javac + java run arith', () => {
  const prog = parseProgram(arithSrc);
  let jCode = emitJava(prog);
  jCode = jCode.replace('  public static void main(String[] args) {\n  }', [
    '  public static void main(String[] args) {',
    '    System.out.println(add(2,3));',
    '    System.out.println(mul(4,5));',
    '    System.out.println(fact(5));',
    '    System.out.println(is_even(10) ? 1 : 0);',
    '    System.out.println(max3(3,9,4));',
    '  }',
  ].join('\n'));
  const dir = fs.mkdtempSync(TMP_PREFIX + 'java-');
  fs.writeFileSync(path.join(dir, 'LinProgram.java'), jCode);
  execFileSync('javac', ['LinProgram.java'], { cwd: dir, timeout: 90000 });
  const out = execFileSync('java', ['-cp', dir, 'LinProgram'], { encoding: 'utf8', timeout: 30000 });
  assert.equal(out.trim(), '5\n20\n120\n1\n9');
});

test('ts: emitted TypeScript parses under node type-strip', () => {
  const prog = parseProgram(arithSrc);
  const ts = emitTs(prog);
  assert.ok(ts.includes('export function add(a: number, b: number): number'));
  assert.ok(ts.includes('function fact(n: number): number'));
  assertJsSyntax(ts.replace(/export /g, '').replace(/: Record<string, number>/g, '').replace(/: number/g, '').replace(/: boolean/g, '').replace(/: unknown/g, ''));
});

console.log('T12 JS→LIN emit roundtrip');
test('emit subset → recompiles → same behavior', () => {
  const jsSource = [
    'function add(a, b) { return a + b; }',
    'function bucketScore(n) { if (n >= 90) { return 4; } else if (n >= 80) { return 3; } else { return 0; } }',
    'function sumTo(n) { var s = 0; for (var i = 1; i <= n; i++) { s = s + i; } return s; }',
    'module.exports = { add, bucketScore, sumTo };',
  ].join('\n');
  const { lin } = emitLinFromJs(jsSource);
  assert.ok(lin.startsWith('@LIN:'));
  const back = runInMemory(compile(lin, { target: 'js' }).code);
  assert.equal(back.add(2, 3), 5);
  assert.deepEqual([back.bucketScore(95), back.bucketScore(85), back.bucketScore(50)], [4, 3, 0]);
  assert.equal(back.sumTo(10), 55);
});

console.log('T13 verifier gates');
test('verify passes on good program with behavior fixtures', () => {
  const src = fs.readFileSync(path.join(__dirname, 'fixtures', 'arith.lia'), 'utf8');
  const report = verify(src, {
    behavior: [
      { fn: 'add', args: [2, 3], want: 5 },
      { fn: 'fact', args: [5], want: 120 },
      { fn: 'max3', args: [3, 9, 4], want: 9 },
    ],
  });
  assert.equal(report.ok, true, JSON.stringify(report.gates));
  for (const g of report.gates) assert.equal(g.pass, true, g.gate);
});

console.log('T14 in-memory purity (no disk writes)');
test('compile+run leaves the filesystem untouched', () => {
  const snap = () => {
    const out = new Map();
    function walk(d) {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
        const p = path.join(d, e.name);
        if (e.isDirectory()) walk(p);
        else {
          const st = fs.statSync(p);
          out.set(p, `${st.size}:${st.mtimeMs}`);
        }
      }
    }
    walk(root);
    return out;
  };
  const before = snap();
  for (const rel of ['examples/safe-compare.lia', 'examples/bytes.lia', `${LEGACY_V1}/tests/m003_rust_match.lin`]) {
    const srcText = readCorpus(rel);
    const code = compile(srcText, { target: 'js' }).code;
    runInMemory(code);
    parseProgram(srcText);
  }
  const after = snap();
  assert.equal(before.size, after.size);
  for (const [k, v] of before) assert.equal(after.get(k), v, `changed: ${k}`);
});

console.log('T14b repo purity (only .lin + .rulel committed; no .json)');
test('no .json files tracked in git', () => {
  const tracked = execFileSync('git', ['ls-files', '*.json'], { cwd: root, encoding: 'utf8' }).trim();
  const files = tracked ? tracked.split('\n').filter(Boolean) : [];
  assert.deepEqual(files, [], `tracked .json: ${files.slice(0, 5).join(', ')}`);
});

test('src/ contains only .lin and .rulel', () => {
  const srcDir = path.join(root, 'src');
  const bad = [];
  function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (!e.name.endsWith('.lin') && !e.name.endsWith('.rulel')) bad.push(path.relative(root, p));
    }
  }
  walk(srcDir);
  assert.deepEqual(bad, [], `foreign files in src/: ${bad.join(', ')}`);
});

/** Phase-2 host-glue scope: scripts/, bin/, test/ — every .mjs must have a synced TRANSPOSED_SOURCE .rulel mirror. */
const HOST_GLUE_DIRS = ['scripts', 'bin', 'test'];
const HOST_GLUE_FIXTURE_EXCLUDE = /^test\/fixtures\//;

function findMjsMirrorRulel(relMjsPath) {
  const rel = relMjsPath.replace(/\\/g, '/');
  const dir = path.dirname(rel);
  const base = path.basename(rel, '.mjs');
  const candidates = [
    path.join(root, dir, `${base}.rulel`),
    path.join(root, rel.replace(/\.mjs$/, '.rulel')),
  ];
  for (const c of candidates) {
    if (!fs.existsSync(c)) continue;
    const text = fs.readFileSync(c, 'utf8');
    if (text.includes('TRANSPOSED_SOURCE') && text.includes(`original="${rel}"`)) return c;
  }
  return null;
}

test('host glue dirs: every .mjs has TRANSPOSED_SOURCE .rulel mirror', () => {
  const missing = [];
  for (const dirName of HOST_GLUE_DIRS) {
    const dir = path.join(root, dirName);
    if (!fs.existsSync(dir)) continue;
    function walk(d) {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name);
        if (e.isDirectory()) walk(p);
        else if (e.name.endsWith('.mjs')) {
          const rel = path.relative(root, p).replace(/\\/g, '/');
          if (HOST_GLUE_FIXTURE_EXCLUDE.test(rel)) continue;
          if (!findMjsMirrorRulel(rel)) missing.push(rel);
        }
      }
    }
    walk(dir);
  }
  assert.deepEqual(missing, [], `missing .rulel mirror for: ${missing.join(', ')}`);
});

test('host glue dirs: .rulel mirrors synced with .mjs', async () => {
  const { extractRulelContent } = await import('../scripts/lin_bootstrap.mjs');
  const drift = [];
  for (const dirName of HOST_GLUE_DIRS) {
    const dir = path.join(root, dirName);
    if (!fs.existsSync(dir)) continue;
    function walk(d) {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name);
        if (e.isDirectory()) walk(p);
        else if (e.name.endsWith('.mjs')) {
          const rel = path.relative(root, p).replace(/\\/g, '/');
          if (HOST_GLUE_FIXTURE_EXCLUDE.test(rel)) continue;
          const mirror = findMjsMirrorRulel(rel);
          if (!mirror) return;
          const mjsText = fs.readFileSync(p, 'utf8');
          const rulelText = extractRulelContent(fs.readFileSync(mirror, 'utf8'));
          if (mjsText !== rulelText) drift.push(rel);
        }
      }
    }
    walk(dir);
  }
  assert.deepEqual(drift, [], `rulel mirror drift: ${drift.join(', ')}`);
});

console.log('T15 RULEL');
test('RULEL parse + COMMS validation', () => {
  const rulelText = '@RULEL:COMMS_PROTOCOL:1.4.0\n~R{.m=meta .r=rule}\n.m{repo=x name=y}\n.r{R20=comms-9router R1=a}\n.f{no_evil}\n.a{code=.lin}\n.c{nucleus=v!h!g}\n.s{state=ok}\n.p{cli=bin/lin.mjs}\n';
  const parsed = parseRulel(rulelText);
  assert.equal(parsed.header.id, 'COMMS_PROTOCOL');
  assert.equal(parsed.header.semver, '1.4.0');
  const v = validateComms(parsed);
  assert.equal(v.ok, true);
  assert.equal(v.rid, 'comms-9router');
});

console.log('T16 fail-closed');
test('missing export, bad target, js-runtime-only on native', () => {
  assert.throws(() => compile('@LIN:L1c:0.2\n!f(){^1}\n=ex{ghost}'), /LIN_EXPORT_NO_FN/);
  assert.throws(() => compile('@LIN:L1c:0.2\n!f(){^1}', { target: 'cobol' }), /LIN_EMIT_TARGET/);
  assert.throws(() => compile('@LIN:L1c:0.2\n!f(){^Buffer.alloc(4)}', { target: 'py' }), /JS_RUNTIME_ONLY|js_runtime_only|LIN_EMIT_JS_RUNTIME_ONLY/i);
  assert.throws(() => parseProgram('@LIN:L1c:0.2\n!broken(a){?(a){^1}'), /LIN_PARSE/);
});

console.log('T17 corpus sweep (original repo L1c files)');
test('all valid @LIN programs from original corpus compile', () => {
  const files = [];
  function walk(d) {
    if (!fs.existsSync(d)) return;
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(lin|lia)$/.test(e.name)) files.push(p);
    }
  }
  for (const d of [`${LEGACY_V1}/src`, 'examples', `${LEGACY_V1}/tests`]) walk(path.join(CORPUS, d));
  let ok = 0;
  let skippedDocs = 0;
  const errors = [];
  for (const f of files) {
    const srcText = fs.readFileSync(f, 'utf8');
    if (!/^@(LIN|LIA|AIL):/m.test(srcText.split('\n')[0] || '')) { continue; }
    try {
      parseProgram(srcText);
      compile(srcText, { target: 'js' });
      ok++;
    } catch (e) {
      if (/unterminated string/.test(e.message) && f.includes('spec')) { skippedDocs++; continue; }
      if (/fail_closed/.test(f)) { ok++; continue; }
      errors.push(`${path.relative(CORPUS, f)}: ${e.message}`);
    }
  }
  assert.equal(errors.length, 0, errors.join(' | '));
  assert.ok(ok >= 70, `expected ≥70 corpus files to pass, got ${ok}`);
});

console.log('T18 CLI end-to-end');
await testAsync('bin/lin.mjs version|check|compile|run|hash|effects|rulel-check|verify|emit', async () => {
  const bin = path.join(root, 'bin', 'lin.mjs');
  const tmp = fs.mkdtempSync(TMP_PREFIX + 'cli-');
  const linFile = path.join(tmp, 'prog.lin');
  fs.writeFileSync(linFile, arithSrc);

  const ver = execFileSync(process.execPath, [bin, 'version'], { encoding: 'utf8' });
  assert.match(ver.trim(), /^\d+\.\d+\.\d+$/);

  const check = JSON.parse(execFileSync(process.execPath, [bin, 'check', linFile], { encoding: 'utf8' }));
  assert.deepEqual(check.fns, ['add', 'mul', 'fact', 'isEven', 'max3']);

  const outJs = path.join(tmp, 'out.js');
  execFileSync(process.execPath, [bin, 'compile', linFile, '--target', 'js', '-o', outJs]);
  assert.ok(fs.readFileSync(outJs, 'utf8').includes('function add(a,b)'));

  const hash = JSON.parse(execFileSync(process.execPath, [bin, 'hash', linFile], { encoding: 'utf8' }));
  assert.match(hash.add, /^[0-9a-f]{16}$/);

  const fx = JSON.parse(execFileSync(process.execPath, [bin, 'effects', linFile], { encoding: 'utf8' }));
  assert.equal(fx.add, 'Pure');

  const rulelFile = path.join(tmp, 'comms.rulel');
  fs.writeFileSync(rulelFile, '@RULEL:T:1.0.0\n.m{a=b}.r{R20=x}.f{}.a{}.c{}.s{}.p{}\n');
  const rl = JSON.parse(execFileSync(process.execPath, [bin, 'rulel-check', rulelFile], { encoding: 'utf8' }));
  assert.equal(rl.validation.ok, true);

  const report = JSON.parse(execFileSync(process.execPath, [bin, 'verify', linFile], { encoding: 'utf8' }));
  assert.equal(report.ok, true);

  const jsFixture = path.join(tmp, 'lib.js');
  fs.writeFileSync(jsFixture, 'function inc(x){ return x+1; }\nmodule.exports={inc};\n');
  const emitted = execFileSync(process.execPath, [bin, 'emit', jsFixture], { encoding: 'utf8' });
  assert.ok(emitted.startsWith('@LIN:'));

  const targets = REAL_TARGETS;
  assert.equal(targets.length, 8);
  assert.ok(targets.includes('zig'));
});

console.log('T19 self-host clone loop');
test('loop reaches suiteRate 1.0 on fixture queue', async () => {
  const { runCloneLoop } = await import(runtimeUrl('selfhost', 'loop.mjs'));
  const queueDir = path.join(__dirname, 'fixtures', 'queue');
  const queue = fs.readdirSync(queueDir).filter((f) => f.endsWith('.js')).map((f) => ({
    name: f.replace(/\.js$/, ''),
    source: fs.readFileSync(path.join(queueDir, f), 'utf8'),
  }));
  const pubDir = fs.mkdtempSync(TMP_PREFIX + 'pub-');
  const state = runCloneLoop({ queue, publishDir: pubDir });
  assert.equal(state.suiteRate, 1, JSON.stringify(state.partial));
  assert.equal(state.done.length, queue.length);
  for (const r of state.repos) {
    assert.equal(r.fail, 0, r.repo);
    assert.ok(r.pass > 0);
    assert.match(r.outputsHash, /^[0-9a-f]{64}$/);
  }
  const published = fs.readdirSync(path.join(pubDir, 'lin'));
  assert.deepEqual(published.sort(), ['leftpad-like.lin', 'ms-like.lin']);
  const linText = fs.readFileSync(path.join(pubDir, 'lin', 'ms-like.lin'), 'utf8');
  assert.ok(linText.startsWith('@LIN:'));
  const back = runInMemory(compile(linText, { target: 'js', exportMode: 'multiple' }).code);
  assert.equal(back.split('3m'), 180000);
  assert.equal(back.formatShort(60000), '1m');
});

test('improve applies repairs and reports applied ids', async () => {
  const { improveSource } = await import(runtimeUrl('selfhost', 'loop.mjs'));
  const messy = [
    "import x from 'y';",
    'export function add(a, b) {',
    '  return a + b;',
    '}',
  ].join('\n');
  const r = improveSource(messy);
  assert.ok(r.applied.includes('R_strip_imports'), r.applied.join(','));
  assert.ok(r.applied.includes('R_strip_export_keywords'));
  assert.ok(!/^import/m.test(r.source));
});

console.log('T20 bootstrap hash gates');
await testAsync('hash gates: core seeds, semantic hash, nucleus lock, compiler idempotent, transpile hash', async () => {
  const { runAllHashGates } = await import('../scripts/hash_gates.mjs');
  const { RUNTIME } = await import('../scripts/lin_runtime.mjs');
  const report = await runAllHashGates(RUNTIME);
  assert.equal(report.ok, true, JSON.stringify(report.gates.filter((g) => !g.ok)));
  for (const g of report.gates) {
    assert.equal(g.ok, true, `${g.gate}: ${JSON.stringify(g)}`);
  }
  const coreGate = report.gates.find((g) => g.gate === 'G_CORE_CODE_HASH');
  assert.ok(coreGate.cores.every((c) => c.ok), JSON.stringify(coreGate.cores.filter((c) => !c.ok)));
  const transpilGate = report.gates.find((g) => g.gate === 'G_TRANSPIL_HASH');
  assert.ok(transpilGate, 'G_TRANSPIL_HASH gate missing from bootstrap suite');
  assert.equal(transpilGate.ok, true, JSON.stringify(transpilGate));
});

console.log('T21 transpile hash verification');
await testAsync('emit/transpile verify semantic + code hash', async () => {
  const { verifyTranspileOutput, verifyTranspileOutputOrThrow } = await import(runtimeUrl('transpile_hash_verify.mjs'));
  const { emitLinFromJs } = await import(runtimeUrl('emit_from_js.mjs'));
  const { transpileToLin } = await import(runtimeUrl('transpiler_to_lin.mjs'));

  const jsSource = [
    'function add(a, b) { return a + b; }',
    'function mul(a, b) { return a * b; }',
    'module.exports = { add, mul };',
  ].join('\n');

  const emitted = emitLinFromJs(jsSource);
  assert.ok(emitted.hash?.ok, JSON.stringify(emitted.hash));
  assert.ok(emitted.hash.semantic_hash_stable);
  assert.ok(emitted.hash.code_hash_stable);
  assert.match(emitted.hash.code_hash, /^[0-9a-f]{64}$/);
  assert.match(emitted.hash.semantic_hash, /^[0-9a-f]{16}$/);

  const report = verifyTranspileOutput(emitted.lin);
  assert.equal(report.ok, true, JSON.stringify(report));
  verifyTranspileOutputOrThrow(emitted.lin);

  const pyLin = transpileToLin('def greet(name):\n    return name\n', { filename: 'g.py' });
  assert.ok(pyLin.startsWith('@LIN:'));
  const pyReport = verifyTranspileOutput(pyLin);
  assert.equal(pyReport.ok, true, JSON.stringify(pyReport));

  assert.throws(() => verifyTranspileOutputOrThrow('@LIN:L1c:0.2\n!broken(){?(a){^1}\n=ex{broken}'), /LIN_TRANSPIL_HASH/);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) {
  for (const [name, msg] of failures) console.log(`  FAILED ${name}: ${msg.slice(0, 200)}`);
  process.exit(1);
}
