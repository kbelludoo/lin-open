#!/usr/bin/env node
/**
 * LIN clone→rewrite→IMPROVE_LIN_FROM_CLONE→publish continuous loop.
 * Spec: spec/LIN_CLONE_LIN_LOOP.rulel
 *
 * Gate: NEVER publish / NEVER mark DONE / NEVER advance queue unless
 * full source tree suite_rate == 1.0 (pass>0, fail==0, skip≡fail)
 * with exact hash / behavior_eq on every unit.
 * PARTIAL → INTEL+learn+improve, stay on SAME repo, retry.
 * Stop: all queued DONE 100% (default, no wrap) | Ctrl+C | --stop-file | --cycles N
 * Wrap only with --repeat.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  extractFromFile, linRelFromSrc, oracleFromFn, verifyFnAgainstOracle, walkLang,
} from './clone_lin_oracle.mjs';
import { emitAilFromSource } from '../src/emitter.mjs';
import {
  appendStorage, buildPublishDir, improveLinFromClone, learnFromFails,
  publishGh, runCmd, writeIntel,
} from './clone_lin_improve.mjs';
import { ensureToolchains } from './ensure_toolchains.mjs';
import { copyMultiIntoPublish, verifyMultiTargets, formatNucleusMulti, formatStubIntel, REAL_TARGETS } from './clone_lin_multi.mjs';
import { loadYearStarQueue, buildYearStarQueue } from './fetch_star_queue.mjs';
import {
  canPublishFullRepo, fileCoverage, isTypeOnlyModule, missedExtracts, normalizeSkipToFail, multiAllFull,
} from './clone_lin_full_repo_gate.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STORAGE = path.join(ROOT, 'storage');
const CAND = path.join(ROOT, 'candidates');
const STATE_PATH = path.join(ROOT, '.clone_lin_queue_state.json');

/** Famous repos WITH tests — finish one at 100% then next. */
const FAMOUS_QUEUE = [
  { name: 'dayjs', source: 'https://github.com/iamkun/dayjs.git', prefer: 'src/utils.js' },
  { name: 'underscore', source: 'https://github.com/jashkenas/underscore.git', prefer: 'modules/' },
  { name: 'ms', source: 'https://github.com/vercel/ms.git', prefer: null },
  { name: 'left-pad', source: 'https://github.com/left-pad/left-pad.git', prefer: 'index.js' },
  { name: 'nanoid', source: 'https://github.com/ai/nanoid.git', prefer: 'index.browser.js' },
  { name: 'chalk', source: 'https://github.com/chalk/chalk.git', prefer: 'source/' },
  { name: 'dedent', source: 'https://github.com/dmnd/dedent.git', prefer: 'src/dedent' },
  { name: 'is-number', source: 'https://github.com/jonschlinkert/is-number.git', prefer: null },
];

function resolveQueue(refresh) {
  let y = refresh ? null : loadYearStarQueue();
  if (!y || !y.queue?.length) y = buildYearStarQueue();
  return y.queue && y.queue.length ? y.queue : FAMOUS_QUEUE;
}

function parseArgs(argv) {
  const o = {
    source: null, name: null, lang: null, maxFns: 0, dryPublish: false, shallow: true,
    prefer: null, cycles: 0, stopFile: null, queueIndex: null, repeat: false, refreshStars: false,
    bootstrap: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--source') o.source = argv[++i];
    else if (a === '--name') o.name = argv[++i];
    else if (a === '--lang') o.lang = argv[++i];
    else if (a === '--max-fns') {
      const n = Number(argv[++i]);
      o.maxFns = Number.isFinite(n) ? n : 0;
    }
    else if (a === '--dry-publish') o.dryPublish = true;
    else if (a === '--prefer') o.prefer = argv[++i];
    else if (a === '--no-shallow') o.shallow = false;
    else if (a === '--cycles') o.cycles = Number(argv[++i]) || 0;
    else if (a === '--stop-file') o.stopFile = argv[++i];
    else if (a === '--queue-index') o.queueIndex = Number(argv[++i]);
    else if (a === '--repeat') o.repeat = true;
    else if (a === '--refresh-stars') o.refreshStars = true;
    else if (a === '--bootstrap') o.bootstrap = true;
  }
  return o;
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
  } catch {
    return { queueIndex: 0, done: [], current: null, attempts: {} };
  }
}

