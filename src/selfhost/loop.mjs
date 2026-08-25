import fs from 'node:fs';
import path from 'node:path';
import { extractJsFunctions } from './extract.mjs';
import { buildOracle, verifyAgainstOracle } from './oracle.mjs';
import { cloneRepo } from './clone.mjs';
import { emitLinFromJs } from '../emit_from_js.mjs';
import { compile } from '../compiler.mjs';
import { runInMemory } from '../vm.mjs';

const REPAIRS = [
  {
    id: 'R_top_level_const_fn',
    test: (src) => /(?:^|\n)\s*(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?function\b/.test(src),
    apply: (src) => src.replace(/(?:^|\n)(\s*)(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(async\s+)?function\b\s*\*?\s*(?:[A-Za-z_$][\w$]*)?\s*/g, (_m, ws, name, as) => `${ws}${as ? 'async ' : ''}function ${name} `),
  },
  {
    id: 'R_strip_export_keywords',
    test: (src) => /^\s*export\s+/m.test(src),
    apply: (src) => src.replace(/^\s*export\s+\{[^}]*\}\s*;?\s*$/gm, '').replace(/^\s*export\s+/gm, ''),
  },
  {
    id: 'R_strip_imports',
    test: (src) => /^\s*import\s/m.test(src),
    apply: (src) => src.replace(/^\s*import\s[^;]+;\s*$/gm, ''),
  },
];

export function improveSource(sourceText) {
  const applied = [];
  let out = String(sourceText || '');
  for (const repair of REPAIRS) {
    if (repair.test(out)) {
      const next = repair.apply(out);
      if (next !== out) {
        applied.push(repair.id);
        out = next;
      }
    }
  }
  return { source: out, applied };
}

export function learnFromFails(report) {
  const lessons = [];
  for (const unit of report.units) {
    if (unit.status === 'EMIT_FAIL' && /top-level token "module"/.test(unit.detail || '')) {
      lessons.push({ unit: unit.name, lesson: 'module_exports_statement', action: 'skip_statement' });
    } else if (unit.status === 'BEHAVIOR_DIFF' && /got=undefined/.test(unit.detail || '')) {
      lessons.push({ unit: unit.name, lesson: 'missing_return', action: 'check_implicit_return' });
    }
  }
  return lessons;
}

export function runCloneLoop(opts = {}) {
  const queue = opts.queue || [];
  const state = {
    startedAt: new Date().toISOString(),
    cycles: 0,
    maxCycles: opts.cycles || 0,
    repos: [],
    done: [],
    partial: [],
  };

  for (;;) {
    const pending = queue.filter((r) => !state.done.includes(r.name));
    if (!pending.length) break;
    if (state.maxCycles && state.cycles >= state.maxCycles) break;
    if (opts.stopFile && fs.existsSync(opts.stopFile)) break;

    const repo = pending[0];
    state.cycles++;

    let report;
    try {
      report = cloneRepo(repo.source, repo.name, { maxFns: opts.maxFns || 0 });
    } catch (e) {
      state.partial.push({ repo: repo.name, error: e.message.slice(0, 160) });
      state.done.push(repo.name);
      continue;
    }

    if (report.complete) {
      if (!opts.dryPublish && opts.publishDir) {
        publishRepo(report, opts.publishDir);
      }
      state.done.push(repo.name);
      state.repos.push(summarize(report));
    } else {
      learnFromFails(report);
      const improved = improveSource(repo.source);
      const retry = cloneRepo(improved.source, repo.name, { maxFns: opts.maxFns || 0 });
      if (retry.complete) {
        if (!opts.dryPublish && opts.publishDir) publishRepo(retry, opts.publishDir);
        state.done.push(repo.name);
        state.repos.push({ ...summarize(retry), improvedBy: improved.applied });
      } else {
        state.partial.push({ repo: repo.name, suiteRate: retry.suiteRate, fails: retry.units.filter((u) => !['PASS', 'SKIP'].includes(u.status)).map((u) => `${u.name}:${u.status}`) });
        state.done.push(repo.name);
      }
    }
  }

  state.finishedAt = new Date().toISOString();
  state.suiteRate = computeSuiteRate(state);
  return state;
}

function summarize(report) {
  return {
    repo: report.repo,
    pass: report.pass,
    fail: report.fail,
    skip: report.skip,
    suiteRate: report.suiteRate,
    outputsHash: report.outputsHash,
  };
}

function computeSuiteRate(state) {
  let pass = 0;
  let total = 0;
  for (const r of state.repos) {
    pass += r.pass;
    total += r.pass + r.fail;
  }
  return total ? pass / total : 0;
}

export function publishRepo(report, dir) {
  const target = path.join(dir, 'lin');
  fs.mkdirSync(target, { recursive: true });
  if (report.mode === 'file' && report.fileLin) {
    fs.writeFileSync(path.join(target, `${sanitizeFile(report.repo)}.lin`), report.fileLin + '\n', 'utf8');
  } else {
    for (const unit of report.units) {
      if (unit.status !== 'PASS' || !unit.cloneLin) continue;
      const file = path.join(target, `${sanitizeFile(unit.name)}.lin`);
      fs.writeFileSync(file, unit.cloneLin + '\n', 'utf8');
    }
  }
  fs.writeFileSync(path.join(dir, `report-${sanitizeFile(report.repo)}.json`), JSON.stringify(summarize(report), null, 2), 'utf8');
}

function sanitizeFile(name) {
  return String(name).replace(/[^A-Za-z0-9_-]/g, '_');
}

export function autonomyStatus(statePath) {
  try {
    return JSON.parse(fs.readFileSync(statePath, 'utf8'));
  } catch {
    return { exists: false, suiteRate: 0, repos: [], done: [], partial: [] };
  }
}
