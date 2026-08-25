/**
 * Loader dos slices do lexer compilados de LIN (LIN_REGEX_002).
 * Sem imports de compiler/parser: artefato é JS puro commitado.
 * LEXER_SLICES_OFF=1 desliga (lexer cai no caminho inline original).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

let cached = null;
let loaded = false;

export function lexerSlices() {
  if (loaded) return cached;
  loaded = true;
  if (process.env.LEXER_SLICES_OFF === '1') {
    cached = null;
    return cached;
  }
  try {
    const artifact = path.join(__dirname, 'lexer_slices.compiled.cjs');
    if (!fs.existsSync(artifact)) {
      cached = null;
      return cached;
    }
    const mod = require(artifact);
    for (const k of ['identLenAt', 'wsRunAt', 'numLenAt']) {
      if (typeof mod[k] !== 'function') throw new Error(`slice ausente: ${k}`);
    }
    cached = { identLenAt: mod.identLenAt, wsRunAt: mod.wsRunAt, numLenAt: mod.numLenAt };
  } catch {
    cached = null;
  }
  return cached;
}