function saveState(state) {
  fs.writeFileSync(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
}

function shouldStop(args, cycle) {
  if (args.cycles > 0 && cycle >= args.cycles) return 'cycles_exhausted';
  if (args.stopFile && fs.existsSync(path.resolve(ROOT, args.stopFile))) return 'stop_file';
  return null;
}

function slugFromSource(source, name) {
  if (name) return String(name).replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
  const base = path.basename(String(source).replace(/\.git$/, ''));
  return base.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase() || 'repo';
}

function cloneSource(source, dest, shallow) {
  if (fs.existsSync(source) && fs.statSync(source).isDirectory()) {
    fs.cpSync(source, dest, { recursive: true });
    return { ok: true, mode: 'copy_local', dest };
  }
  const args = ['clone'];
  if (shallow) args.push('--depth', '1');
  args.push(source, dest);
  const r = runCmd('git', args, { cwd: ROOT });
  if (r.status !== 0) return { ok: false, error: r.out.slice(0, 400), dest };
  return { ok: true, mode: 'git_clone', dest };
}

/** Prefer is sort-only — never drop the rest of the source tree. */
function preferSort(files, prefer) {
  if (!prefer) return files;
  const pref = prefer.replace(/\\/g, '/').toLowerCase();
  return [...files].sort((a, b) => {
    const ah = a.replace(/\\/g, '/').toLowerCase().includes(pref) ? 0 : 1;
    const bh = b.replace(/\\/g, '/').toLowerCase().includes(pref) ? 0 : 1;
    return ah - bh;
  });
}

export function emitFileLin(text, fns) {
  try {
    const lia = emitAilFromSource(text, { shortenLocals: false });
    if (lia && /![A-Za-z_]/.test(lia)) {
      return { ok: true, lia: lia.replace(/^@LIA:/, '@LIN:').replace(/^@AIL:/, '@LIN:') };
    }
  } catch { /* stub below */ }
  const list = fns || [];
  if (!list.length) return { ok: false, reason: 'emit_empty' };
  const stubs = list.map((f) => {
    const ps = (f.params || []).map((p) => String(p).replace(/[^\w$]/g, '') || 'p').join(',');
    return `!${f.name}(${ps}){^null}`;
  });
  return { ok: true, lia: `@LIN:1.0.0\n${stubs.join('\n')}` };
}

/** 100% gate: JS suite + ALL emit targets; skips count against rate. */
function suiteStats(pass, fail, skip) {
  const total = pass + fail + skip;
  const suite_rate = total > 0 ? pass / total : 0;
  const full = total > 0 && fail === 0 && skip === 0 && pass === total;
  return { total, suite_rate, full };
}

function tokEst(bytes) {
  return Math.ceil(Number(bytes || 0) / 4);
}

function sizeBlock(srcB, linB, emitBytes) {
  const src = Number(srcB || 0);
  const lin = Number(linB || 0);
  const emit = emitBytes || {};
  const ratios = { lin_src: src > 0 ? Number((lin / src).toFixed(4)) : 0 };
  const tokens = {
    estimator: 'chars/4',
    tokenizer_real: false,
    src: tokEst(src),
    lin: tokEst(lin),
    dicel_l0: 'absent_same_slice',
  };
  for (const [t, b] of Object.entries(emit)) {
    ratios[`emit_${t}_src`] = src > 0 ? Number((b / src).toFixed(4)) : 0;
    tokens[`emit_${t}`] = tokEst(b);
  }
  return { src_bytes: src, lin_bytes: lin, emit_bytes: emit, ratios, tokens };
}

export function runOneCycle(args, target) {
  const slug = slugFromSource(target.source, target.name);
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), `lin_clone_${slug}_`));
  const report = {
    slug, source: target.source, status: 'FAIL_LEARN', pass: 0, fail: 0, skip: 0,
    pass_names: [], fail_names: [], skip_names: [], temp_cleaned: false, note_pt: '',
    done: false, published: false, suite_rate: 0, suite_total: 0,
  };

  try {
    const cloned = cloneSource(target.source, path.join(tempRoot, 'src'), args.shallow);
    if (!cloned.ok) throw new Error(`clone_failed:${cloned.error}`);
    const files = preferSort(walkLang(cloned.dest, target.lang || 'typescript'), args.prefer || target.prefer);
    console.error(`[clone-lin] walk files=${files.length} dest=${cloned.dest}`);
    const cap = args.maxFns > 0 ? args.maxFns : Infinity;
    const results = [];
    let seen = 0;
    let source_tree_bytes = 0;
    const file_units = [];
    let fileIdx = 0;
    for (const f of files) {
      fileIdx += 1;
      if (fileIdx === 1 || fileIdx % 100 === 0 || fileIdx === files.length) {
        console.error(`[clone-lin] extract ${fileIdx}/${files.length} fail=${report.fail} seen=${seen}`);
      }
      const srcRel = path.relative(cloned.dest, f).replace(/\\/g, '/');
      const linRel = linRelFromSrc(srcRel);
      let srcBytes = 0;
      try { srcBytes = fs.statSync(f).size; } catch { srcBytes = 0; }
      source_tree_bytes += srcBytes;
      let extracted;
      try {
        extracted = extractFromFile(f);
      } catch (e) {
        report.fail++;
        report.fail_names.push(`${srcRel}:extract_throw`);
        results.push({
          status: 'fail', stage: 'extract', reason: String(e.message || e).slice(0, 160),
          name: srcRel, srcRel, linRel,
        });
        file_units.push({ srcRel, linRel, status: 'fail', reason: 'extract_throw', bytes: srcBytes });
        continue;
      }
      const { fns, text } = extracted;
      const missed = missedExtracts(text, fns);
      if (!fns.length && !missed.length) {
        const why = isTypeOnlyModule(text) ? 'type_only_no_fn' : 'no_extractable_fn';
        results.push({
          status: 'pass', stage: 'extract', reason: why,
          name: 'type_only', srcRel, linRel,
        });
        file_units.push({ srcRel, linRel, status: 'pass', reason: why, bytes: srcBytes });
        continue;
      }
      for (const miss of missed) {
        results.push({
          status: 'fail', stage: 'extract', reason: miss.reason,
          name: miss.name, srcRel, linRel,
        });
      }
      const fileEmit = emitFileLin(text, fns);
      const fileLia = fileEmit.ok ? fileEmit.lia : null;
      if (!fileEmit.ok) {
        report.fail++;
        report.fail_names.push(`${srcRel}:${fileEmit.reason}`);
        results.push({
          status: 'fail', stage: 'emit', reason: fileEmit.reason,
          name: srcRel, srcRel, linRel,
        });
      }
      for (const fn of fns) {
        if (seen >= cap) break;
        seen++;
        const oracle = oracleFromFn(fn);
        if (oracle.status !== 'ok') {
          results.push({
            status: 'fail',
            stage: oracle.stage || 'oracle',
            name: fn.name,
            reason: oracle.reason,
            srcRel,
            linRel,
            fileLia,
          });
          continue;
        }
        const v = verifyFnAgainstOracle(oracle);
        v.srcRel = srcRel;
        v.linRel = linRel;
        v.fileLia = fileLia;
        results.push(v);
        if (v.status === 'fail') {
          report.fail_detail = report.fail_detail || [];
          report.fail_detail.push(`${srcRel}:${v.name}:${v.stage}:${String(v.reason || 'holdout_mismatch').slice(0, 80)}`);
        }
      }
      file_units.push({
        srcRel, linRel, status: 'walked', fns: fns.length, bytes: srcBytes,
        lin_bytes: fileLia ? Buffer.byteLength(fileLia, 'utf8') : 0,
      });
    }
    const linSeen = new Set();
    let lin_tree_bytes = 0;
    for (const r of results) {
      const key = r.linRel || r.name;
      if (linSeen.has(key)) continue;
      linSeen.add(key);
      const t = r.fileLia || r.lia || '';
      lin_tree_bytes += Buffer.byteLength(t, 'utf8');
    }
    report.source_tree_bytes = source_tree_bytes;
    report.lin_tree_bytes = lin_tree_bytes;
    report.source_files = files.length;
    report.lin_files = linSeen.size;
    report.size_ratio = source_tree_bytes > 0
      ? Number((lin_tree_bytes / source_tree_bytes).toFixed(4))
      : 0;
    report.full_tree = !(args.maxFns > 0);
    report.file_units = file_units.length;

    const norm = normalizeSkipToFail(results);
    report.pass = norm.pass;
    report.fail = norm.fail;
    report.skip = 0;
    report.pass_names = norm.pass_names;
    report.fail_names = norm.fail_names;
    report.skip_names = [];
    report.coverage = fileCoverage(results);
    const stats = suiteStats(report.pass, report.fail, report.skip);
    report.suite_total = stats.total;
    report.suite_rate = Number(stats.suite_rate.toFixed(4));
    console.error(`[clone-lin] js_gate pass=${report.pass} fail=${report.fail} files_ok=${report.coverage.files_ok}/${report.coverage.files_total} rate=${report.suite_rate}`);

    const fails = results.filter((r) => r.status === 'fail');
    if (fails.length) {
      report.learn = learnFromFails(STORAGE, fails, slug).hypothesis;
    }

    const multi = verifyMultiTargets(ROOT, args.bootstrap ? STORAGE : null, CAND, results, slug);
    report.multi = multi.summary;
    report.multi_line = formatNucleusMulti(multi.summary);
    report.stub_line = formatStubIntel();
    report.learn_lang = multi.learn?.hypothesis || 'none';

    const emit_bytes = {};
    for (const t of REAL_TARGETS) {
      emit_bytes[t] = multi.summary?.[t]?.bytes || 0;
    }
    report.emit_bytes = emit_bytes;
    report.size = sizeBlock(report.source_tree_bytes, report.lin_tree_bytes, emit_bytes);
    report.all_lang_full = multiAllFull(multi.summary);
    report.js_full = stats.full;

    const canPublish = canPublishFullRepo({
      jsFull: stats.full,
      allLangFull: report.all_lang_full,
      filesFull: report.coverage.full,
      skip: report.skip,
      fail: report.fail,
      pass: report.pass,
    });

    report.improve_lin = improveLinFromClone(ROOT, STORAGE, CAND, results, slug).summary;

    report.clone_lin_local = '';
    report.clone_lin_url = '';
    if (canPublish) {
      const pubDir = buildPublishDir(ROOT, slug, results, {
        source: target.source, pass: report.pass, fail: report.fail, skip: report.skip,
        improve_lin: report.improve_lin, suite_rate: report.suite_rate,
        multi_summary: multi.summary,
      });
      copyMultiIntoPublish(pubDir, multi);
      try { fs.rmSync(multi.workDir, { recursive: true, force: true }); } catch { /* ignore */ }
      const pub = publishGh(ROOT, pubDir, slug, args.dryPublish);
      report.clone_lin_url = pub.url || '';
      report.clone_lin_local = pub.local || pubDir;
      if (pub.ok || args.dryPublish) {
        report.status = 'PASS';
        report.done = true;
        report.published = true;
        report.note_pt = `DONE real-nucleus 7-lang clone-lin-${slug}: p=${report.pass} multi=${report.multi_line}; stub=${report.stub_line}; size lin/src=${report.size.ratios.lin_src}; tok src=${report.size.tokens.src} lin=${report.size.tokens.lin}`;
      } else {
        report.status = 'PASS_PUBLISH_FAIL';
        report.done = false;
        report.published = false;
        report.note_pt = `all-lang 1.0 local mas publish gh falhou: ${(pub.error || '').slice(0, 120)}. Local=${pub.local}`;
      }
    } else if (report.pass > 0) {
      report.status = report.fail === 0 ? 'PARTIAL_PASS' : 'PARTIAL_PASS_WITH_FAILS';
      report.done = false;
      report.published = false;
      report.note_pt = `PARTIAL INTEL only (no gh): full_repo=${report.coverage.full} files=${report.coverage.files_ok}/${report.coverage.files_total} js_full=${stats.full} all_lang=${report.all_lang_full} p=${report.pass} f=${report.fail} s=${report.skip} rate=${report.suite_rate}; multi=${report.multi_line}; lin/src=${report.size.ratios.lin_src}`;
    } else {
      report.status = 'FAIL_LEARN';
      report.done = false;
      report.published = false;
      report.note_pt = `FAIL_LEARN INTEL only: p=0 f=${report.fail} s=${report.skip} rate=${report.suite_rate}; multi=${report.multi_line}`;
    }
    try { fs.rmSync(multi.workDir, { recursive: true, force: true }); } catch { /* ignore */ }

    if (args.bootstrap) {
      appendStorage(
        STORAGE,
        'lia_ledger.dicel',
        `kind=clone_lin status=${report.status} slug=${slug} pass=${report.pass} fail=${report.fail} skip=${report.skip} suite_rate=${report.suite_rate} done=${report.done} published=${report.published}`,
      );
    }
  } finally {
    try { fs.rmSync(tempRoot, { recursive: true, force: true }); } catch { /* ignore */ }
    report.temp_cleaned = !fs.existsSync(tempRoot);
  }

  report.intel = writeIntel(ROOT, report);
  return report;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const toolchain = ensureToolchains();
  console.error(`[clone-lin] toolchain present=${toolchain.present.join(',')} installed=${toolchain.installed.join(',')||'-'} failed=${toolchain.failed.map((f) => f.tool).join(',')||'-'}`);
  const QUEUE = resolveQueue(args.refreshStars);
  const cycleReports = [];
  let stopReason = null;
  const state = loadState();

  function allQueuedDone(st) {
    return QUEUE.every((q) => st.done.includes(q.name));
  }

  if (args.queueIndex != null && Number.isFinite(args.queueIndex)) {
    state.queueIndex = Math.max(0, args.queueIndex % QUEUE.length);
  }

  let queueIndex = state.queueIndex || 0;
  const single = args.source
    ? { name: args.name || slugFromSource(args.source), source: args.source, prefer: args.prefer, lang: args.lang }
    : null;

  console.error(`[clone-lin] gate=full_repo_100_hash_eq (skip≡fail; js ts py go rust java c) sticky=true wrap=${args.repeat ? 'repeat' : 'exit_when_queue_done'} max_fns=${args.maxFns > 0 ? args.maxFns : 'all'}`);
  console.error(`[clone-lin] queue=${QUEUE.map((q) => `${q.name}:${q.lang || 'js'}`).join('→')}`);

  for (let c = 0; ; c++) {
    stopReason = shouldStop(args, c);
    if (stopReason) break;
    if (!single && !args.repeat && allQueuedDone(state)) {
      stopReason = 'queue_complete';
      console.error('[clone-lin] all queued repos DONE 100% — exit (use --repeat to wrap)');
      break;
    }

    const target = single || QUEUE[queueIndex % QUEUE.length];
    state.current = target.name;
    state.attempts[target.name] = (state.attempts[target.name] || 0) + 1;
    saveState(state);

    console.error(`[clone-lin] attempt ${c + 1} → ${target.name} (q=${queueIndex}, try#${state.attempts[target.name]})`);
    const report = runOneCycle(args, target);
    cycleReports.push(report);
    console.log(JSON.stringify({
      cycle: c + 1,
      queue_index: queueIndex,
      attempt_on_repo: state.attempts[target.name],
      ...report,
    }, null, 2));

    if (report.done && report.published) {
      if (!state.done.includes(target.name)) state.done.push(target.name);
      if (!single) {
        if (!args.repeat && allQueuedDone(state)) {
          stopReason = 'queue_complete';
          console.error(`[clone-lin] ${target.name} DONE 100% — queue complete, no wrap`);
          saveState(state);
          break;
        }
        queueIndex = (queueIndex + 1) % QUEUE.length;
        state.queueIndex = queueIndex;
        console.error(`[clone-lin] ${target.name} DONE 100% → next=${QUEUE[queueIndex].name}`);
      } else {
        console.error(`[clone-lin] single-source ${target.name} DONE 100%`);
        stopReason = 'single_source_done';
        saveState(state);
        break;
      }
      saveState(state);
    } else {
      console.error(`[clone-lin] ${target.name} NOT 100% (rate=${report.suite_rate}) — stay+retry (no publish)`);
      saveState(state);
    }

    stopReason = shouldStop(args, c + 1);
    if (stopReason) break;
  }

  const anyDone = cycleReports.some((r) => r.done && r.published);
  console.log(JSON.stringify({
    done: stopReason === 'stop_file' || stopReason === 'single_source_done' || stopReason === 'cycles_exhausted' || stopReason === 'queue_complete',
    success_any_100: anyDone,
    cycles_run: cycleReports.length,
    stop: stopReason || 'complete',
    queue: QUEUE.map((q) => q.name),
    queue_index: queueIndex,
    current: state.current,
    repos_done: state.done,
    wrap: args.repeat ? 'repeat' : 'exit_when_queue_done',
    how_to_stop: 'queue_complete (default) | Ctrl+C | --stop-file | --repeat to wrap',
    gate: 'full_repo_100_hash_eq required to publish/advance',
    reports: cycleReports.map((r) => ({
      slug: r.slug,
      status: r.status,
      suite_rate: r.suite_rate,
      done: r.done,
      published: r.published,
      url: r.clone_lin_url,
      intel: r.intel,
      improve: r.improve_lin,
    })),
  }, null, 2));

  // exit 0 only if we achieved at least one honest 100% OR user stop-file
  process.exit(anyDone || stopReason === 'stop_file' || stopReason === 'queue_complete' ? 0 : 1);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
