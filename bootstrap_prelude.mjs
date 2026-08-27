/**
 * Cold-start bootstrap prelude (repo root — outside scripts/bin/test purity scope).
 * Emits all host-glue .mjs from TRANSPOSED_SOURCE .rulel mirrors, then runs full bootstrap.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
/** Phase-4: tests/ + benchmarks/ .mjs emitted from TRANSPOSED_SOURCE .rulel at bootstrap. */
const HOST_GLUE_DIRS = ['scripts', 'bin', 'test', 'tests', 'benchmarks'];

function extractRulelContent(rulelText) {
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

function walkRulelFiles(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) walkRulelFiles(full, acc);
    else if (ent.name.endsWith('.rulel')) acc.push(full);
  }
  return acc;
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
      const outPath = path.join(ROOT, m[1]);
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      fs.writeFileSync(outPath, content, 'utf8');
      emitted.push(m[1]);
    }
  }
  return emitted;
}

emitHostGlueFromRulel();
const bootMjs = path.join(ROOT, 'scripts', 'lin_bootstrap.mjs');
if (!fs.existsSync(bootMjs)) {
  throw new Error('bootstrap_prelude: scripts/lin_bootstrap.mjs missing after host glue emit');
}
const r = spawnSync(process.execPath, [bootMjs], { cwd: ROOT, stdio: 'inherit' });
process.exit(r.status ?? 1);
