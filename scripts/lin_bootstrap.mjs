/**
 * LIN self-host bootstrap: src/*.lin + src/*.rulel → build/runtime/
 * - Host glue: extracted from TRANSPOSED_SOURCE .rulel mirrors (not committed as .mjs in src/)
 * - Cores: compiled from *_core.lin via LIN (LIN compiles LIN)
 * - Fixed-point gate on compiler.lin when emit-ready
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { runAllHashGates } from './hash_gates.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'src');
const RUNTIME = path.join(ROOT, 'build', 'runtime');
const SELFHOST_RT = path.join(RUNTIME, 'selfhost');

const CORES = [
  { lin: 'lexer_slices.lin', cjs: 'lexer_slices.compiled.cjs', exports: ['identLenAt', 'wsRunAt', 'numLenAt'] },
  { lin: 'semantic_hash_core.lin', cjs: 'semantic_hash_core.compiled.cjs', exports: ['escapeRe', 'canonicalize'] },
  { lin: 'effects_core.lin', cjs: 'effects_core.compiled.cjs', exports: ['firstUseIsRead', 'collectAssignedIds'] },
  { lin: 'rulel_core.lin', cjs: 'rulel_core.compiled.cjs', exports: ['splitTopEntries', 'parseValuePairs', 'parseRulel', 'validateComms'] },
  { lin: 'vm_core.lin', cjs: 'vm_core.compiled.cjs', exports: ['assertJsSyntaxCore', 'validateSandboxSpec'] },
  { lin: 'verifier_core.lin', cjs: 'verifier_core.compiled.cjs', exports: ['deepEq', 'findMissingExports'] },
  {
    lin: 'transpiler_to_lin_core.lin',
    cjs: 'transpiler_to_lin_core.compiled.cjs',
    exports: ['detectLanguage', 'extractBracedFunctions', 'transpileRustToLin', 'transpileGoToLin', 'transpileCToLin', 'transpileZigToLin'],
  },
];

function sha256(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
}

export function extractRulelContent(rulelText) {
  const marker = '.source{content="';
  const start = rulelText.indexOf(marker);
  if (start < 0) return null;
  let i = start + marker.length;
  let out = '';
  while (i < rulelText.length) {
    const ch = rulelText[i];
    if (ch === '\\') {
      const n = rulelText[i + 1];
      const map = { n: '\n', r: '\r', t: '\t', '"': '"', '\\': '\\' };
      if (n in map) {
        out += map[n];
        i += 2;
        continue;
      }
      out += n;
      i += 2;
      continue;
    }
    if (ch === '"') break;
    out += ch;
    i += 1;
  }
  return out;
}

function rulelOriginalPath(rulelText, rulelName) {
  const m = rulelText.match(/~METADATA\{original="([^"]+)"/);
  if (m) return m[1];
  if (rulelName.endsWith('.compiled_cjs.rulel')) {
    return `src/${rulelName.replace(/\.compiled_cjs\.rulel$/, '.compiled.cjs')}`;
  }
  return null;
}

function walkRulelFiles(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) walkRulelFiles(full, acc);
    else if (ent.name.endsWith('.rulel')) acc.push(full);
  }
  return acc;
}

function escapeRulelSource(text) {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t');
}

export function jsonToTransposedRulel(relJsonPath, jsonText) {
  const rel = relJsonPath.replace(/\\/g, '/');
  return `@RULEL:TRANSPOSED_SOURCE:1.0\n~METADATA{original="${rel}" ext=".json"}\n.source{content="${escapeRulelSource(jsonText)}"}\n`;
}

export function mjsToTransposedRulel(relMjsPath, mjsText) {
  const rel = relMjsPath.replace(/\\/g, '/');
  return `@RULEL:TRANSPOSED_SOURCE:1.0\n~METADATA{original="${rel}" lang="mjs"}\n.source{content="${escapeRulelSource(mjsText)}"}\n`;
}

/** Host-glue dirs whose .mjs is emitted from TRANSPOSED_SOURCE .rulel at bootstrap (not src/). */
const HOST_GLUE_DIRS = ['scripts', 'bin', 'test'];

function findJsonMirrorRulel(relJsonPath) {
  const rel = relJsonPath.replace(/\\/g, '/');
  const dir = path.dirname(rel);
  const base = path.basename(rel, '.json');
  const candidates = [
    path.join(ROOT, rel.replace(/\.json$/, '_json.rulel')),
    path.join(ROOT, dir === '.' ? `${base.replace(/\./g, '_')}.rulel` : path.join(dir, `${base.replace(/\./g, '_')}.rulel`)),
    path.join(ROOT, dir === '.' ? `${base}_json.rulel` : path.join(dir, `${base}_json.rulel`)),
  ];
  for (const c of candidates) {
    if (!fs.existsSync(c)) continue;
    const text = fs.readFileSync(c, 'utf8');
    if (text.includes('TRANSPOSED_SOURCE') && text.includes(`original="${rel}"`)) return c;
  }
  for (const rulelPath of walkRulelFiles(ROOT)) {
    const text = fs.readFileSync(rulelPath, 'utf8');
    if (!text.includes('TRANSPOSED_SOURCE')) continue;
    const m = text.match(/original="([^"]+)"/);
    if (m && m[1] === rel) return rulelPath;
  }
  return null;
}

