#!/usr/bin/env node
/**
 * LIN autonomous mode: toolchains + improve + evolve + clone-lin until 100%.
 * Clone loop: original→hash→LIN→compile→hash; PARTIAL = retry SAME repo;
 * 100% = INTEL + gh clone-lin-<name> + cleanup + next. No wrap unless --repeat.
 * @FORBID{mutate_lia_nucleus}
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const INTEL = path.join(ROOT, 'INTEL_LIN_AUTONOMY_RUN.dicel');
const LAB = 'C:/Users/k/Documents/dicel-unified/INTEL_LIN_AUTONOMY_RUN.dicel';

function parseArgs(argv) {
  const o = {
    cycles: 1,
    cloneCycles: 0,
    skipClone: false,
    skipToolchains: false,
    repeat: false,
    maxFns: 12,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--cycles') o.cycles = Math.max(1, Number(argv[++i]) || 1);
    else if (a === '--clone-cycles') o.cloneCycles = Math.max(0, Number(argv[++i]) || 0);
    else if (a === '--skip-clone') o.skipClone = true;
    else if (a === '--skip-toolchains') o.skipToolchains = true;
    else if (a === '--repeat') o.repeat = true;
    else if (a === '--max-fns') o.maxFns = Math.max(1, Number(argv[++i]) || 12);
  }
  return o;
}

function run(script, args, timeoutMs) {
  const r = spawnSync(process.execPath, [path.join(ROOT, 'scripts', script), ...args], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: timeoutMs || 3_600_000,
    maxBuffer: 20 * 1024 * 1024,
  });
  return {
    status: r.status ?? 1,
    out: `${r.stdout || ''}${r.stderr || ''}`.slice(-8000),
  };
}

function parseJsonTail(out) {
  const i = out.lastIndexOf('\n{') >= 0 ? out.lastIndexOf('\n{') + 1 : out.lastIndexOf('{');
  if (i < 0) return { raw: out.slice(0, 400) };
  try {
    return JSON.parse(out.slice(i));
  } catch {
    return { raw: out.slice(-500) };
  }
}

function writeIntel(epoch) {
  const body = `@DICEL:LIN_AUTONOMY_RUN:1.1.0
^t="${epoch.t}"
^status="${epoch.status}"
^nucleus=untouched
^mode=evolve+improve+fix+clone_until_100+expose
^pipeline="original→hash→LIN→compile→hash→retry_until_100→clone-lin-gh"

@STAGES {
  toolchains: ${JSON.stringify(epoch.toolchains).slice(0, 500)}
  improve: ${JSON.stringify(epoch.improve).slice(0, 400)}
  evolve: ${JSON.stringify(epoch.evolve).slice(0, 400)}
  clone_lin: ${JSON.stringify(epoch.clone_lin).slice(0, 1200)}
}

@EXPOSE {
  intel_lin="${INTEL.replace(/\\\\/g, '/')}"
  year_star="INTEL_LIN_YEAR_STAR_QUEUE.dicel"
  ledger="storage/lia_ledger.dicel"
}

@FORBID { mutate_lia_nucleus }
`;
  fs.writeFileSync(INTEL, body, 'utf8');
  try {
    fs.writeFileSync(LAB, body, 'utf8');
  } catch { /* ignore */ }
}

function oneEpoch(args) {
  const t = new Date().toISOString();
  const toolchains = args.skipToolchains
    ? { status: 'SKIPPED' }
    : parseJsonTail(run('ensure_toolchains.mjs', [], 180_000).out);
  const improve = parseJsonTail(run('evolve_loop.mjs', ['improve'], 180_000).out);
  const evolve = parseJsonTail(run('evolve_loop.mjs', ['evolve'], 180_000).out);

  let clone_lin = { status: 'SKIPPED' };
  if (!args.skipClone) {
    const cargs = ['--max-fns', String(args.maxFns)];
    if (args.cloneCycles > 0) cargs.push('--cycles', String(args.cloneCycles));
    if (args.repeat) cargs.push('--repeat');
    const c = run('clone_lin_loop.mjs', cargs, 14_400_000);
    const tail = parseJsonTail(c.out);
    const published = Array.isArray(tail.reports)
      ? tail.reports.filter((r) => r.published && r.done)
      : [];
    const rateOk = tail.stop === 'queue_complete'
      || (published.length > 0 && tail.stop !== 'cycles_exhausted');
    const partialSmoke = args.cloneCycles === 1 && tail.stop === 'cycles_exhausted' && published.length === 0;
    clone_lin = {
      status: partialSmoke
        ? 'CLONE_PARTIAL_NOT_DONE'
        : (c.status === 0 && rateOk ? 'CLONE_UNTIL_100_OK' : 'CLONE_NOT_100'),
      exit: c.status,
      stop: tail.stop,
      repos_done: tail.repos_done,
      published,
      current: tail.current,
      suite_rates: Array.isArray(tail.reports) ? tail.reports.map((r) => r.suite_rate) : [],
    };
  }

  const cloneOk = args.skipClone
    || clone_lin.status === 'CLONE_UNTIL_100_OK'
    || clone_lin.stop === 'queue_complete';
  const improveOk = improve.status === 'IMPROVE_OK' || improve.raw;
  const epoch = {
    t,
    status: cloneOk ? 'AUTONOMY_EPOCH_OK' : 'AUTONOMY_STAY_UNTIL_100',
    toolchains: toolchains.present ? { present: toolchains.present } : toolchains,
    improve: improve.status || improve,
    evolve: evolve.status || evolve,
    clone_lin,
    improve_ok: !!improveOk,
  };
  writeIntel(epoch);
  return epoch;
}

const args = parseArgs(process.argv.slice(2));
const epochs = [];
for (let i = 0; i < args.cycles; i++) {
  const e = oneEpoch(args);
  epochs.push(e);
  console.log(JSON.stringify(e, null, 2));
  if (e.status === 'AUTONOMY_STAY_UNTIL_100') break;
}
const ok = epochs.some((e) => e.status === 'AUTONOMY_EPOCH_OK');
process.exit(ok ? 0 : 1);
