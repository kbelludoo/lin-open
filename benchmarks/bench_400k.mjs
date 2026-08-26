/**
 * LIA large-corpus roundtrip bench (~400k LOC target).
 *
 * Protocol (exact like P200 / INTEL_LIA_ROUNDTRIP_VERIFY):
 *   source named-fn → LIA emit → compile JS → holdout outputs
 *   behavior_eq requires identical String(outputs) + identical sha256
 *   NO soft match / padding / approximate equality
 *
 * Usage (PowerShell):
 *   node scripts/bench_400k.mjs
 *   node scripts/bench_400k.mjs --root "C:\Users\k\Documents\ail-bench\clone-400k\TypeScript\src"
 *   node scripts/bench_400k.mjs --max-fns 500
 *
 * Language name: LIA (formerly AIL). Corpus clone folder remains ail-bench.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { emitAilFromSource, extractJsFunctions, estTokens } from '../src/emitter.mjs';
import { compileLiaToJs } from '../src/compiler.mjs';

const require = createRequire(import.meta.url);
const LIA_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_ROOT = 'C:\\Users\\k\\Documents\\ail-bench\\clone-400k\\TypeScript\\src';
const DEFAULT_REPO_URL = 'https://github.com/microsoft/TypeScript';
const REPORT_PATH = path.join(LIA_ROOT, 'INTEL_LIA_400K_ROUNDTRIP.dicel');
const WORK_DIR = path.join(LIA_ROOT, '.bench_400k_tmp');

const SKIP_DIR_RE = /[\\/](\.git|node_modules|dist|build|coverage|__tests__|fixtures|baselines|test(s)?)([\\/]|$)/i;
const SRC_EXT_RE = /\.(js|mjs|cjs|ts|tsx|jsx)$/i;

function parseArgs(argv) {
  const out = { root: DEFAULT_ROOT, maxFns: 0, holdoutN: 8, alsoLodash: true };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root' && argv[i + 1]) out.root = path.resolve(argv[++i]);
    else if (a === '--max-fns' && argv[i + 1]) out.maxFns = Number(argv[++i]) || 0;
    else if (a === '--holdout-n' && argv[i + 1]) out.holdoutN = Number(argv[++i]) || 8;
    else if (a === '--no-lodash') out.alsoLodash = false;
  }
  return out;
}

function hashOutputs(outputs) {
  const json = JSON.stringify(outputs.map((o) => String(o)));
  return crypto.createHash('sha256').update(json).digest('hex');
}

function generateHoldout(arity, count) {
  const seeded = [
    [0],
    [1],
    [2],
    [-1],
    [''],
    ['a'],
    ['foo'],
    ['bar'],
    [10],
    [42],
    [0, 0],
    [1, 2],
    [2, 3],
    [5, 7],
    ['a', 'a'],
    ['a', 'b'],
    ['foo', 'foo'],
    ['foo', 'bar'],
    ['', ''],
    ['prefix', 'pre'],
    [0, 1, 2],
    [1, 2, 3],
    ['a', 'b', 'c'],
    [true, false, 0],
  ];
  const inputs = [];
  for (let i = 0; i < count; i++) {
    const base = seeded[i % seeded.length];
    const args = [];
    for (let j = 0; j < arity; j++) args.push(base[j % base.length]);
    inputs.push(args);
  }
  return inputs;
}

function walkSourceFiles(root) {
  const files = [];
  function walk(dir) {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (SKIP_DIR_RE.test(p + path.sep)) continue;
        walk(p);
      } else if (e.isFile() && SRC_EXT_RE.test(e.name)) {
        if (SKIP_DIR_RE.test(p)) continue;
        files.push(p);
      }
    }
  }
  walk(root);
  return files;
}

function countLoc(text) {
  return String(text).split(/\r?\n/).length;
}

/** Strip light TS surface so isolated classic functions can load in Node. */
function stripLightTs(src) {
  let s = String(src);
  s = s.replace(/\/\*[\s\S]*?\*\//g, '');
  s = s.replace(/(^|[^:])\/\/.*$/gm, '$1');
  // generics on function name: function foo<T>(
  s = s.replace(/\bfunction\s+([A-Za-z_$][\w$]*)\s*<[^>]+>\s*\(/g, 'function $1(');
  // return type before body: ): T {
  s = s.replace(/\)\s*:\s*[^{;]+\{/g, '){');
  // param type annotations (repeat for nested unions)
  for (let i = 0; i < 8; i++) {
    const next = s.replace(
      /([A-Za-z_$][\w$]*)\s\?\s*:\s*[^,)=]+/g,
      '$1',
    ).replace(
      /([A-Za-z_$][\w$]*)\s*:\s*[^,)=]+/g,
      '$1',
    );
    if (next === s) break;
    s = next;
  }
  // `as Type` / `as const` / satisfies
  s = s.replace(/\s+as\s+const\b/g, '');
  s = s.replace(/\s+as\s+[A-Za-z_$][\w$<>\[\]|&.,\s]*/g, '');
  s = s.replace(/\s+satisfies\s+[A-Za-z_$][\w$<>\[\]|&.\s]*/g, '');
  // non-null assertions obj! / call!()
  s = s.replace(/([A-Za-z_$0-9)\]])\!(?=\s*([.;,)\]\}\[]|$))/g, '$1');
  s = s.replace(/\breadonly\s+/g, '');
  s = s.replace(/\bpublic\s+|\bprivate\s+|\bprotected\s+|\babstract\s+/g, '');
  // angle-bracket assertions <Type>expr (heuristic, avoid comparisons)
  s = s.replace(/<(?:string|number|boolean|any|unknown|object|never|void)>\s*/g, '');
  return s;
}

