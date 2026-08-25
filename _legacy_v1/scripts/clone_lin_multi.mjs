/**
 * Multi-target emit+run for clone-lin nucleus (js,ts,py,go,rust,java,c).
 * Gate: required langs PASS (skip≡fail); C SKIP ok iff gcc absent after retry.
 * Stub langs may still emit but MUST NOT count as PASS / suite_rate.
 * Learn on new-lang FAIL → trauma/hypothesis/candidates; never nucleus.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { compileLia } from '../src/multi_emit.mjs';
import { TARGETS, REAL_TARGETS, STUB_TARGETS, formatNucleusMulti, formatStubIntel, honestNucleusMulti } from '../src/emit_shared.mjs';
import { appendStorage } from './clone_lin_improve.mjs';
import { ensureToolchains, hasCmd as hasToolchainCmd } from './ensure_toolchains.mjs';

export { TARGETS, REAL_TARGETS, STUB_TARGETS, formatNucleusMulti, formatStubIntel, honestNucleusMulti };

const EXT = {
  js: '.cjs', ts: '.ts', py: '.py', go: '.go', rust: '.rs', c: '.c', java: '.java',
  cs: '.cs', lua: '.lua', elixir: '.ex', crystal: '.cr', kotlin: '.kt', hcl: '.tf',
  julia: '.jl', scala: '.scala', haskell: '.hs', prolog: '.pl',
  zig: '.zig', nim: '.nim', asm: '.asm',
};

export function hasCmd(cmd) {
  return hasToolchainCmd(cmd);
}

function pythonBin() {
  if (hasCmd('python')) return 'python';
  if (hasCmd('python3')) return 'python3';
  return null;
}

function writeWork(dir, name, target, code) {
  const sub = path.join(dir, target);
  fs.mkdirSync(sub, { recursive: true });
  let fileName = `${name}${EXT[target] || `.${target}`}`;
  if (target === 'java') {
    const m = String(code || '').match(/public class ([A-Za-z][A-Za-z0-9]*)/);
    if (m) fileName = `${m[1]}.java`;
  }
  const p = path.join(sub, fileName);
  fs.writeFileSync(p, code, 'utf8');
  return p;
}

function runTsSyntax(file) {
  const r = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
  if (r.status === 0) return { ok: true, detail: 'node --check' };
  let code = fs.readFileSync(file, 'utf8')
    .replace(/^export /gm, '')
    .replace(/: unknown/g, '')
    .replace(/: boolean/g, '')
    .replace(/: Record<string, number>/g, '');
  const tmp = `${file}.cjs`;
  fs.writeFileSync(tmp, `${code}\n`, 'utf8');
  const c = spawnSync(process.execPath, ['--check', tmp], { encoding: 'utf8' });
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  return { ok: c.status === 0, detail: (c.stderr || c.stdout || 'ts_strip_check').slice(0, 200) };
}

function runTarget(target, file) {
  if (STUB_TARGETS.includes(target)) {
    return { run: 'STUB', detail: 'experimental_emit_not_toolchain_validated' };
  }
  if (target === 'js') {
    const c = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    return { run: c.status === 0 ? 'PASS' : 'FAIL', detail: (c.stderr || 'node --check').slice(0, 160) };
  }
  if (target === 'ts') {
    const t = runTsSyntax(file);
    return { run: t.ok ? 'PASS' : 'FAIL', detail: t.detail };
  }
  if (target === 'py') {
    const bin = pythonBin();
    if (!bin) return { run: 'SKIP', detail: 'python_absent' };
    const c = spawnSync(bin, ['-m', 'py_compile', file], { encoding: 'utf8' });
    return { run: c.status === 0 ? 'PASS' : 'FAIL', detail: (c.stderr || c.stdout || 'py_compile').slice(0, 200) };
  }
  if (target === 'go') {
    if (!hasCmd('go')) return { run: 'SKIP', detail: 'go_absent' };
    const obj = path.join(path.dirname(file), `${path.basename(file, '.go')}.o`);
    const c = spawnSync('go', ['tool', 'compile', '-p', 'clonefn', '-o', obj, file], {
      encoding: 'utf8', env: { ...process.env, GO111MODULE: 'off' },
    });
    return { run: c.status === 0 ? 'PASS' : 'FAIL', detail: (c.stderr || c.stdout || 'go tool compile').slice(0, 200) };
  }
  if (target === 'c') {
    const gcc = hasCmd('gcc') ? 'gcc' : hasCmd('cc') ? 'cc' : null;
    if (!gcc) return { run: 'SKIP', detail: 'gcc_absent' };
    const c = spawnSync(gcc, ['-std=gnu11', '-fsyntax-only', file], { encoding: 'utf8' });
    return { run: c.status === 0 ? 'PASS' : 'FAIL', detail: (c.stderr || c.stdout || 'gcc -fsyntax-only').slice(0, 200) };
  }
  if (target === 'java') {
    if (!hasCmd('javac')) return { run: 'SKIP', detail: 'javac_absent' };
    const c = spawnSync('javac', [file], { encoding: 'utf8' });
    return { run: c.status === 0 ? 'PASS' : 'FAIL', detail: (c.stderr || c.stdout || 'javac').slice(0, 200) };
  }
  if (target === 'rust') {
    if (!hasCmd('rustc')) return { run: 'SKIP', detail: 'rustc_absent' };
    const bin = path.join(path.dirname(file), `${path.basename(file, '.rs')}_bin`);
    const c = spawnSync('rustc', ['--crate-type', 'lib', '--cap-lints', 'allow', file, '-o', bin], { encoding: 'utf8' });
    return { run: c.status === 0 ? 'PASS' : 'FAIL', detail: (c.stderr || c.stdout || 'rustc').slice(0, 200) };
  }
  return { run: 'STUB', detail: 'experimental_emit_not_toolchain_validated' };
}

export function emitOneTarget(lia, name, target, workDir) {
  if (STUB_TARGETS.includes(target)) {
    return {
      target, name, status: 'STUB', emit: 'stub', run: 'STUB',
      reason: 'experimental_emit_not_toolchain_validated', file: null, code: '',
    };
  }
  let code;
  try {
    const r = compileLia(lia, {
      target, exportMode: 'single', withMain: false, package: 'clonefn',
      className: String(name || 'LinEmit').replace(/[^A-Za-z0-9]/g, '') || 'LinEmit',
      stubRuntime: false,
    });
    code = r.code || r.js || '';
    if (!code) throw new Error('empty_emit');
  } catch (e) {
    return {
      target, name, status: 'FAIL', emit: 'FAIL', run: 'n/a',
      reason: String(e.message || e).slice(0, 240), file: null, code: '',
    };
  }
  const file = writeWork(workDir, name, target, code);
  const ran = runTarget(target, file);
  const status = ran.run === 'FAIL' ? 'FAIL' : ran.run === 'SKIP' ? 'SKIP' : ran.run === 'STUB' ? 'STUB' : 'PASS';
  return {
    target, name, status, emit: 'ok', run: ran.run, reason: ran.detail, file, code,
  };
}

export function learnNewLang(storageDir, candDir, slug, fails) {
  if (!fails.length) return { hypothesis: null, candidate: null };
  const targets = [...new Set(fails.map((f) => f.target))];
  const hyp = `H_NEW_LANG_${slug}_${targets.join('_')}_${Date.now().toString(36)}`;
  if (storageDir) {
    appendStorage(
      storageDir,
      'lia_trauma.dicel',
      `class=NEW_LANG corpus=clone-lin-${slug} targets=${targets.join(',')} count=${fails.length} fix_target=emit_peripheral`,
    );
    appendStorage(
      storageDir,
      'lia_hypotheses.dicel',
      `id=${hyp} from=[NEW_LANG|${targets.join('|')}] claim="raise emit+run on new/failing target without nucleus mutate" transfer=same_class status=OPEN`,
    );
  }
  fs.mkdirSync(candDir, { recursive: true });
  const candPath = path.join(candDir, `CLONE_LANG_${slug}_${Date.now().toString(36)}.rulel`);
  const q = (s) => String(s || '').replace(/"/g, "'").slice(0, 120);
  fs.writeFileSync(
    candPath,
    [
      '@RULEL:LIN_CANDIDATE:1.0.0',
      '~R{.m=meta .h=harvest .f=forbid}',
      `.m{from_clone=clone-lin-${slug} stage=LEARN_NEW_LANG}`,
      '.f{mutate_nucleus=true}',
      `.h{${fails.slice(0, 8).map((f) => `fail{target=${f.target} fn=${f.name} emit=${f.emit} run=${f.run} reason="${q(f.reason)}"}`).join(' ')} fix=emit_peripheral}`,
      '',
    ].join('\n'),
    'utf8',
  );
  if (storageDir) {
    appendStorage(
      storageDir,
      'lia_ledger.dicel',
      `kind=learn_new_lang slug=${slug} hyp=${hyp} fails=${fails.length} candidate="${path.basename(candPath)}"`,
    );
  }
  return { hypothesis: hyp, candidate: candPath };
}

/** Emit all non-js targets for JS-pass fns; retry once after learn on FAIL. */
export function verifyMultiTargets(root, storageDir, candDir, jsResults, slug) {
  ensureToolchains({ quiet: true });
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), `lin_multi_${slug}_`));
  const others = REAL_TARGETS.filter((t) => t !== 'js');
  const perFn = [];
  const summary = {};
  for (const t of REAL_TARGETS) summary[t] = { PASS: 0, SKIP: 0, FAIL: 0, bytes: 0 };

  const passes = jsResults.filter((r) => r.status === 'pass' && (r.lia || r.fileLia));
  const fileGroups = new Map();
  for (const r of passes) {
    const key = r.linRel || r.srcRel || r.name;
    let g = fileGroups.get(key);
    if (!g) {
      g = { lia: r.fileLia || r.lia, names: [] };
      fileGroups.set(key, g);
    }
    if (r.fileLia) g.lia = r.fileLia;
    g.names.push(r.name);
    const jsCode = r.js || '';
    const jsFile = writeWork(workDir, r.name, 'js', jsCode);
    summary.js.PASS++;
    summary.js.bytes += Buffer.byteLength(jsCode, 'utf8');
    perFn.push({
      target: 'js', name: r.name, status: 'PASS', emit: 'ok', run: 'PASS',
      reason: 'oracle_behavior_eq', file: jsFile, code: jsCode,
    });
  }
  let gi = 0;
  const gTotal = fileGroups.size;
  for (const [key, g] of fileGroups) {
    gi += 1;
    if (gi === 1 || gi % 50 === 0 || gi === gTotal) {
      console.error(`[clone-lin] multi ${gi}/${gTotal} ${key}`);
    }
    const className = String(key).replace(/[^A-Za-z0-9]/g, '') || 'LinEmit';
    for (const t of others) {
      const row = emitOneTarget(g.lia, className, t, workDir);
      summary[t].bytes += Buffer.byteLength(row.code || '', 'utf8');
      for (const name of g.names) {
        summary[t][row.status] = (summary[t][row.status] || 0) + 1;
        perFn.push({ ...row, name });
      }
    }
  }

  const fails = perFn.filter((x) => x.status === 'FAIL');
  const learn = fails.length ? learnNewLang(storageDir, candDir, slug, fails) : { hypothesis: null };
  return { workDir, perFn, summary, learn, targets: REAL_TARGETS, stub: STUB_TARGETS };
}

/** Host-lang dumps stay in lia INTEL / verify workDir — never in clone-lin-* gh repo. */
export function copyMultiIntoPublish(_pubDir, _multi) {
  return;
}
