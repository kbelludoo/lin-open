/**
 * IMPROVE_LIN_FROM_CLONE + publish helpers for clone_lin_loop.
 * Never mutates verifier / semantic_hash / behavior_eq / LIN_gate nucleus.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { stripStubPassScores } from '../src/emit_shared.mjs';
import { formatStubIntel, honestNucleusMulti, hasStubPassScore } from './clone_lin_full_repo_gate.mjs';
import { autoGenerateFromFails } from './lin_auto_generate.mjs';

export function runCmd(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, {
    encoding: 'utf8', shell: false, cwd: opts.cwd, env: opts.env || process.env,
  });
  return { status: r.status ?? 1, out: `${r.stdout || ''}${r.stderr || ''}` };
}

export function appendStorage(storageDir, file, block) {
  const p = path.join(storageDir, file);
  fs.mkdirSync(storageDir, { recursive: true });
  fs.appendFileSync(p, `\n@E{t="${new Date().toISOString()}" ${block}}\n`, 'utf8');
}

export function classifyFail(v) {
  if (v.stage === 'emit') return 'EMIT_MAP';
  if (v.stage === 'compile') return 'PARSE';
  if (v.stage === 'runtime') {
    return /is not defined|ReferenceError/i.test(v.reason || '') ? 'CLOSURE' : 'RUNTIME_HELPER';
  }
  if (v.reason === 'holdout_mismatch') return 'SEMANTICS_GAP';
  return 'UNKNOWN';
}

export function learnFromFails(storageDir, fails, slug) {
  const classes = [...new Set(fails.map(classifyFail))];
  for (const c of classes) {
    appendStorage(
      storageDir,
      'lia_trauma.dicel',
      `class=${c} corpus=clone-lin-${slug} count=${fails.filter((f) => classifyFail(f) === c).length} fix_target=compiler_outside_nucleus`,
    );
  }
  const hyp = `H_CLONE_LIN_${slug}_${Date.now().toString(36)}`;
  appendStorage(
    storageDir,
    'lia_hypotheses.dicel',
    `id=${hyp} from=[${classes.join('|')}] claim="raise exact-hash pass on full clone-lin source tree" transfer=same_class status=OPEN`,
  );
  appendStorage(
    storageDir,
    'lia_ledger.dicel',
    `kind=clone_lin_learn slug=${slug} fail=${fails.length} classes=${classes.join(',')}`,
  );
  return { classes, hypothesis: hyp };
}

/** S5 mandatory: mine rewrite for peripheral LIN improvements. */
export function improveLinFromClone(root, storageDir, candDir, results, slug) {
  fs.mkdirSync(candDir, { recursive: true });
  const skips = results.filter((r) => r.status === 'skip');
  const fails = results.filter((r) => r.status === 'fail');
  const passes = results.filter((r) => r.status === 'pass');
  const reasonCounts = {};
  for (const r of [...skips, ...fails]) {
    const key = r.reason || classifyFail(r);
    reasonCounts[key] = (reasonCounts[key] || 0) + 1;
  }
  const harvest = [];
  if (reasonCounts.template_literal) {
    harvest.push({
      kind: 'emit_peripheral', gap: 'template_literal', n: reasonCounts.template_literal,
      proposal: 'preserve_or_desugar_template_literals_in_applySourceSigils', nucleus: false,
    });
  }
  if (reasonCounts.host_or_module_ref || reasonCounts.CLOSURE
    || fails.some((f) => classifyFail(f) === 'CLOSURE')) {
    harvest.push({
      kind: 'emit_peripheral', gap: 'CLOSURE',
      n: (reasonCounts.host_or_module_ref || 0) + (reasonCounts.CLOSURE || 0),
      proposal: 'preserve_free_var_bindings_when_extracting_named_fns', nucleus: false,
    });
  }
  if (passes.length) {
    harvest.push({
      kind: 'positive_transfer', gap: null, n: passes.length,
      proposal: `keep_arrow_ASI_fixes; names=${passes.map((p) => p.name).join(',')}`, nucleus: false,
    });
  }
  if (!harvest.length) {
    harvest.push({ kind: 'observe', gap: 'none_new', n: 0, proposal: 'no_new_peripheral_gap', nucleus: false });
  }

  const candPath = path.join(candDir, `CLONE_${slug}_${Date.now().toString(36)}.rulel`);
  fs.writeFileSync(
    candPath,
    [
      '@RULEL:LIN_CANDIDATE:1.0.0',
      '~R{.m=meta .h=harvest .f=forbid}',
      `.m{from_clone=clone-lin-${slug} stage=IMPROVE_LIN_FROM_CLONE}`,
      '.f{mutate_nucleus=true}',
      '.h{' + harvest.map((h) => `${h.kind}{gap="${h.gap}" n=${h.n} proposal="${h.proposal}" nucleus=${h.nucleus}}`).join(' ') + '}',
      '',
    ].join('\n'),
    'utf8',
  );

  const autogen = autoGenerateFromFails(root, candDir, fails, slug);
  const harvestSummary = harvest.map((h) => `${h.kind}:${h.gap || 'ok'}×${h.n}`).join('|');
  const summary = autogen.n ? `${harvestSummary}|autogen=${autogen.summary}` : harvestSummary;
  appendStorage(
    storageDir,
    'lia_ledger.dicel',
    `kind=improve_lin_from_clone slug=${slug} harvest="${harvestSummary}" autogen="${autogen.summary}" candidate="${path.basename(candPath)}" nucleus=untouched`,
  );
  appendStorage(
    storageDir,
    'lia_trauma.dicel',
    `class=HARVEST corpus=clone-lin-${slug} note="${summary}" fix_target=compiler_outside_nucleus`,
  );
  return { harvest, candidate: candPath, summary, autogen, root };
}

