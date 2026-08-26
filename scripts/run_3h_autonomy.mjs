#!/usr/bin/env node
/**
 * 3-Hour Autonomous LIN Self-Evolution & Self-Improvement Loop.
 * 
 * Target duration: 3 hours (10,800 seconds).
 * Continuous cycle:
 *   1. Check & Ensure Toolchains (node, tsc, python, go, rustc, gcc, javac)
 *   2. Self-Improvement (Deterministic repair + holdout oracle validation)
 *   3. Self-Evolution (Full test suite verification + multi-target emit + ledger commit)
 *   4. Clone & Rewrite Loop (Real repository rewriting & verification)
 *   5. Record provenance in storage/lia_ledger.rulel and INTEL_LIN_AUTONOMY_RUN.rulel
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LOG_FILE = path.join(ROOT, 'autonomy_3h.log');
const STATE_FILE = path.join(ROOT, 'autonomy_3h_state.json');

const DURATION_MS = 3 * 60 * 60 * 1000; // 3 hours (10,800,000 ms)
const startTime = Date.now();
const endTime = startTime + DURATION_MS;

function log(msg) {
  const t = new Date().toISOString();
  const line = `[${t}] ${msg}\n`;
  process.stdout.write(line);
  fs.appendFileSync(LOG_FILE, line, 'utf8');
}

function runCmd(cmd, args, timeoutMs = 300_000) {
  const res = spawnSync(cmd, args, {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: timeoutMs,
    maxBuffer: 20 * 1024 * 1024,
    shell: true
  });
  return {
    status: res.status ?? 1,
    out: ((res.stdout || '') + (res.stderr || '')).slice(-4000)
  };
}

fs.writeFileSync(LOG_FILE, `=== Starting 3-Hour LIN Autonomous Self-Evolution Loop ===\nStart: ${new Date(startTime).toISOString()}\nTarget End: ${new Date(endTime).toISOString()}\nDuration: 3 hours (10,800s)\n\n`, 'utf8');

let epoch = 0;
let totalImprovements = 0;
let totalEvolutions = 0;
let totalClones = 0;

while (Date.now() < endTime) {
  epoch++;
  const elapsedSec = Math.floor((Date.now() - startTime) / 1000);
  const remainingSec = Math.max(0, Math.floor((endTime - Date.now()) / 1000));
  
  log(`--- Epoch ${epoch} | Elapsed: ${elapsedSec}s | Remaining: ${remainingSec}s ---`);
  
  // 1. Toolchains check
  log('Step 1: Verifying Toolchains...');
  const tc = runCmd('node', ['scripts/ensure_toolchains.mjs'], 60_000);
  log(`Toolchains exit: ${tc.status}`);
  
  // 2. Self-Improvement
  log('Step 2: Running Self-Improvement Cycle...');
  const imp = runCmd('node', ['scripts/evolve_loop.mjs', 'improve'], 120_000);
  log(`Improve exit: ${imp.status}`);
  if (imp.status === 0) totalImprovements++;
  
  // 3. Self-Evolution
  log('Step 3: Running Self-Evolution Cycle (Suite Verification)...');
  const evo = runCmd('node', ['scripts/evolve_loop.mjs', 'evolve'], 180_000);
  log(`Evolution exit: ${evo.status}`);
  if (evo.status === 0) totalEvolutions++;
  
  // 4. Clone Loop Cycle
  log('Step 4: Running Clone & Rewrite Verification Cycle...');
  const cln = runCmd('node', ['scripts/clone_lin_loop.mjs', '--cycles', '1', '--max-fns', '8'], 240_000);
  log(`Clone loop exit: ${cln.status}`);
  if (cln.status === 0) totalClones++;
  
  // 5. Multi-Emit Gate Verification
  log('Step 5: Running Multi-Target Gate...');
  const multi = runCmd('node', ['scripts/golden_multi_emit.mjs'], 60_000);
  log(`Multi-emit exit: ${multi.status}`);
  
  // Update state file
  const state = {
    epoch,
    startTime: new Date(startTime).toISOString(),
    endTime: new Date(endTime).toISOString(),
    lastUpdated: new Date().toISOString(),
    elapsedSeconds: elapsedSec,
    remainingSeconds: remainingSec,
    totalImprovements,
    totalEvolutions,
    totalClones,
    status: Date.now() < endTime ? 'RUNNING' : 'COMPLETED'
  };
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
  
  // Short pause before next epoch
  const sleepMs = 5000;
  spawnSync('sleep', ['5'], { stdio: 'ignore' });
}

log(`=== 3-Hour LIN Autonomous Self-Evolution Loop FINISHED ===\nTotal Epochs: ${epoch}\nTotal Improvements: ${totalImprovements}\nTotal Evolutions: ${totalEvolutions}\nTotal Clones: ${totalClones}\n`);
