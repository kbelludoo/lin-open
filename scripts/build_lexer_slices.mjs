/**
 * Regenera src/lexer_slices.compiled.cjs a partir de src/lexer_slices.lin
 * (LIN_REGEX_002). Uso: node scripts/build_lexer_slices.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);

const { compile } = await import(path.join(root, 'src', 'compiler.mjs'));
const lin = fs.readFileSync(path.join(root, 'src', 'lexer_slices.lin'), 'utf8');
const r = compile(lin, { target: 'js' });

const EXPORTS = ['identLenAt', 'wsRunAt', 'numLenAt'];
for (const name of EXPORTS) {
  if (!new RegExp(`function ${name}\\(`).test(r.code)) {
    throw new Error(`LIN_REGEX_002: slice ausente no emit: ${name}`);
  }
}

const out = `${r.code}\nmodule.exports={${EXPORTS.join(',')}};\n`;
const dest = path.join(root, 'src', 'lexer_slices.compiled.cjs');
fs.writeFileSync(dest, out);
console.log(`ok ${path.relative(root, dest)} (${out.length} bytes)`);
