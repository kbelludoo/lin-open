#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile, REAL_TARGETS, DEFAULT_EMIT_TARGET, LIN_VERSION } from '../src/compiler.mjs';
import { parseProgram } from '../src/parser.mjs';
import { programHashes } from '../src/semantic_hash.mjs';
import { parseRulel, validateComms } from '../src/rulel.mjs';
import { verify } from '../src/verifier.mjs';
import { runInMemory } from '../src/vm.mjs';
import { emitLinFromJs } from '../src/emit_from_js.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function usage() {
  console.error(`lin <command> [args] — LIN v${LIN_VERSION} (in-memory rewrite)

Commands:
  check <file.lin>                    parse + list fns/exports/consts
  compile <file.lin> [--target t] [-o out]
       targets: ${REAL_TARGETS.join('|')} (default ${DEFAULT_EMIT_TARGET})
  run <file.lin> [jsonArgs...]        compile + execute exports in memory
  hash <file.lin>                     semantic hashes per fn
  effects <file.lin>                  effect inference per fn
  emit <file.js> [-o out.lin]         JS subset → LIN source
  rulel-check <file.rulel>            RULEL parse + COMMS validation
  verify <file.lin> [--behavior cases.json]
                                      full gate report
  version`);
  process.exit(2);
}

const [cmd, ...rest] = process.argv.slice(2);
if (!cmd || cmd === 'help') usage();

function takeFlag(argv, name) {
  const i = argv.indexOf(name);
  if (i >= 0 && argv[i + 1]) {
    return { value: argv[i + 1], args: argv.filter((_, j) => j !== i && j !== i + 1) };
  }
  return { value: null, args: argv };
}

function readInput(file) {
  if (!file) usage();
  const resolved = path.resolve(file);
  return fs.readFileSync(resolved, 'utf8');
}

if (cmd === 'version') {
  console.log(LIN_VERSION);
  process.exit(0);
}

if (cmd === 'check') {
  const text = readInput(rest[0]);
  const prog = parseProgram(text);
  console.log(JSON.stringify({
    header: prog.header,
    fns: prog.fns.map((f) => f.name),
    exports: prog.exports,
    consts: prog.consts ? Object.keys(prog.consts) : [],
    structs: prog.structs.map((s) => s.name),
    enums: prog.enums.map((e) => e.name),
    modules: prog.modules.map((m) => m.name),
  }, null, 2));
  process.exit(0);
}

