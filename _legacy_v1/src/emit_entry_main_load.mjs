/**
 * Host loader: LIN source is src/emit_entry_main.lin
 * Quality-suite entry main vs golden safeCompare main.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from './compiler.mjs';

const LIN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'emit_entry_main.lin');
const lin = fs.readFileSync(LIN, 'utf8');
const { js } = compileLiaToJs(lin, { exportMode: 'multiple' });
const tmp = path.join(os.tmpdir(), 'lin_emit_entry_main.cjs');
fs.writeFileSync(tmp, js, 'utf8');
const mod = createRequire(import.meta.url)(tmp);
try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }

export const qualityFnNames = mod.qualityFnNames;
export const qualityCallCount = mod.qualityCallCount;
export const qualityCallFn = mod.qualityCallFn;
export const qualityCallArgs = mod.qualityCallArgs;
export const isQualityFnSet = mod.isQualityFnSet;
export const wantSafeCompareMain = mod.wantSafeCompareMain;

export function qualityCalls() {
  const n = Number(mod.qualityCallCount()) || 0;
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push({ fn: String(mod.qualityCallFn(i)), args: String(mod.qualityCallArgs(i)) });
  }
  return out;
}

export function formatQualityMain(target, nameMap) {
  const host = (n) => (nameMap && nameMap[n]) || n;
  const calls = qualityCalls();
  const call = (c) => `${host(c.fn)}(${c.args})`;
  if (target === 'rust') {
    const body = calls.map((c) => `    println!("{}", ${call(c)});`).join('\n');
    return `\nfn main() {\n${body}\n}\n`;
  }
  if (target === 'go') {
    const body = calls.map((c) => `\tfmt.Println(${call(c)})`).join('\n');
    return `\nfunc main() {\n${body}\n}\n`;
  }
  if (target === 'c') {
    const prints = calls.map((c) => `  printf("%lld\\n", (long long)${call(c)});`).join('\n');
    return `\nint main(void) {\n${prints}\n  return 0;\n}\n`;
  }
  if (target === 'java') {
    const prints = calls.map((c) => `    System.out.println(${call(c)});`).join('\n');
    return `  public static void main(String[] args) {\n${prints}\n  }`;
  }
  return '';
}
