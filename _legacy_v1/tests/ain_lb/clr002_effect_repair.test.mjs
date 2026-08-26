import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getClr, linPath } from '../../src/lin_ain_lb_clr_load.mjs';
import { runClr002 } from './clr002_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const clr = getClr();

assert.equal(linPath(), 'src/lin_ain_lb_clr.lin');
assert.equal(clr.clr002Id(), 'CLR-002');
assert.equal(clr.clr002Name(), 'effect_repair');
assert.equal(clr.clr002Side(), 'LIN_only');
assert.equal(clr.clr002Operation(), 'database.write');
assert.equal(clr.clr002Effect(), 'io');
assert.equal(clr.clr002Capability(), 'database');
assert.equal(clr.clr002RequiredContext(), 'io');
assert.equal(clr.clr002CausalGraph(), 'operation->effect->capability->allowed_context');
assert.match(clr.clr002RepairPolicy(), /otherwise DENIED/);
assert.equal(clr.clr002RepairDecision(1, 1, 1, 0), 'CONDITIONAL');
assert.equal(clr.clr002RepairDecision(1, 1, 1, 1), 'APPLIED');
assert.equal(clr.clr002RepairDecision(1, 0, 1, 1), 'DENIED');
assert.equal(clr.clr002NoTargetMutation(), 1);
assert.equal(clr.clr002NoLlm(), 1);
assert.equal(clr.clr002NoDicel(), 1);
assert.match(clr.clr002Limitation(), /not_wired_into_compiler/);
assert.match(clr.clr002Paused(), /C1-C5_and_M006_paused/);

const report = runClr002();
assert.equal(report.id, 'CLR-002');
assert.equal(report.pure_declaration.detect, 'PASS');
assert.equal(report.pure_declaration.explain, 'PASS');
assert.equal(report.database_write_conflict.detect, 'PASS');
assert.equal(report.database_write_conflict.explain, 'PASS');
assert.equal(report.database_write_conflict.propose, 'PASS');
assert.equal(report.database_write_conflict.proposed_change.from, 'pure');
assert.equal(report.database_write_conflict.proposed_change.to, 'io');
assert.equal(report.database_write_conflict.apply, 'CONDITIONAL');
assert.equal(report.database_write_conflict.apply_approved, 'APPLIED');
assert.deepEqual(report.database_write_conflict.proof_before_apply, [
  'proposed_change',
  'semantic_proof',
  'invariant_preserved',
  'approval',
  'apply',
]);
assert.equal(report.database_write_conflict.semantic_hash_preserved, true);
assert.equal(report.no_target_mutation, true);
assert.equal(report.no_llm, 1);
assert.equal(report.no_dicel, 1);

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'clr002_runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"apply": "CONDITIONAL"/);
assert.match(cli.stdout, /"semantic_hash_preserved": true/);
assert.match(cli.stdout, /"no_target_mutation": true/);

console.log('ok ain_lb_clr CLR-002');