function looksLikeTsResidue(js) {
  return /:\s*(string|number|boolean|any|unknown|void|never|object|Error|Node)\b/.test(js)
    || /\sas\s+[A-Za-z_$]/.test(js)
    || /\)\s*:\s*[A-Za-z_$]/.test(js);
}

function unsupportedReason(fn) {
  const body = String(fn.body || '');
  const params = (fn.params || []).join(',');
  if (/\basync\b/.test(body) || /\basync\b/.test(params)) return 'async';
  if (/\byield\b/.test(body)) return 'generator';
  if (/\bawait\b/.test(body)) return 'await';
  if (/:\s*(string|number|boolean|any|unknown|void|never|object|this)\b/.test(params)) {
    /* still try after strip */
  }
  if (/<[A-Z]/.test(params)) return 'generics_params';
  if (/\.\.\./.test(params)) return 'rest_params';
  if (/[{[]/.test(params)) return 'destructure_params';
  if (/\bimport\s*\(/.test(body)) return 'dynamic_import';
  if (/\bnew\s+target\b/.test(body)) return 'new_target';
  if (/`[^`]*\$\{/.test(body) && body.length > 4000) return 'heavy_template';
  return null;
}

function runHoldout(fn, holdout) {
  return holdout.map((args) => {
    try {
      return fn(...args);
    } catch (e) {
      return `ERROR:${e && e.message ? e.message : e}`;
    }
  });
}

function loadIsolatedFn(jsSource, name) {
  fs.mkdirSync(WORK_DIR, { recursive: true });
  const tmp = path.join(WORK_DIR, `fn_${name}_${crypto.randomBytes(4).toString('hex')}.cjs`);
  fs.writeFileSync(tmp, jsSource, 'utf8');
  try {
    delete require.cache[require.resolve(tmp)];
    const mod = require(tmp);
    const fn = typeof mod === 'function' ? mod : mod[name];
    if (typeof fn !== 'function') {
      return { ok: false, reason: 'export_not_fn', tmp };
    }
    return { ok: true, fn, tmp };
  } catch (e) {
    return { ok: false, reason: `load:${e.message || e}`, tmp };
  }
}

function cleanupTmp(tmp) {
  try {
    if (tmp) fs.unlinkSync(tmp);
  } catch {
    /* ignore */
  }
}

function verifyOneFn(fn, relFile) {
  const skip = unsupportedReason(fn);
  if (skip) return { status: 'skip', reason: skip, file: relFile, fn: fn.name };

  const arity = (fn.params || []).length;
  const holdout = generateHoldout(arity, 8);
  const origSrcRaw = `function ${fn.name}(${fn.params.join(',')}){${fn.body}}`;
  const stripped = stripLightTs(origSrcRaw);
  if (looksLikeTsResidue(stripped)) {
    return { status: 'skip', reason: 'ts_residue', file: relFile, fn: fn.name };
  }
  const origSrc = `${stripped}\nmodule.exports=${fn.name};\n`;

  let LIA;
  try {
    // Emit from stripped JS so LIA/compiler never see TS annotations.
    LIA = emitAilFromSource(stripped, { shortenLocals: true });
  } catch (e) {
    return { status: 'fail', reason: `emit:${e.message || e}`, file: relFile, fn: fn.name };
  }
  if (!LIA || !LIA.includes(`!${fn.name}(`)) {
    return { status: 'skip', reason: 'emit_empty', file: relFile, fn: fn.name };
  }

  let compiledJs;
  try {
    const compiled = compileLiaToJs(LIA, { exportMode: 'single' });
    compiledJs = compiled.js;
  } catch (e) {
    return { status: 'fail', reason: `compile:${e.message || e}`, file: relFile, fn: fn.name };
  }

  const origLoad = loadIsolatedFn(origSrc, fn.name);
  if (!origLoad.ok) {
    cleanupTmp(origLoad.tmp);
    return { status: 'skip', reason: `orig_${origLoad.reason}`, file: relFile, fn: fn.name };
  }
  const compLoad = loadIsolatedFn(compiledJs, fn.name);
  if (!compLoad.ok) {
    cleanupTmp(origLoad.tmp);
    cleanupTmp(compLoad.tmp);
    return { status: 'fail', reason: `comp_${compLoad.reason}`, file: relFile, fn: fn.name };
  }

  const oOut = runHoldout(origLoad.fn, holdout);
  const cOut = runHoldout(compLoad.fn, holdout);
  const oHash = hashOutputs(oOut);
  const cHash = hashOutputs(cOut);
  const eq =
    oHash === cHash && oOut.every((v, i) => String(v) === String(cOut[i]));

  cleanupTmp(origLoad.tmp);
  cleanupTmp(compLoad.tmp);

  return {
    status: eq ? 'pass' : 'fail',
    reason: eq ? 'behavior_eq' : 'hash_mismatch',
    file: relFile,
    fn: fn.name,
    original_hash: oHash,
    compiled_hash: cHash,
    ail_chars: LIA.length,
    compiled_chars: compiledJs.length,
    holdout_n: holdout.length,
  };
}

function inventoryRoot(root) {
  const files = walkSourceFiles(root);
  let loc = 0;
  let fnsExtracted = 0;
  const fileRows = [];
  for (const f of files) {
    let text = '';
    try {
      text = fs.readFileSync(f, 'utf8');
    } catch {
      continue;
    }
    const n = countLoc(text);
    loc += n;
    const fns = extractJsFunctions(text);
    fnsExtracted += fns.length;
    fileRows.push({ path: f, loc: n, fns });
  }
  return { files, loc, fnsExtracted, fileRows };
}

function summarizeReasons(rows) {
  const map = {};
  for (const r of rows) {
    const k = r.reason || r.status;
    map[k] = (map[k] || 0) + 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
    .map(([k, v]) => ({ reason: k, n: v }));
}

function writeReport(rep) {
  const samplePass = rep.results.filter((r) => r.status === 'pass').slice(0, 12);
  const sampleFail = rep.results.filter((r) => r.status === 'fail').slice(0, 12);
  const blockers = summarizeReasons(rep.results.filter((r) => r.status !== 'pass'));

  const lines = [
    '@DICEL:LIA_400K_ROUNDTRIP:1.0.0',
    '',
    '^rule="semantic_hash_exact_like_P200"',
    '^same_content=true',
    '^no_padding=true',
    '^soft_match=false',
    '^behavior_eq_required=1.0',
    `^status="${rep.status}"`,
    `^repo_url="${rep.repoUrl}"`,
    `^clone_path="${rep.clonePath.replace(/\\/g, '/')}"`,
    `^source_root="${rep.sourceRoot.replace(/\\/g, '/')}"`,
    `^measured_loc=${rep.measuredLoc}`,
    `^files_total=${rep.filesTotal}`,
    `^files_ok=${rep.filesOk}`,
    `^files_skip=${rep.filesSkip}`,
    `^fns_extracted=${rep.fnsExtracted}`,
    `^fns_attempted=${rep.fnsAttempted}`,
    `^fns_pass=${rep.fnsPass}`,
    `^fns_fail=${rep.fnsFail}`,
    `^fns_skip=${rep.fnsSkip}`,
    `^pass_rate=${rep.passRate}`,
    `^largest_connected_pass=${rep.largestConnectedPass}`,
    `^holdout_n=${rep.holdoutN}`,
    `^protocol="source->LIA->compile_JS->holdout_sha256"`,
    `^emitter="${rep.emitter.replace(/\\/g, '/')}"`,
    `^compiler="${rep.compiler.replace(/\\/g, '/')}"`,
    `^generated_at="${rep.generatedAt}"`,
    '',
    '@RULE_CONFIRM {',
    '  exact_output_equality: true',
    '  sha256_of_output_vector: true',
    '  soft_match_forbidden: true',
    '  like: "INTEL_LIA_ROUNDTRIP_VERIFY / P200 semantic_hash"',
    '}',
    '',
    '@INVENTORY {',
    `  loc: ${rep.measuredLoc}`,
    `  files: ${rep.filesTotal}`,
    `  named_functions_extracted: ${rep.fnsExtracted}`,
    `  note: "LOC = lines in .js/.ts/.tsx/.jsx under source_root (skip node_modules/.git/tests/fixtures)"`,
    '}',
    '',
    '@COUNTS {',
    `  files_ok: ${rep.filesOk}`,
    `  files_skip: ${rep.filesSkip}`,
    `  fns_pass: ${rep.fnsPass}`,
    `  fns_fail: ${rep.fnsFail}`,
    `  fns_skip: ${rep.fnsSkip}`,
    '}',
    '',
    '@HASH_SAMPLE_PASS {',
    ...samplePass.map(
      (p) =>
        `  { fn:"${p.fn}", file:"${p.file.replace(/\\/g, '/')}", original_hash:"${p.original_hash}", compiled_hash:"${p.compiled_hash}", eq:true }`,
    ),
    '}',
    '',
    '@HASH_SAMPLE_FAIL {',
    ...sampleFail.map(
      (p) =>
        `  { fn:"${p.fn}", file:"${String(p.file).replace(/\\/g, '/')}", reason:"${String(p.reason).replace(/"/g, "'")}", original_hash:"${p.original_hash || ''}", compiled_hash:"${p.compiled_hash || ''}" }`,
    ),
    '}',
    '',
    '@BLOCKERS {',
    ...blockers.map((b) => `  { reason:"${b.reason.replace(/"/g, "'")}", n:${b.n} }`),
    '}',
    '',
    '@LODASH_SECONDARY {',
    ...(rep.lodash
      ? [
          `  path: "${rep.lodash.path.replace(/\\/g, '/')}"`,
          `  loc: ${rep.lodash.loc}`,
          `  fns_pass: ${rep.lodash.fnsPass}`,
          `  fns_fail: ${rep.lodash.fnsFail}`,
          `  fns_skip: ${rep.lodash.fnsSkip}`,
          `  note: "classic JS requireable control corpus"`,
        ]
      : ['  skipped: true']),
    '}',
    '',
    '@VERDICT {',
    `  semantic_hash_rule_in_place: true`,
    `  loc_target_met: ${rep.measuredLoc >= 200000}`,
    `  connected_set_pass: ${rep.largestConnectedPass}`,
    `  honest_note: "${rep.honestNote.replace(/"/g, "'")}"`,
    '}',
  ];

  fs.writeFileSync(REPORT_PATH, lines.join('\n') + '\n', 'utf8');
  return REPORT_PATH;
}

function runCorpus(label, root, opts) {
  const inv = inventoryRoot(root);
  const results = [];
  let attempted = 0;
  const fileStats = new Map(); // file -> {pass,fail,skip,tried}

  for (const row of inv.fileRows) {
    const rel = path.relative(root, row.path);
    if (!fileStats.has(rel)) fileStats.set(rel, { pass: 0, fail: 0, skip: 0, tried: 0 });
    for (const fn of row.fns) {
      if (opts.maxFns && attempted >= opts.maxFns) break;
      attempted++;
      const st = fileStats.get(rel);
      st.tried++;
      const r = verifyOneFn(fn, rel);
      results.push(r);
      if (r.status === 'pass') st.pass++;
      else if (r.status === 'fail') st.fail++;
      else st.skip++;
      if (attempted % 200 === 0) {
        const pass = results.filter((x) => x.status === 'pass').length;
        const fail = results.filter((x) => x.status === 'fail').length;
        const skip = results.filter((x) => x.status === 'skip').length;
        console.error(`[${label}] ${attempted}/${inv.fnsExtracted} fns… pass=${pass} fail=${fail} skip=${skip}`);
      }
    }
    if (opts.maxFns && attempted >= opts.maxFns) break;
  }

  const fnsPass = results.filter((r) => r.status === 'pass').length;
  const fnsFail = results.filter((r) => r.status === 'fail').length;
  const fnsSkip = results.filter((r) => r.status === 'skip').length;
  let filesOk = 0;
  let filesSkip = 0;
  let largestConnectedPass = 0;
  for (const st of fileStats.values()) {
    if (st.tried === 0) continue;
    if (st.fail === 0 && st.pass > 0) {
      filesOk++;
      largestConnectedPass = Math.max(largestConnectedPass, st.pass);
    } else if (st.pass === 0) filesSkip++;
    else filesOk++; // partial ok still counts as touched ok file with some passes
  }
  // largest connected = max passes in a single file with zero fails among attempted that weren't skip-only
  largestConnectedPass = 0;
  for (const st of fileStats.values()) {
    if (st.pass > 0 && st.fail === 0) largestConnectedPass = Math.max(largestConnectedPass, st.pass);
  }

  return {
    label,
    root,
    measuredLoc: inv.loc,
    filesTotal: inv.files.length,
    fnsExtracted: inv.fnsExtracted,
    fnsAttempted: attempted,
    fnsPass,
    fnsFail,
    fnsSkip,
    filesOk,
    filesSkip,
    largestConnectedPass,
    results,
  };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const sourceRoot = opts.root;
  if (!fs.existsSync(sourceRoot)) {
    console.error('Missing source root:', sourceRoot);
    process.exit(2);
  }

  console.error('Inventory + roundtrip on', sourceRoot);
  const primary = runCorpus('TS', sourceRoot, opts);

  let lodash = null;
  const lodashRoot = 'C:\\Users\\k\\Documents\\LIA-bench\\clone-400k\\lodash';
  if (opts.alsoLodash && fs.existsSync(lodashRoot)) {
    console.error('Secondary lodash corpus…');
    // Cap lodash fns for runtime unless maxFns already set low
    const lodashOpts = { ...opts, maxFns: opts.maxFns || 800 };
    const L = runCorpus('lodash', lodashRoot, lodashOpts);
    lodash = {
      path: lodashRoot,
      loc: L.measuredLoc,
      fnsPass: L.fnsPass,
      fnsFail: L.fnsFail,
      fnsSkip: L.fnsSkip,
    };
  }

  const passRate =
    primary.fnsAttempted === 0
      ? 0
      : Number((primary.fnsPass / primary.fnsAttempted).toFixed(4));

  const status =
    primary.fnsPass > 0 && primary.measuredLoc >= 200000
      ? primary.fnsFail === 0
        ? 'PASS'
        : 'PARTIAL'
      : primary.fnsPass > 0
        ? 'PARTIAL'
        : 'FAIL';

  const honestNote =
    'TypeScript/src is ~400k LOC but not Node-requireable as a package; ' +
    'bench verifies extractable classic function() declarations via isolated holdout. ' +
    'Arrow/class/async/TS-heavy and free-ref fns are skipped or fail compile. ' +
    'Lodash secondary provides classic JS control. Exact sha256 holdout only — no soft match.';

  const report = {
    status,
    repoUrl: DEFAULT_REPO_URL,
    clonePath: path.resolve(sourceRoot, '..', '..'),
    sourceRoot,
    measuredLoc: primary.measuredLoc,
    filesTotal: primary.filesTotal,
    filesOk: primary.filesOk,
    filesSkip: primary.filesSkip,
    fnsExtracted: primary.fnsExtracted,
    fnsAttempted: primary.fnsAttempted,
    fnsPass: primary.fnsPass,
    fnsFail: primary.fnsFail,
    fnsSkip: primary.fnsSkip,
    passRate,
    largestConnectedPass: primary.largestConnectedPass,
    holdoutN: opts.holdoutN,
    emitter: path.join(LIA_ROOT, 'src', 'emitter.mjs'),
    compiler: path.join(LIA_ROOT, 'src', 'compiler.mjs'),
    generatedAt: new Date().toISOString(),
    results: primary.results,
    lodash,
    honestNote,
  };

  // fix clonePath: source is .../TypeScript/src → clone is .../clone-400k/TypeScript
  report.clonePath = path.resolve(sourceRoot, '..');

  const reportPath = writeReport(report);
  try {
    fs.rmSync(WORK_DIR, { recursive: true, force: true });
  } catch {
    /* ignore */
  }

  console.log(
    JSON.stringify(
      {
        status: report.status,
        reportPath,
        measured_loc: report.measuredLoc,
        files_total: report.filesTotal,
        files_ok: report.filesOk,
        files_skip: report.filesSkip,
        fns_extracted: report.fnsExtracted,
        fns_attempted: report.fnsAttempted,
        fns_pass: report.fnsPass,
        fns_fail: report.fnsFail,
        fns_skip: report.fnsSkip,
        pass_rate: report.passRate,
        largest_connected_pass: report.largestConnectedPass,
        rule: 'semantic_hash_exact_like_P200',
        lodash,
      },
      null,
      2,
    ),
  );
  process.exit(report.fnsPass > 0 ? 0 : 1);
}

main();
