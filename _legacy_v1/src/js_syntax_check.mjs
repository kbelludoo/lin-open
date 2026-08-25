/**
 * Fail-closed JS emit: node --check before compile OK / write.
 * lossy=true may warn; MUST NOT write illegal JS.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export function jsSyntaxCheck(js) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lin_js_chk_'));
  const file = path.join(dir, 'emit.cjs');
  fs.writeFileSync(file, String(js ?? ''), 'utf8');
  const r = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
  try { fs.rmSync(dir, { recursive: true, force: true }); } catch { /* ignore */ }
  const detail = String(r.stderr || r.stdout || 'node --check').trim().slice(0, 240);
  return { ok: r.status === 0, detail: detail || 'node --check' };
}

export function assertJsParse(js, opts = {}) {
  const { ok, detail } = jsSyntaxCheck(js);
  if (ok) return;
  if (opts.lossy) console.warn(`LIN_EMIT_JS_SYNTAX (lossy): ${detail}`);
  throw new Error(`LIN_EMIT_JS_SYNTAX: ${detail}`);
}
