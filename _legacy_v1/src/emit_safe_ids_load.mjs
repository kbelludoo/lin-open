/**
 * Host loader: LIN source is src/emit_safe_ids.lin
 * Rename reserved params (len, type, ...) inside bodies so Go/C/Java match signatures.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';
import { safeEmitId } from './emit_shared.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'emit_safe_ids.lin');
const lin = fs.readFileSync(LIN, 'utf8');
const { js } = compileLiaToJs(lin, { exportMode: 'multiple' });
const tmp = path.join(os.tmpdir(), 'lin_emit_safe_ids.cjs');
fs.writeFileSync(tmp, js, 'utf8');
const mod = createRequire(import.meta.url)(tmp);
try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }

export function rawParamNames(paramsRaw) {
  const csv = String(mod.rawParamNamesCsv(paramsRaw) || '');
  return csv ? csv.split(',').filter(Boolean) : [];
}

export function rewriteSafeParamIds(body, rawNames) {
  const raws = [...(rawNames || [])].filter(Boolean).sort((a, b) => b.length - a.length);
  const safes = raws.map((r) => safeEmitId(r));
  return String(mod.rewriteSafeParamIds(String(body || ''), raws.join(','), safes.join(',')));
}
