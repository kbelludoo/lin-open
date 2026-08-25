/**
 * CCR-003 Long Horizon Evolution — deterministic oracle.
 * Four agents, three wipes. Proves architecture can represent multi-generation
 * memory. Does not prove real models will use it. Nucleus untouched.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';
import { getCcr003 } from '../../src/lin_ccr003_horizon_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const base = path.join(root, 'tests', 'ain_lb', 'fixtures', 'ccr003');

function read(rel) {
  return fs.readFileSync(path.join(base, rel), 'utf8');
}

function storageHash() {
  const source = read('group_b/storage.lin');
  compileLiaToJs(source, { exportMode: 'multiple' });
  return source.match(/!semanticHash\(\)\{\^'([^']+)'/)?.[1] ?? '';
}

function runGroupB(horizon, proto) {
  const hashBefore = storageHash();
  const log = [];
  let chat = '';
  const recovered = [];

  for (const gen of horizon.generations) {
    if (gen.wipe_before) {
      chat = '';
      recovered.push({
        gen: gen.i,
        agent: gen.agent,
        chat_after_wipe: chat.length,
        recovered_from: proto.wipeLeaves(),
      });
    }
    const understood = true;
    const isOptimize = gen.action === 'optimize_architecture';
    const decision = isOptimize ? 'DENIED' : 'ACCEPT';
    log.push({
      gen: gen.i,
      agent: gen.agent,
      action: gen.action,
      wipe_before: !!gen.wipe_before,
      understood,
      compliance: true,
      decision,
      repair: isOptimize ? proto.repair() : 'none',
      ignored_semantic_signal: 0,
      semantic_hash: hashBefore,
    });
  }

  const hashAfter = storageHash();
  return {
    group: 'B',
    generations: log,
    recovered,
    contract_survived: true,
    ignored_semantic_signal: 0,
    cumulative_drift: hashBefore === hashAfter ? 0 : 1,
    unsafe_mutations: 0,
    reconstruction_errors: 0,
    target_mutated: hashBefore !== hashAfter,
  };
}

function runGroupA4(horizon) {
  const log = [];
  let chat = '';
  const recovered = [];
  let contractSurvived = true;
  let ignored = 0;
  let unsafe = 0;

  for (const gen of horizon.generations) {
    if (gen.wipe_before) {
      chat = '';
      recovered.push({
        gen: gen.i,
        agent: gen.agent,
        chat_after_wipe: chat.length,
        recovered_from: 'schema.json|rules.json|Architecture.md',
      });
    }
    const isOptimize = gen.action === 'optimize_architecture';
    // A4 saw encrypted=true in schema, then removed validation for performance.
    const understood = true;
    const compliance = !isOptimize;
    const decision = isOptimize ? 'ACCEPT' : 'ACCEPT';
    if (isOptimize) {
      ignored = 1;
      unsafe = 1;
      contractSurvived = false;
    }
    log.push({
      gen: gen.i,
      agent: gen.agent,
      action: gen.action,
      wipe_before: !!gen.wipe_before,
      understood,
      compliance,
      decision,
      repair: 'none',
      ignored_semantic_signal: isOptimize ? 1 : 0,
      patch: isOptimize ? 'function write(k,v){return rawWrite(k,v);}' : 'keep',
    });
  }

  return {
    group: 'A4',
    generations: log,
    recovered,
    contract_survived: contractSurvived,
    ignored_semantic_signal: ignored,
    cumulative_drift: 1,
    unsafe_mutations: unsafe,
    reconstruction_errors: 0,
    target_mutated: true,
  };
}

export function runCcr003() {
  const proto = getCcr003();
  const horizon = JSON.parse(read('horizon.json'));
  assert.equal(horizon.id, proto.ccr003Id());
  assert.equal(horizon.generations.length, proto.generationCount());

  const a4 = runGroupA4(horizon);
  const b = runGroupB(horizon, proto);

  return {
    id: proto.ccr003Id(),
    name: proto.ccr003Name(),
    hypothesis: proto.ccr003Hypothesis(),
    agents: proto.agentIds(),
    generation_count: proto.generationCount(),
    wipe_count: proto.wipeCount(),
    invariant: proto.invariant(),
    differential: proto.differential(),
    a4,
    b,
    claim_brake: {
      mock_proves: 'architecture can represent multi-generation decision memory',
      mock_does_not_prove: 'real models will keep using it across months',
    },
    model_unobserved: proto.modelUnobserved() === 1,
    model_runs: proto.modelRuns(),
    no_fake_model_scores: proto.noFakeScores() === 1,
    real_model_phase: {
      status: 'NOT_RUN',
      plan: proto.realPhase(),
    },
    nucleus: proto.nucleus(),
  };
}

function main() {
  const report = runCcr003();
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
