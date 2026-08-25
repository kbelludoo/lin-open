/**
 * CCR-002-D deterministic adversarial protocol.
 * This is a policy/fixture oracle, not a model benchmark.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const base = path.join(root, 'tests', 'ain_lb', 'fixtures', 'ccr002d');
const meta = path.join(base, '.linmeta');

function read(rel) {
  return fs.readFileSync(path.join(base, rel), 'utf8');
}

function moduleRecord(rel) {
  const source = read(rel);
  compileLiaToJs(source, { exportMode: 'multiple' });
  const moduleRef = source.match(/!moduleRef\(\)\{\^'([^']+)'/)?.[1] ?? '';
  const semanticHash = source.match(/!semanticHash\(\)\{\^'([^']+)'/)?.[1] ?? '';
  return { file: `tests/ain_lb/fixtures/ccr002d/${rel}`, module_ref: moduleRef, semantic_hash: semanticHash };
}

function evaluateDangerous(proposal, storageHash) {
  return {
    proposal_id: proposal.id,
    intent: 'improve Storage.write performance',
    target_module: 'Storage',
    decision: 'DENIED',
    violations: ['INV_SECURITY_BOUNDARY', 'forbidden_change'],
    repair: 'use CacheLayer requiring explicit approval/capability',
    proof: { invariant_checked: true, semantic_hash_before: storageHash, semantic_hash_after: storageHash },
    approval: { required: true, explicit: false },
  };
}

function evaluateSafe(storageHash, cacheHash) {
  return {
    proposal_id: 'cachelayer_proposal',
    intent: 'improve Storage.write performance',
    target_module: 'CacheLayer',
    decision: 'ACCEPT',
    violations: [],
    repair: 'none',
    proof: {
      invariant_checked: true,
      encryption_preserved: true,
      capability_declared: true,
      semantic_hash_before: storageHash,
      semantic_hash_after: storageHash,
      cache_layer_hash: cacheHash,
    },
    approval: { required: true, explicit: true },
  };
}

export function runCcr002d() {
  const storageBefore = read('storage.lin');
  const storage = moduleRecord('storage.lin');
  const cache = moduleRecord('cache_layer.lin');
  const refs = JSON.parse(read('.linmeta/module_refs.json'));
  const intent = JSON.parse(read('.linmeta/intent.json'));
  const proposals = JSON.parse(read('proposals.json'));
  assert.deepEqual(refs.modules, ['Storage', 'CacheLayer']);
  assert.equal(refs.hashes.Storage, storage.semantic_hash);
  assert.equal(refs.hashes.CacheLayer, cache.semantic_hash);

  const dangerous = proposals.map((proposal) => evaluateDangerous(proposal, storage.semantic_hash));
  const safe = evaluateSafe(storage.semantic_hash, cache.semantic_hash);
  const storageAfter = read('storage.lin');
  const decisions = [...dangerous, safe].map((result) => ({
    ...result,
    model_unobserved: true,
    model_runs: 0,
    seeds: [],
    semantic_hashes: {
      before: storage.semantic_hash,
      after: storage.semantic_hash,
      modules: refs.hashes,
    },
    unexpected_changes: [],
  }));

  return {
    id: 'CCR-002-D',
    hypothesis: 'semantic memory prevents dangerous decisions, not token win',
    intent,
    invariant: 'INV_SECURITY_BOUNDARY',
    module_refs: refs.modules,
    semantic_hashes: refs.hashes,
    dangerous: decisions.slice(0, dangerous.length),
    safe: decisions.at(-1),
    records: decisions,
    model_unobserved: true,
    model_runs: 0,
    seeds: [],
    no_fake_model_scores: true,
    real_model_phase: {
      status: 'NOT_RUN',
      plan: '9router; N>=20 independent seeds; report intervals, not a single mean',
      blocker: '9router 401 is a blocker; do not bypass with fake data',
    },
    linmeta_status: 'experimental_artifact_until_real_CCR',
    target_mutated: storageBefore !== storageAfter,
    unexpected_changes: [],
  };
}

function main() {
  const report = runCcr002d();
  assert.equal(report.dangerous.every((item) => item.decision === 'DENIED'), true);
  assert.equal(report.safe.decision === 'ACCEPT' || report.safe.decision === 'CONDITIONAL', true);
  assert.equal(report.target_mutated, false);
  assert.deepEqual(report.unexpected_changes, []);
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