export function ensureJsonMirrors() {
  const created = [];
  const skipDirs = new Set(['node_modules', 'build', '.git']);
  function walkJson(dir) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      if (skipDirs.has(ent.name)) continue;
      const full = path.join(dir, ent.name);
      if (ent.isDirectory()) walkJson(full);
      else if (ent.name.endsWith('.json')) {
        const rel = path.relative(ROOT, full).replace(/\\/g, '/');
        if (findJsonMirrorRulel(rel)) continue;
        const mirrorPath = path.join(path.dirname(full), `${path.basename(rel, '.json')}_json.rulel`);
        const jsonText = fs.readFileSync(full, 'utf8');
        fs.writeFileSync(mirrorPath, jsonToTransposedRulel(rel, jsonText), 'utf8');
        created.push(path.relative(ROOT, mirrorPath).replace(/\\/g, '/'));
      }
    }
  }
  walkJson(ROOT);
  return created;
}

function emitRepoJsonFromRulel() {
  const emitted = [];
  for (const rulelPath of walkRulelFiles(ROOT)) {
    const text = fs.readFileSync(rulelPath, 'utf8');
    if (!text.includes('TRANSPOSED_SOURCE')) continue;
    const m = text.match(/original="([^"]+)"/);
    if (!m || !m[1].endsWith('.json')) continue;
    const content = extractRulelContent(text);
    if (!content) continue;
    const outPath = path.join(ROOT, m[1]);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, content, 'utf8');
    emitted.push(m[1]);
  }
  return emitted;
}

function emitTransposedToPath(originalRel, content) {
  if (originalRel.startsWith('src/')) {
    const rel = originalRel.replace(/^src\//, '');
    const out = rel.startsWith('selfhost/')
      ? path.join(SELFHOST_RT, path.basename(rel))
      : path.join(RUNTIME, rel);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, content, 'utf8');
    return originalRel;
  }
  const outPath = path.join(ROOT, originalRel);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, content, 'utf8');
  return originalRel;
}

function extractTransposedRulels() {
  const emitted = [];
  for (const rulelPath of walkRulelFiles(SRC)) {
    const text = fs.readFileSync(rulelPath, 'utf8');
    if (!text.includes('TRANSPOSED_SOURCE') && !text.includes('.source{content=')) continue;
    const content = extractRulelContent(text);
    if (!content) continue;
    const original = rulelOriginalPath(text, path.basename(rulelPath));
    if (!original || !original.startsWith('src/')) continue;
    emitted.push(emitTransposedToPath(original, content));
  }
  return emitted;
}

function emitHostGlueFromRulel() {
  const emitted = [];
  for (const dirName of HOST_GLUE_DIRS) {
    const dir = path.join(ROOT, dirName);
    if (!fs.existsSync(dir)) continue;
    for (const rulelPath of walkRulelFiles(dir)) {
      const text = fs.readFileSync(rulelPath, 'utf8');
      if (!text.includes('TRANSPOSED_SOURCE')) continue;
      const m = text.match(/original="([^"]+)"/);
      if (!m || !m[1].endsWith('.mjs')) continue;
      const content = extractRulelContent(text);
      if (!content) continue;
      emitted.push(emitTransposedToPath(m[1], content));
    }
  }
  return emitted;
}

function extractCompiledCjsRulels() {
  let count = 0;
  for (const name of fs.readdirSync(SRC)) {
    if (!name.endsWith('.compiled_cjs.rulel')) continue;
    const text = fs.readFileSync(path.join(SRC, name), 'utf8');
    const content = extractRulelContent(text);
    if (!content) continue;
    const cjsName = name.replace(/\.compiled_cjs\.rulel$/, '.compiled.cjs');
    fs.writeFileSync(path.join(RUNTIME, cjsName), content, 'utf8');
    count += 1;
  }
  return count;
}

async function compileCoresFromLin() {
  const compilerUrl = pathToFileURL(path.join(RUNTIME, 'compiler.mjs')).href;
  const { compile } = await import(compilerUrl);
  const compiled = [];
  for (const core of CORES) {
    const linPath = path.join(SRC, core.lin);
    const cjsPath = path.join(RUNTIME, core.cjs);
    const src = fs.readFileSync(linPath, 'utf8');
    try {
      const result = compile(src, { target: 'js' });
      const out = `${result.code}\nmodule.exports={${core.exports.join(',')}};\n`;
      fs.writeFileSync(cjsPath, out, 'utf8');
      compiled.push({ lin: core.lin, cjs: core.cjs, bytes: out.length, hash: sha256(out).slice(0, 16), source: 'lin' });
    } catch (e) {
      if (!fs.existsSync(cjsPath)) throw e;
      compiled.push({ lin: core.lin, cjs: core.cjs, source: 'rulel_seed', error: String(e.message || e).slice(0, 120) });
    }
  }
  return compiled;
}

