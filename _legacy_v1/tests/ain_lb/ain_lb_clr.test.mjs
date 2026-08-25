import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../../src/compiler.mjs';
import { getClr, linPath } from '../../src/lin_ain_lb_clr_load.mjs';
import { runClr001 } from './runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

const clr = getClr();
assert.equal(linPath(), 'src/lin_ain_lb_clr.lin');
assert.equal(clr.clrId(), 'CLR-001');
assert.equal(clr.clrName(), 'context_loss_recovery');
assert.equal(clr.side(), 'LIN_only');
assert.equal(clr.phaseCount(), 3);
assert.equal(clr.phaseAt(0).name, 'build_payments');
assert.equal(clr.phaseAt(1).name, 'wipe_chat');
assert.equal(clr.inventScore(), 0);
assert.equal(clr.fakeCurve(), 0);
assert.equal(clr.fakeAgents(), 0);
assert.equal(clr.redefineHash(), 0);
assert.equal(clr.windowMeasured(), 0);
assert.equal(clr.hashNucleus(), 'EXISTING_semantic_hash');
assert.equal(clr.chatAfterWipe(), 0);
assert.equal(clr.wireExisting(), 1);
assert.equal(clr.ainLbSpec(), 'spec/AIN-LB.rulel');
assert.equal(clr.expectedCount(), 6);
assert.match(clr.hyp(), /H_CLR001/);
assert.match(clr.falsifyIf(), /deny_fixture_status_ACCEPT/);
assert.match(clr.windowSpec(), /8k\|16k\|32k\|128k/);
assert.match(clr.keepFields(), /module_ref/);
assert.match(clr.cli(), /agent-ir/);
assert.equal(clr.caseCount(), 5);
assert.equal(clr.regCount(), 16);
assert.equal(clr.realModelRound(), 'SKIP_9ROUTER_401');
assert.equal(clr.ninerouterBlock(), 0);
assert.equal(clr.deepM006(), 0);
assert.equal(clr.hashVia(), 'EXISTING_semantic_hash');
assert.equal(clr.hashImpl(), 'src/content_hash.lin');
assert.equal(clr.focus(), 'agent_variability');
assert.equal(clr.theoryPass(), 0);
assert.equal(clr.keyMetric(), 'repair_loop_length');
assert.match(clr.keyMetricPath(), /LIN_DENIED/);
assert.equal(clr.metricCount(), 5);
assert.equal(clr.metricAt(4), 'repair_loop_length_model_DENIED_causal_repair_ACCEPT');
assert.equal(clr.c4Tests(), 'semantic_equivalence_EXISTING_semantic_hash_not_name_clash');
assert.equal(clr.qCount(), 3);
assert.equal(clr.qAnswered(), 0);
assert.equal(clr.q0Answer(), '');
assert.match(clr.q0(), /valid Agent IR/);
assert.match(clr.q1(), /LIN explain/);
assert.match(clr.q2(), /iterations to ACCEPT/);
assert.equal(clr.mechRepair0(), 'add io to allowed_effects');
assert.equal(clr.isMechRepair('add io to allowed_effects | remove Storage.write'), 1);
assert.equal(clr.firstMechRepair('add io to allowed_effects | remove Storage.write'), 'add io to allowed_effects');
assert.equal(clr.caseAt(0).name, 'capability_violation');
assert.equal(clr.caseAt(1).name, 'contract_violation');
assert.equal(clr.caseAt(2).name, 'dependency_confusion');
assert.equal(clr.caseAt(3).name, 'semantic_duplicate');
assert.equal(clr.caseAt(4).name, 'architecture_recovery');
assert.equal(clr.caseAt(0).expect, 'DENIED');
assert.equal(clr.caseAt(4).expect, 'ACCEPT');
assert.equal(clr.emptyReg().model, '');
assert.equal(clr.emptyReg().provider, '');
assert.equal(clr.emptyReg().run_id, '');
assert.equal(clr.emptyReg().decision, '');
assert.equal(clr.emptyReg().input_task_hash, '');
assert.equal(clr.emptyReg().agent_ir_hash, '');
assert.deepEqual(clr.emptyReg().violations, []);
assert.match(clr.regFields(), /run_id\|timestamp\|model\|provider/);
assert.match(clr.regFields(), /repair_attempts\|tokens_input\|tokens_output\|latency/);

const phase0 = path.join(root, 'tests', 'ain_lb', 'fixtures', 'phase0');
for (const name of ['user', 'balance', 'transfer', 'audit', 'perms', 'logs', 'catalog', 'contracts']) {
  const lin = fs.readFileSync(path.join(phase0, `${name}.lin`), 'utf8');
  const { js } = compileLiaToJs(lin, { exportMode: 'multiple' });
  const tmp = path.join(os.tmpdir(), `ain_lb_${name}_${process.pid}.cjs`);
  fs.writeFileSync(tmp, js, 'utf8');
  const mod = createRequire(import.meta.url)(tmp);
  try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }
  if (name === 'transfer') {
    assert.equal(mod.moduleRef(), 'Transfer');
    assert.equal(mod.approvalThreshold(), 10000);
    assert.equal(mod.needsApproval(10001), 1);
    assert.equal(mod.needsApproval(9999), 0);
  } else if (name === 'catalog') {
    assert.equal(mod.modCount(), 6);
    assert.equal(mod.hashNucleus(), 'EXISTING_semantic_hash');
    assert.equal(mod.redefineHash(), 0);
  } else if (name === 'contracts') {
    assert.match(mod.approvalRule(), /transfer_gt_10000/);
  } else {
    assert.ok(mod.moduleRef(), name);
  }
}