export function writeIntel(root, report) {
  const p = path.join(root, `INTEL_CLONE_LIN_${report.slug}.rulel`);
  const rate = report.suite_rate != null ? report.suite_rate : 0;
  const cov = report.coverage || {};
  const q = (s) => String(s || '').replace(/"/g, "'");
  const multi = honestNucleusMulti(report.multi || report.multi_line);
  const stub = formatStubIntel();
  const note = stripStubPassScores(q(report.note_pt));
  const body = [
    '@RULEL:INTEL_CLONE_LIN:1.4.0',
    '~R{.m=meta .g=gate .c=compare}',
      `.m{slug=${report.slug} lang=LIN status=${report.status} done=${report.done === true} published=${report.published === true} source="${q(report.source)}" url="${q(report.clone_lin_url)}" nucleus=ts!js!py!go!rust!c!java prefer_emit=ts}`,
    `.g{publish=full_repo_100_hash_eq skip_eq_fail=true behavior_eq=1.0 suite_rate=${rate} pass=${report.pass} fail=${report.fail} skip=${report.skip} files_ok=${cov.files_ok || 0} files_total=${cov.files_total || 0} stub_not_suite=true c_skip=ok_iff_gcc_absent_after_retry}`,
    `.c{pass="${q((report.pass_names || []).join('!'))}" fail="${q((report.fail_names || []).join('!'))}" multi="${q(multi)}" stub="${q(stub)}" learn=${report.learn || 'none'} improve=${q(report.improve_lin)} note="${note}"}`,
    '',
  ].join('\n');
  const multiField = (body.match(/multi="([^"]*)"/) || [])[1] || '';
  if (hasStubPassScore(multiField) || hasStubPassScore(body)) {
    throw new Error('INTEL_FALSE_RESULT: stub lang recorded as PASS');
  }
  fs.writeFileSync(p, body, 'utf8');
  return p;
}

export function buildPublishDir(root, slug, results, meta) {
  const dir = path.join(root, '.clone_lin_publish', `clone-lin-${slug}`);
  const persistentDir = path.join(root, 'clones_lin', slug);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(path.join(dir, 'lin'), { recursive: true });
  fs.mkdirSync(persistentDir, { recursive: true });

  const passes = results.filter((x) => x.status === 'pass');
  for (const r of passes) {
    const text = (r.lia || '').replace(/^@LIA:/, '@LIN:').replace(/^@AIL:/, '@LIN:');
    const safeName = String(r.name).replace(/[^a-zA-Z0-9._-]/g, '_');
    fs.writeFileSync(path.join(dir, 'lin', `${safeName}.lin`), text, 'utf8');
    fs.writeFileSync(path.join(persistentDir, `${safeName}.lin`), text, 'utf8');
  }
  const mt = meta.multi_summary ? honestNucleusMulti(meta.multi_summary) : 'prefer_ts';
  const stub = formatStubIntel();
  const fns = passes.map((r) => r.name).join('!');
  const readmeContent = [
    '@RULEL:CLONE_LIN:1.1.0',
    `~R{.m=meta .c=compile .f=forbid .p=path}`,
    `.m{repo=clone-lin-${slug} source="${meta.source}" truth=LIN+RULEL_only intel="lia/INTEL_CLONE_LIN_${slug}.rulel" nucleus=ts!js!py!go!rust!c!java prefer_emit=ts}`,
    '.c{cmd="lin compile lin/<fn>.lin --target ts|js|py|go|rust|c|java -o out" restore="compile_back_to_original_behavior"}',
    '.f{host_lang_in_repo .cjs .js .ts .py .go .rs compiled/}',
    `.p{lin="lin/*.lin" readme=README.md fns="${fns}" multi="${mt}" stub="${stub}"}`,
    '',
  ].join('\n');

  fs.writeFileSync(path.join(dir, 'README.md'), readmeContent, 'utf8');
  fs.writeFileSync(path.join(persistentDir, 'README.md'), readmeContent, 'utf8');
  return dir;
}

export function publishGh(root, dir, slug, dry) {
  const repoName = `clone-lin-${slug}`;
  if (dry) return { ok: true, mode: 'dry', url: null, local: dir, repoName };
  const who = runCmd('gh', ['api', 'user', '--jq', '.login'], { cwd: root });
  const user = (who.out || '').trim().split(/\r?\n/).filter(Boolean).pop();
  if (who.status !== 0 || !user) return { ok: false, error: 'gh_user_unavailable', local: dir, repoName };
  const full = `${user}/${repoName}`;
  const gitEnv = {
    ...process.env,
    GIT_AUTHOR_NAME: 'lin-bot',
    GIT_AUTHOR_EMAIL: 'lin-bot@users.noreply.github.com',
    GIT_COMMITTER_NAME: 'lin-bot',
    GIT_COMMITTER_EMAIL: 'lin-bot@users.noreply.github.com',
  };
  if (!fs.existsSync(path.join(dir, '.git'))) {
    let g = runCmd('git', ['init'], { cwd: dir });
    if (g.status !== 0) return { ok: false, error: `git_init:${g.out}`, local: dir, repoName };
    g = runCmd('git', ['add', '-A'], { cwd: dir });
    if (g.status !== 0) return { ok: false, error: `git_add:${g.out}`, local: dir, repoName };
    g = runCmd('git', ['commit', '-m', 'feat(clone-lin): initial LIN rewrite surface'], {
      cwd: dir, env: gitEnv,
    });
    if (g.status !== 0) return { ok: false, error: `git_commit:${g.out}`, local: dir, repoName };
  }
  if (runCmd('gh', ['repo', 'view', full, '--json', 'name'], { cwd: root }).status === 0) {
    runCmd('gh', ['repo', 'delete', full, '--yes'], { cwd: root });
  }
  const create = runCmd(
    'gh',
    ['repo', 'create', full, '--public', '--source', dir, '--remote', 'origin', '--push'],
    { cwd: root },
  );
  if (create.status !== 0) return { ok: false, error: create.out.slice(0, 500), local: dir, repoName };
  return { ok: true, mode: 'gh', url: `https://github.com/${full}`, local: dir, repoName };
}