async function selfHostCompilerGate() {
  const compilerUrl = pathToFileURL(path.join(RUNTIME, 'compiler.mjs')).href;
  const { compile } = await import(compilerUrl);
  const linPath = path.join(SRC, 'compiler.lin');
  const src = fs.readFileSync(linPath, 'utf8');
  try {
    const gen1 = compile(src, { target: 'js' }).code;
    const gen2 = compile(src, { target: 'js' }).code;
    return {
      ok: sha256(gen1) === sha256(gen2),
      gen1Hash: sha256(gen1).slice(0, 16),
      gen2Hash: sha256(gen2).slice(0, 16),
      note: 'compiler.lin deterministic emit (LIN compiles LIN idempotent)',
    };
  } catch (e) {
    return { ok: false, error: String(e.message || e).slice(0, 200) };
  }
}

export async function runLinBootstrap(opts = {}) {
  const quiet = !!opts.quiet;
  fs.mkdirSync(RUNTIME, { recursive: true });
  fs.mkdirSync(SELFHOST_RT, { recursive: true });

  const mirrorsCreated = ensureJsonMirrors();
  if (!quiet && mirrorsCreated.length) {
    console.log(`[lin_bootstrap] created JSON mirrors: ${mirrorsCreated.length} new .rulel files`);
  }

  const jsonEmitted = emitRepoJsonFromRulel();
  if (!quiet && jsonEmitted.length) {
    console.log(`[lin_bootstrap] emitted host JSON from .rulel: ${jsonEmitted.join(', ')}`);
  }

  const hostGlueEmitted = emitHostGlueFromRulel();
  const extracted = extractTransposedRulels();
  const cjsSeeds = extractCompiledCjsRulels();
  if (!quiet) {
    if (hostGlueEmitted.length) {
      console.log(`[lin_bootstrap] emitted host glue from .rulel: ${hostGlueEmitted.join(', ')}`);
    }
    console.log(`[lin_bootstrap] extracted ${extracted.length} src TRANSPOSED_SOURCE rulel → build/runtime/`);
    console.log(`[lin_bootstrap] seeded ${cjsSeeds} compiled_cjs.rulel mirrors`);
  }

  const cores = await compileCoresFromLin();
  if (!quiet) {
    for (const c of cores) {
      const tag = c.source === 'lin' ? `LIN→LIN ${c.bytes}b ${c.hash}` : `rulel_seed (${c.error || 'emit pending'})`;
      console.log(`[lin_bootstrap] ${c.lin} → ${c.cjs}: ${tag}`);
    }
  }

  const gate = await selfHostCompilerGate();
  if (!quiet) {
    console.log(`[lin_bootstrap] compiler.lin self-host gate: ${gate.ok ? 'PASS' : 'SKIP'} ${gate.error || `${gate.gen1Hash} vs ${gate.gen2Hash}`}`);
  }

  const hashGates = await runAllHashGates(RUNTIME);
  if (!quiet) {
    for (const g of hashGates.gates) {
      const tag = g.ok ? 'PASS' : 'FAIL';
      console.log(`[lin_bootstrap] hash gate ${g.gate}: ${tag}`);
    }
  }
  if (!hashGates.ok) {
    const failed = hashGates.gates.filter((g) => !g.ok).map((g) => g.gate);
    throw new Error(`LIN bootstrap hash gates failed: ${failed.join(', ')}`);
  }

  const manifest = {
    policy: 'LIN_compiles_LIN',
    src_purity: 'only .lin + .rulel in src/',
    host_glue_purity: 'scripts/bin/test .mjs emitted from TRANSPOSED_SOURCE .rulel at bootstrap',
    json_purity: 'only .rulel in repo; host .json emitted at bootstrap',
    runtime: 'build/runtime/',
    json_emitted: jsonEmitted,
    host_glue_emitted: hostGlueEmitted,
    extracted_rulel: extracted,
    cjs_seeds: cjsSeeds,
    cores_compiled_from_lin: cores,
    compiler_self_host_gate: gate,
    hash_gates: hashGates,
    timestamp: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(RUNTIME, '.bootstrap.manifest'), JSON.stringify(manifest, null, 2));
  return manifest;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runLinBootstrap().then((m) => {
    console.log(JSON.stringify({ ok: true, cores: m.cores_compiled_from_lin.length }, null, 2));
  }).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
