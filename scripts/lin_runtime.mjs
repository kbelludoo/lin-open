/**
 * Resolve build/runtime/ (LIN bootstrap output). Ensures bootstrap ran.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const RUNTIME = path.join(ROOT, 'build', 'runtime');
export const RUNTIME_SELFHOST = path.join(RUNTIME, 'selfhost');

export function runtimePath(...parts) {
  return path.join(RUNTIME, ...parts);
}

export function runtimeUrl(...parts) {
  return pathToFileURL(runtimePath(...parts)).href;
}

export async function ensureRuntime() {
  const marker = runtimePath('compiler.mjs');
  if (!fs.existsSync(marker)) {
    const boot = pathToFileURL(path.join(ROOT, 'scripts', 'lin_bootstrap.mjs')).href;
    const { runLinBootstrap } = await import(boot);
    await runLinBootstrap({ quiet: true });
  }
  if (!fs.existsSync(marker)) {
    throw new Error('LIN bootstrap failed: build/runtime/compiler.mjs missing');
  }
}

export async function importRuntime(spec) {
  await ensureRuntime();
  return import(runtimeUrl(spec));
}