const report = runClr001();
assert.equal(report.id, 'CLR-001');
assert.equal(report.invent_score, 0);
assert.equal(report.fake_agents, 0);
assert.equal(report.fake_curve, 0);
assert.equal(report.redefine_hash, 0);
assert.equal(report.phase0.correct_files, 6);
assert.equal(report.phase0.total, 6);
assert.equal(report.phase1_wipe.chat_memory, 0);
assert.equal(report.window_curve.measured, 0);
assert.equal(report.ingest[0].status, 'ACCEPT');
assert.equal(report.ingest[0].intent, 'add_international_payments');
assert.equal(report.ingest[0].module_ref, 'Transfer');
assert.equal(report.ingest[1].status, 'DENIED');
assert.equal(report.ingest[1].node, 'Storage.write');
assert.equal(report.ingest[1].missing, 'io');
assert.match(report.ingest[1].message, /DENIED AGENT_IR/);
assert.match(report.ingest[1].repairs, /add io to allowed_effects/);
assert.equal(report.adversarial.runs[0].status, 'ACCEPT');
assert.equal(report.adversarial.runs[1].status, 'DENIED');
assert.equal(report.adversarial.runs[2].status, 'ACCEPT');
assert.equal(report.hypothesis_holds_on_lin_gate, 1);
assert.equal(report.five_cases_hold, 1);
assert.equal(report.cases.length, 5);
assert.equal(report.cases[0].status, 'DENIED');
assert.equal(report.cases[0].node, 'Storage.write');
assert.equal(report.cases[0].missing, 'io');
assert.match(report.cases[0].repairs, /add io to allowed_effects/);
assert.equal(report.cases[1].status, 'DENIED');
assert.equal(report.cases[1].node, 'Transfer.ensure');
assert.equal(report.cases[1].missing, 'transfer_gt_10000_needs_approval');
assert.ok(report.cases[2].status === 'DENIED' || report.cases[2].status === 'REJECT');
assert.equal(report.cases[2].node, 'module');
assert.equal(report.cases[3].status, 'DENIED');
assert.equal(report.cases[3].node, 'INV_SEMANTIC_DUP');
assert.equal(report.cases[3].semantic_hash.same_hash, 1);
assert.equal(report.cases[3].semantic_hash.names_differ, 1);
assert.equal(report.cases[3].semantic_hash.hash_via, 'EXISTING_semantic_hash');
assert.equal(report.cases[3].semantic_hash.note, 'semantic_equivalence_not_name_clash');
assert.equal(report.c4_tests, 'semantic_equivalence_EXISTING_semantic_hash_not_name_clash');
assert.equal(report.cases[4].status, 'ACCEPT');
assert.equal(report.cases[4].intent, 'add_country_limits');
assert.equal(report.real_model_round, 'SKIP_9ROUTER_401');
assert.equal(report.ninerouter_block, 0);
assert.equal(report.deep_m006, 0);
assert.equal(report.hash_via, 'EXISTING_semantic_hash');
assert.equal(report.key_metric, 'repair_loop_length');
assert.equal(report.repair_loop.converged, 1);
assert.equal(report.repair_loop.repair_loop_length, 1);
assert.equal(report.repair_loop.status, 'ACCEPT');
assert.equal(report.repair_loop.invented_llm, 0);
assert.equal(report.repair_loop.source, 'mechanical_no_model');
assert.equal(report.repair_loop.steps[0].status, 'DENIED');
assert.equal(report.repair_loop.steps[0].applied, 'add io to allowed_effects');
assert.equal(report.repair_loop.steps[1].status, 'ACCEPT');
assert.equal(report.questions.answered, 0);
assert.equal(report.questions.items.length, 3);
assert.equal(report.questions.items[0].answer, '');
assert.deepEqual(report.registry_fields, [
  'run_id', 'timestamp', 'model', 'provider', 'temperature', 'seed',
  'input_task_hash', 'repo_hash_before', 'repo_hash_after', 'agent_ir_hash',
  'decision', 'violations', 'repair_attempts',
  'tokens_input', 'tokens_output', 'latency',
]);
assert.equal(report.registry_template.model, '');
assert.equal(report.registry_template.provider, '');
assert.equal(report.registry_template.temperature, '');
assert.equal(report.registry_template.seed, '');
assert.equal(report.registry_template.run_id, '');
assert.equal(report.registry_template.input_task_hash, '');
assert.equal(report.registry_template.repo_hash_before, '');
assert.equal(report.registry_template.repo_hash_after, '');
assert.equal(report.registry_template.agent_ir_hash, '');
assert.equal(report.registry_template.decision, '');
assert.deepEqual(report.registry_template.violations, []);
assert.equal(report.registry_template.repair_attempts, '');
assert.equal(report.registry_template.tokens_input, '');
assert.equal(report.registry_template.tokens_output, '');
assert.equal(report.registry_template.latency, '');
assert.ok(report.compression.present.includes('module_ref'));
assert.ok(report.compression.present.includes('semantic_hash'));
assert.equal(report.compression.redefine, 0);
const blob = JSON.stringify(report);
assert.equal(blob.includes('AI_DEVELOPMENT_SCORE'), false);
assert.equal(/85\s*%/.test(blob), false);
assert.equal(/35\s*%/.test(blob), false);
assert.equal(blob.includes('gpt-4'), false);
assert.equal(blob.includes('claude'), false);

const cli = spawnSync(process.execPath, [path.join(root, 'tests', 'ain_lb', 'runner.mjs')], {
  encoding: 'utf8',
  cwd: root,
});
assert.equal(cli.status, 0, cli.stderr);
assert.match(cli.stdout, /"status": "ACCEPT"/);
assert.match(cli.stdout, /"status": "DENIED"/);
assert.equal(cli.stdout.includes('AI_DEVELOPMENT_SCORE'), false);

console.log('ok ain_lb_clr CLR-001');
