import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../src/compiler.mjs';
import { compileLia, REAL_TARGETS } from '../src/multi_emit.mjs';
import { ingestFile, ingestJsonText, validateAgentIr, linPath } from '../src/lin_agent_ir_ingest_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fx = path.join(root, 'tests', 'fixtures', 'agent_ir');

const priLin = fs.readFileSync(path.join(root, 'src', 'lin_priority.lin'), 'utf8');
const priJs = compileLiaToJs(priLin, { exportMode: 'multiple' }).js;
const priTmp = path.join(os.tmpdir(), 'lin_priority_test.cjs');
fs.writeFileSync(priTmp, priJs, 'utf8');
const pri = createRequire(import.meta.url)(priTmp);
try { fs.rmSync(priTmp, { force: true }); } catch { /* ignore */ }

assert.equal(pri.priCount(), 6);
assert.equal(pri.p0().name, 'agent_ir');
assert.equal(pri.p0().status, 'SLICE1_DONE');
assert.equal(pri.p0().next, 'ain_lb_clr_001');
assert.equal(pri.p1().name, 'ain_lb_clr');
assert.equal(pri.p1().status, 'CLR-001');
assert.equal(pri.p1().lin_now, 'src/lin_ain_lb_clr.lin');
assert.equal(pri.p2().name, 'real_models');
assert.equal(pri.p2().status, 'WAIT');
assert.equal(pri.p3().name, 'win_lose');
assert.equal(pri.p4().name, 'm006');
assert.equal(pri.p4().status, 'DEFER');
assert.equal(pri.p4().next, 'not_Lean');
assert.equal(pri.p5().status, 'KEEP');
assert.equal(pri.sigilRequired(), 0);
assert.equal(pri.buildLean(), 0);
assert.equal(pri.redefineHash(), 0);
assert.equal(pri.inventScore(), 0);
assert.equal(pri.fakeAgents(), 0);
assert.equal(pri.expandFailClosedLangs(), 0);
assert.match(pri.pipeNow(), /CLR-001_LIN_harness/);
assert.match(pri.pipeNot(), /not deep_M006_before_AIN_LB/);
assert.match(pri.decisiveExperiment(), /DENY_write_without_io/);
assert.match(pri.hypAinLb(), /H_CLR001/);
assert.equal(pri.priById('P0').lin_now, 'src/lin_agent_ir_ingest.lin');
assert.equal(pri.priById('P1').lin_now, 'src/lin_ain_lb_clr.lin');

assert.equal(linPath(), 'src/lin_agent_ir_ingest.lin');

const ok = ingestFile(path.join(fx, 'ok.json'));
assert.equal(ok.ok, 1);
assert.equal(ok.status, 'ACCEPT');
assert.equal(ok.intent, 'add_cache_layer');
assert.equal(ok.target, 'UserRepository');
assert.equal(ok.module_ref, 'UserRepository');
assert.equal(ok.hash_nucleus, 'EXISTING_semantic_hash');
assert.equal(ok.redefine, 0);
assert.equal(ok.sigil_required, 0);
assert.equal(ok.proof, 'AGENT_IR_VALID');
assert.deepEqual(ok.constraints, ['latency < 20ms', 'no_data_loss']);
assert.deepEqual(ok.allowed_effects, ['memory']);

const missIntent = ingestFile(path.join(fx, 'missing_intent.json'));
assert.equal(missIntent.ok, 0);
assert.equal(missIntent.status, 'REJECT');
assert.equal(missIntent.field, 'intent');
assert.match(missIntent.message, /REJECTED AGENT_IR/);
assert.match(missIntent.message, /Field: intent/);
assert.match(missIntent.message, /Missing: non-empty intent/);
assert.match(missIntent.message, /repairs:/);

const missTarget = ingestFile(path.join(fx, 'missing_target.json'));
assert.equal(missTarget.ok, 0);
assert.equal(missTarget.field, 'target');
assert.match(missTarget.message, /repairs:/);

const denied = ingestFile(path.join(fx, 'storage_write_no_io.json'));
assert.equal(denied.ok, 0);
assert.equal(denied.status, 'DENIED');
assert.equal(denied.node, 'Storage.write');
assert.equal(denied.missing, 'io');
assert.match(denied.message, /DENIED AGENT_IR/);
assert.match(denied.message, /Node: Storage.write/);
assert.match(denied.message, /Missing: io/);
assert.match(denied.message, /add io to allowed_effects/);

const allowed = ingestFile(path.join(fx, 'storage_write_with_io.json'));
assert.equal(allowed.ok, 1);
assert.equal(allowed.status, 'ACCEPT');
assert.equal(allowed.module_ref, 'Storage');

const notObj = ingestFile(path.join(fx, 'not_object.json'));
assert.equal(notObj.ok, 0);
assert.equal(notObj.field, 'root');
assert.match(notObj.message, /do not pass text LIN/);

const badJson = ingestFile(path.join(fx, 'invalid.json'));
assert.equal(badJson.ok, 0);
assert.equal(badJson.field, 'json');
assert.match(badJson.message, /valid JSON/);

const empty = ingestJsonText('');
assert.equal(empty.ok, 0);
assert.equal(empty.field, 'json');

const viaObj = validateAgentIr({
  intent: 'ping',
  target: 'AuthService',
  constraints: [],
  allowed_effects: ['pure'],
});
assert.equal(viaObj.ok, 1);
assert.equal(viaObj.module_ref, 'AuthService');

const cli = path.join(root, 'scripts', 'lin_agent_ir_ingest.mjs');
const cliOk = spawnSync(process.execPath, [cli, path.join(fx, 'ok.json')], { encoding: 'utf8' });
assert.equal(cliOk.status, 0);
assert.match(cliOk.stdout, /"status": "ACCEPT"/);

const cliDeny = spawnSync(process.execPath, [cli, path.join(fx, 'storage_write_no_io.json')], { encoding: 'utf8' });
assert.equal(cliDeny.status, 1);
assert.match(cliDeny.stdout, /DENIED AGENT_IR/);

const bin = path.join(root, 'bin', 'lin.mjs');
const binOk = spawnSync(process.execPath, [bin, 'agent-ir', path.join(fx, 'ok.json')], { encoding: 'utf8' });
assert.equal(binOk.status, 0);
assert.match(binOk.stdout, /"module_ref": "UserRepository"/);

const tiny = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=agent_ir_exp
~G{?=if #=for ^=ret :else}
!add(a,b){^a+b}
=ex{add}`;
for (const target of REAL_TARGETS) {
  const r = compileLia(tiny, { target });
  assert.ok(r.code, `7lang empty emit target=${target}`);
}

console.log('ok lin_agent_ir_ingest');
