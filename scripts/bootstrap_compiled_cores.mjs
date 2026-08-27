/**
 * Restore src/*_core.compiled.cjs (and lexer_slices) from *.compiled_cjs.rulel
 * when missing. Chicken-and-egg: the Node host needs these CJS artifacts before
 * it can compile .lin sources. The purity pass deleted the .cjs files but kept
 * RULEL mirrors with identical content.
 *
 * Idempotent. Usage: node scripts/bootstrap_compiled_cores.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = path.join(root, 'src');

function extractRulelContent(rulelText) {
  const marker = '.source{content="';
  const start = rulelText.indexOf(marker);
  if (start < 0) throw new Error('missing .source{content=');
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

const rulels = fs.readdirSync(srcDir).filter((f) => f.endsWith('.compiled_cjs.rulel'));
let wrote = 0;
let skipped = 0;

for (const rulelName of rulels) {
  const cjsName = rulelName.replace(/\.compiled_cjs\.rulel$/, '.compiled.cjs');
  const cjsPath = path.join(srcDir, cjsName);
  const rulelPath = path.join(srcDir, rulelName);
  if (fs.existsSync(cjsPath)) {
    skipped += 1;
    continue;
  }
  const content = extractRulelContent(fs.readFileSync(rulelPath, 'utf8'));
  fs.writeFileSync(cjsPath, content, 'utf8');
  wrote += 1;
  console.log(`restored ${path.relative(root, cjsPath)} (${content.length} bytes)`);
}

console.log(`bootstrap_compiled_cores: wrote=${wrote} skipped=${skipped}`);