if (cmd === 'compile') {
  let argv = rest;
  const outT = takeFlag(argv, '-o');
  argv = outT.args;
  const tgt = takeFlag(argv, '--target');
  argv = tgt.args;
  const stubFlag = argv.includes('--stub-js-runtime-only');
  argv = argv.filter((a) => a !== '--stub-js-runtime-only');
  const target = String(tgt.value || DEFAULT_EMIT_TARGET).toLowerCase();
  const file = argv[0];
  const text = readInput(file);
  try {
    const r = compile(text, { target, stubJsRuntimeOnly: stubFlag });
    if (outT.value) {
      fs.writeFileSync(path.resolve(outT.value), r.code, 'utf8');
      console.log(JSON.stringify({ out: path.resolve(outT.value), target, fns: r.fns }));
    } else {
      process.stdout.write(r.code);
    }
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

if (cmd === 'run') {
  const file = rest[0];
  const text = readInput(file);
  try {
    const r = compile(text, { target: 'js' });
    const mod = runInMemory(r.code);
    const callArgs = rest.slice(1).filter((a) => a.trim());
    const out = {};
    for (const name of Object.keys(mod)) {
      const fnRef = mod[name];
      if (typeof fnRef === 'function' && callArgs.length && mod.hasOwnProperty(name)) {
        out[name] = fnRef(...JSON.parse(callArgs[0]));
      } else {
        out[name] = typeof fnRef === 'function' ? `[fn ${(fnRef.length)} args]` : fnRef;
      }
    }
    console.log(JSON.stringify(out, null, 2));
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

if (cmd === 'hash') {
  const text = readInput(rest[0]);
  const prog = parseProgram(text);
  console.log(JSON.stringify(programHashes(prog), null, 2));
  process.exit(0);
}

if (cmd === 'effects') {
  const text = readInput(rest[0]);
  const r = compile(text, { target: 'js' });
  const out = Object.fromEntries(r.program.fns.map((f) => [f.name, f.effect]));
  console.log(JSON.stringify(out, null, 2));
  process.exit(0);
}

if (cmd === 'emit') {
  let argv = rest;
  const outT = takeFlag(argv, '-o');
  argv = outT.args;
  const file = argv[0];
  if (!file) usage();
  try {
    const js = fs.readFileSync(path.resolve(file), 'utf8');
    const r = emitLinFromJs(js);
    if (outT.value) {
      fs.writeFileSync(path.resolve(outT.value), r.lin, 'utf8');
      console.log(JSON.stringify({ out: path.resolve(outT.value), fns: r.fns }));
    } else {
      process.stdout.write(r.lin);
    }
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

if (cmd === 'rulel-check') {
  const text = readInput(rest[0]);
  const parsed = parseRulel(text);
  const validation = validateComms(parsed);
  console.log(JSON.stringify({ header: parsed.header, validation }, null, 2));
  process.exit(validation.ok ? 0 : 1);
}

if (cmd === 'verify') {
  const bt = takeFlag(rest, '--behavior');
  const file = bt.args[0];
  const text = readInput(file);
  const opts = {};
  if (bt.value) opts.behavior = JSON.parse(fs.readFileSync(path.resolve(bt.value), 'utf8'));
  const report = verify(text, opts);
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok ? 0 : 1);
}

if (cmd === 'clone-lin' || cmd === 'clone_lin') {
  const { runCloneLoop } = await import('../src/selfhost/loop.mjs');
  const st = takeFlag(rest, '--stop-file');
  const cy = takeFlag(st.args, '--cycles');
  const mf = takeFlag(cy.args, '--max-fns');
  const pd = takeFlag(mf.args, '--publish-dir');
  const sourceDir = pd.args[0];
  if (!sourceDir) usage();
  const queue = [];
  for (const e of fs.readdirSync(path.resolve(sourceDir), { withFileTypes: true })) {
    if (e.isFile() && /\.js$/.test(e.name)) {
      queue.push({ name: e.name.replace(/\.js$/, ''), source: fs.readFileSync(path.join(path.resolve(sourceDir), e.name), 'utf8') });
    }
  }
  const state = runCloneLoop({
    queue,
    cycles: cy.value ? Number(cy.value) : 0,
    stopFile: st.value ? path.resolve(st.value) : null,
    maxFns: mf.value ? Number(mf.value) : 0,
    publishDir: pd.value ? path.resolve(pd.value) : null,
    dryPublish: !pd.value,
  });
  console.log(JSON.stringify(state, null, 2));
  process.exit(state.suiteRate === 1 ? 0 : state.partial.length || state.repos.length ? (state.suiteRate === 1 ? 0 : 3) : 1);
}

if (cmd === 'improve' || cmd === 'evolve') {
  const { improveSource } = await import('../src/selfhost/loop.mjs');
  const file = rest[0];
  const text = readInput(file);
  const r = improveSource(text);
  console.log(JSON.stringify({ applied: r.applied, changed: r.source !== text }, null, 2));
  process.exit(0);
}

if (cmd === 'autonomy-status' || cmd === 'autonomy_status') {
  const { autonomyStatus } = await import('../src/selfhost/loop.mjs');
  const sp = path.resolve(rest[0] || '.clone_state.json');
  console.log(JSON.stringify(autonomyStatus(sp), null, 2));
  process.exit(0);
}

usage();
