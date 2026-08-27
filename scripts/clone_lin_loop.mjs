#!/usr/bin/env node
/**
 * LIN clone→compile gate (v2 host).
 * Spec: spec/LIN_CLONE_LIN_LOOP.rulel
 *
 * Restores the scripts/clone_lin_loop.mjs entrypoint removed during the v2
 * promotion (archived under _legacy_v1/). Uses the in-memory compiler against
 * local clones_lin/ (and optional JS fixture queues) so autonomy / clone_lia
 * aliases work again without resurrecting the v1 regex emitter.
 *
 * Gate: suite_rate == 1.0 (pass>0, fail==0) before marking DONE.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from '../src/compiler.mjs';
import { ensureToolchains } from './ensure_toolchains.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CLONES = path.join(ROOT, 'clones_lin');

function parseArgs(argv) {
  const o = {
    cycles: 0,
    maxFns: 0,
    repeat: false,
    name: null,
    dryPublish: false,
    stopFile: null,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--cycles') o.cycles = Number(argv[++i]) || 0;
    else if (a === '--max-fns') o.maxFns = Number(argv[++i]) || 0;
    else if (a === '--repeat') o.repeat = true;
    else if (a === '--name') o.name = argv[++i];
    else if (a === '--dry-publish') o.dryPublish = true;
    else if (a === '--stop-file') o.stopFile = argv[++i];
  }
  return o;
}

function listRepos() {
  if (!fs.existsSync(CLONES)) return [];
  return fs.readdirSync(CLONES, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort();
}

function walkLin(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walkLin(p));
    else if (e.isFile() && e.name.endsWith('.lin')) out.push(p);
  }
  return out;
}

function compileRepo(name, maxFns) {
  const dir = path.join(CLONES, name);
  if (!fs.existsSync(dir)) {
    return { name, pass: 0, fail: 0, skip: 0, suite_rate: 0, fail_names: [], status: 'MISSING' };
  }
  let files = walkLin(dir);
  if (maxFns > 0) files = files.slice(0, maxFns);
  const pass_names = [];
  const fail_names = [];
  for (const f of files) {
    const rel = path.relative(dir, f).replace(/\\/g, '/');
    try {
      compile(fs.readFileSync(f, 'utf8'), { target: 'js' });
      pass_names.push(rel);
    } catch (e) {
      fail_names.push(`${rel}:${String(e.message || e).slice(0, 120)}`);
    }
  }
  const pass = pass_names.length;
  const fail = fail_names.length;
  const total = pass + fail;
  const suite_rate = total ? pass / total : 0;
  const done = total > 0 && fail === 0;
  return {
    name,
    pass,
    fail,
    skip: 0,
    suite_rate: Number(suite_rate.toFixed(4)),
    pass_names,
    fail_names,
    done,
    published: false,
    status: done ? 'PASS' : (pass ? 'PARTIAL_PASS_WITH_FAILS' : 'FAIL'),
  };
}

function writeIntel(report) {
  const out = path.join(ROOT, `INTEL_CLONE_LIN_${report.name}.rulel`);
  const body = `@RULEL:INTEL_CLONE_LIN:1.3.0
^slug="${report.name}"
^lang="LIN"
^status="${report.status}"
^done=${report.done}
^published=${report.published}
^suite_rate=${report.suite_rate}
^suite_total=${report.pass + report.fail}
^pass=${report.pass} ^fail=${report.fail} ^skip=0
^publish_gate="suite_rate==1.0_JS"
^host="scripts/clone_lin_loop.mjs v2-compile-gate"

@COMPARISON {
  pass_names: ${JSON.stringify(report.pass_names.slice(0, 40))}
  fail_names: ${JSON.stringify(report.fail_names.slice(0, 40))}
}

@NOTE_PT {
  ${report.done ? 'DONE' : 'PARTIAL'} clone-lin-${report.name}: p=${report.pass} f=${report.fail} suite_rate=${report.suite_rate}
}
`;
  fs.writeFileSync(out, body, 'utf8');
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  try { ensureToolchains(); } catch { /* best-effort */ }

  let repos = listRepos();
  if (args.name) repos = repos.filter((n) => n === args.name);
  if (!repos.length) {
    const empty = { stop: 'queue_empty', repos_done: [], reports: [], suiteRate: 0 };
    console.log(JSON.stringify(empty, null, 2));
    process.exit(1);
  }

  const reports = [];
  let cycles = 0;
  const maxCycles = args.cycles > 0 ? args.cycles : 1;

  do {
    cycles += 1;
    if (args.stopFile && fs.existsSync(args.stopFile)) break;
    for (const name of repos) {
      const r = compileRepo(name, args.maxFns);
      writeIntel(r);
      reports.push(r);
    }
    if (!args.repeat) break;
  } while (cycles < maxCycles);

  const done = reports.filter((r) => r.done).map((r) => r.name);
  const allDone = reports.length > 0 && reports.every((r) => r.done);
  const out = {
    stop: allDone ? 'queue_complete' : (args.cycles > 0 ? 'cycles_exhausted' : 'partial'),
    cycles,
    repos_done: done,
    current: reports.find((r) => !r.done)?.name || null,
    reports: reports.map((r) => ({
      name: r.name,
      suite_rate: r.suite_rate,
      pass: r.pass,
      fail: r.fail,
      done: r.done,
      published: r.published,
      status: r.status,
      fail_names: r.fail_names.slice(0, 20),
    })),
    suiteRate: reports.length
      ? Number((reports.reduce((a, r) => a + r.suite_rate, 0) / reports.length).toFixed(4))
      : 0,
  };
  console.log(JSON.stringify(out, null, 2));
  process.exit(allDone ? 0 : 3);
}

main();
