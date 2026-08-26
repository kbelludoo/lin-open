/**
 * Confirmatory Phase A Runner (PREREG-AIN-LB-001)
 * HARD LOCK:
 * 1. Reads model_id and rules EXCLUSIVELY from prereg/phase_a_prereg.json.
 * 2. Refuses any CLI/env override that contradicts the sealed manifest.
 * 3. ZERO cross-model fallback. Single fixed model with backoff on same route.
 * 4. Total seed invalidation on persistent infrastructure errors.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { TASKS, RECOVERY_TASK, COLD_TASK } from '../benchmarks/ain-lb/tasks/define.mjs';
import { check } from '../benchmarks/ain-lb/langcheck.mjs';
import { createProvider } from '../benchmarks/ain-lb/provider.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PREREG_FILE = path.join(ROOT, 'prereg', 'phase_a_prereg.json');
const OUT_DIR = path.join(ROOT, 'raw', 'phase_a');
fs.mkdirSync(OUT_DIR, { recursive: true });

if (!fs.existsSync(PREREG_FILE)) {
  throw new Error(`CRITICAL PREREG ERROR: ${PREREG_FILE} not found. Manifest must be sealed before execution.`);
}

const preregContent = fs.readFileSync(PREREG_FILE, 'utf8');
const preregSha256 = crypto.createHash('sha256').update(preregContent).digest('hex');
const prereg = JSON.parse(preregContent);

const LOCKED_MODEL = prereg.governance.model_id;
const PACING_DELAY_MS = prereg.governance.pacing_delay_ms || 2000;

const TASK_MAP = {
  T1: TASKS.T1,
  T2: TASKS.T2,
  T3: TASKS.T3,
  T4: TASKS.T4,
  T5: TASKS.T5,
  T6: TASKS.T6,
  T0: RECOVERY_TASK,
  T7: COLD_TASK
};

const TASK_KEYS = prereg.experimental_matrix.tasks;
const LANGUAGES = prereg.experimental_matrix.languages;

export async function runConfirmatoryBatch(seedStart = 1, seedEnd = 5) {
  process.env.OPENAI_MODEL = LOCKED_MODEL;
  const provider = createProvider({ mock: false });

  console.log(`================================================================`);
  console.log(`PREREG-AIN-LB-001 | FASE A CONFIRMATÓRIA`);
  console.log(`MANIFEST SHA-256    : ${preregSha256}`);
  console.log(`LOCKED MODEL        : ${LOCKED_MODEL} (Hardcoded via prereg)`);
  console.log(`SEMENTES ATIVAS     : S_${String(seedStart).padStart(2, '0')}..S_${String(seedEnd).padStart(2, '0')}`);
  console.log(`PACING              : ${PACING_DELAY_MS}ms entre chamadas`);
  console.log(`CROSS-MODEL FALLBACK: STRICTLY_FORBIDDEN`);
  console.log(`================================================================\n`);

  for (let sIdx = seedStart; sIdx <= seedEnd; sIdx++) {
    const seedNumber = 424240 + sIdx;
    const seedId = `S_${String(sIdx).padStart(2, '0')}`;
    const seedFile = path.join(OUT_DIR, `seed_${String(sIdx).padStart(3, '0')}.json`);
    
    console.log(`>>> [CONFIRMATORY] Starting Seed ${seedId} (int: ${seedNumber}) on ${LOCKED_MODEL}`);
    const seedResults = {
      protocol: 'PREREG-AIN-LB-001',
      status: 'CONFIRMATORY',
      preregSha256,
      seedId,
      seedNumber,
      model: LOCKED_MODEL,
      timestamp: new Date().toISOString(),
      units: []
    };

    let seedFailed = false;
    let seedFailReason = '';

    for (const taskId of TASK_KEYS) {
      if (seedFailed) break;
      const task = TASK_MAP[taskId];
      console.log(`  -> Task ${taskId} (${task.name})`);

      for (const lang of LANGUAGES) {
        const spec = task.spec(lang);
        await new Promise(r => setTimeout(r, PACING_DELAY_MS));

        try {
          const gen = await provider.generate(lang, task.id, spec, {
            mock: false,
            seed: String(seedNumber),
            model: LOCKED_MODEL
          });

          const ck = check(lang, gen.text);
          const codeHash = crypto.createHash('sha256').update(gen.text).digest('hex').slice(0, 16);

          const unit = {
            seedId,
            seedNumber,
            taskId,
            taskName: task.name,
            language: lang,
            model: LOCKED_MODEL,
            firstPassOk: Boolean(ck.ok),
            checkStage: ck.stage || (ck.ok ? 'OK' : 'FAIL'),
            checkReason: ck.reason || (ck.ok ? 'ok' : 'failed'),
            tokensTotal: gen.tokens,
            latencyMs: Math.round(gen.elapsedMs),
            codeLength: gen.text.length,
            codeHash,
            codeSnippet: gen.text.slice(0, 300)
          };

          seedResults.units.push(unit);
          console.log(`     [${lang.padEnd(4)}] ${ck.ok ? 'PASS' : 'FAIL'} | tok: ${String(gen.tokens).padStart(5)} | ${Math.round(gen.elapsedMs)}ms | ${ck.reason?.slice(0, 60) || 'ok'}`);
        } catch (unitErr) {
          seedFailed = true;
          seedFailReason = unitErr.message;
          console.error(`     [${lang.padEnd(4)}] CRITICAL INFRA ERROR ON ${LOCKED_MODEL}: ${unitErr.message}`);
          console.error(`     ==> SEED ${seedId} INVALIDATED! Aborting batch.`);
          break;
        }
      }
    }

    if (seedFailed) {
      if (fs.existsSync(seedFile)) fs.unlinkSync(seedFile);
      throw new Error(`Seed ${seedId} invalidated due to infrastructure failure: ${seedFailReason}`);
    }

    fs.writeFileSync(seedFile, JSON.stringify(seedResults, null, 2), 'utf8');
    console.log(`[CONFIRMATORY SAVED] Seed file written -> ${seedFile}\n`);
  }

  // Update Confirmatory Manifest
  const manifestFile = path.join(OUT_DIR, 'phase_a_manifest.json');
  const manifest = {
    protocol: 'PREREG-AIN-LB-001',
    status: 'CONFIRMATORY',
    preregSha256,
    fixedModel: LOCKED_MODEL,
    completedSeeds: Array.from({ length: seedEnd - seedStart + 1 }, (_, i) => `S_${String(seedStart + i).padStart(2, '0')}`),
    totalUnits: (seedEnd - seedStart + 1) * TASK_KEYS.length * LANGUAGES.length,
    updatedAt: new Date().toISOString()
  };
  fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2), 'utf8');
  console.log(`================================================================`);
  console.log(`CONFIRMATORY PHASE A BATCH S_${String(seedStart).padStart(2, '0')}..S_${String(seedEnd).padStart(2, '0')} COMPLETE.`);
  console.log(`================================================================`);
}

if (process.argv[1] && process.argv[1].endsWith('run_phase_a.mjs')) {
  const start = parseInt(process.argv[2], 10) || 1;
  const end = parseInt(process.argv[3], 10) || 5;
  runConfirmatoryBatch(start, end).catch(err => {
    console.error('Fatal Confirmatory Batch Error:', err);
    process.exit(1);
  });
}
