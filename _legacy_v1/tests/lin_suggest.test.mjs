import assert from 'node:assert/strict';
import { getSuggest } from '../src/lin_suggest_load.mjs';
import { getAgentIr } from '../src/lin_agent_ir_load.mjs';

const mod = getSuggest();

assert.equal(mod.suggestCount(), 8);
assert.equal(mod.suggestIds(), 'S001|S002|S003|S004|S005|S006|S007|S008');

const keys = ['id', 'goal', 'why_for_ai', 'proof_or_gate', 'next_repair', 'status'];
for (let i = 0; i < 8; i++) {
  const row = mod.suggestionAt(i);
  for (const k of keys) {
    assert.ok(row[k], `missing ${k} at ${i}`);
  }
}

const s002 = mod.suggestById('S002');
assert.equal(s002.status, 'SLICE1');
assert.match(s002.next_repair, /refine b:int\{>0\}/);
assert.match(s002.next_repair, /require b>0/);

const s001 = mod.suggestById('S001');
assert.equal(s001.status, 'DONE');
assert.match(s001.proof_or_gate, /LIN_EMIT_FAIL_CLOSED/);

const blob = mod.suggestAllLines();
assert.match(blob, /id=S002/);
assert.match(blob, /id=S007/);
assert.match(blob, /id=S008/);
assert.equal(mod.agreeAiCriteria(), 1);
assert.equal(mod.agreeCompact(), 1);
assert.equal(mod.compactMustNotLoseInfo(), 1);
assert.equal(mod.redefineHash(), 0);
assert.match(mod.stackLine(), /IA\|LIN/);
assert.match(mod.pipeline(), /goal->constraints/);
assert.match(mod.irNative(), /intent->LIN_semantic_IR->code/);
assert.match(mod.semCompressWhy(), /not=text_zip/);

assert.equal(mod.agreeRank(), 1);
assert.equal(mod.mechCount(), 6);
assert.equal(mod.mechAt(0).mechanism, 'rules_plus_causal_diagnosis');
assert.equal(mod.mechAt(0).stars, 5);
assert.equal(mod.mechAt(0).copy_language, 0);
assert.equal(mod.mechAt(1).mechanism, 'invariants_plus_small_proof_obligations');
assert.equal(mod.mechAt(2).mechanism, 'ast_as_data_declarative_transform');
assert.equal(mod.mechAt(3).mechanism, 'types_that_carry_meaning');
assert.equal(mod.mechAt(4).mechanism, 'safe_execution_ownership_no_ub');
assert.equal(mod.mechAt(5).mechanism, 'scientific_math_first_class');

const intent = mod.intentShape();
assert.ok('objective' in intent && 'constraints' in intent);
assert.ok('allowed_changes' in intent && 'forbidden' in intent);
assert.match(mod.intentWhy(), /intent\{objective,constraints,allowed_changes,forbidden\}/);
assert.match(mod.rankAllLines(), /rank=1 mechanism=rules_plus_causal_diagnosis/);
assert.equal(mod.agreeAgentLangs(), 1);
assert.equal(mod.agentIrPath(), 'src/lin_agent_ir.lin');
assert.match(mod.archThree(), /LIN_Agent_IR/);

const ir = getAgentIr();

assert.equal(ir.agreeAgentLangs(), 1);
assert.equal(ir.forbidShrink(), 1);
assert.equal(ir.layerCount(), 3);
assert.equal(ir.layerAt(0).name, 'LIN');
assert.equal(ir.layerAt(0).shrink_lin_to_dsl, 0);
assert.equal(ir.layerAt(1).name, 'LIN_Agent_IR');
assert.equal(ir.layerAt(2).name, 'LIN_Proof_Layer');
assert.equal(ir.absCount(), 6);
assert.equal(ir.absAt(0).absorb_from, 'edict');
assert.equal(ir.absAt(0).stars, 5);
assert.equal(ir.absAt(0).copy_language, 0);
assert.equal(ir.absAt(1).absorb_from, 'mog');
assert.equal(ir.absAt(2).absorb_from, 'lisp');
assert.equal(ir.absAt(3).absorb_from, 'prolog');
assert.equal(ir.absAt(4).absorb_from, 'lingo');
assert.equal(ir.absAt(5).absorb_from, 'ilo');
assert.equal(ir.absAt(5).stars, 3);
assert.equal(ir.openSpace(), 'IA thinks, mutates, proves BEFORE emit');
assert.match(ir.agentLoop(), /prove/);
assert.match(ir.absAllLines(), /arch=LIN\+LIN_Agent_IR\+LIN_Proof_Layer/);
assert.equal(ir.agreeAiCriteria(), 1);
assert.equal(ir.agreeCompact(), 1);
assert.equal(ir.compactMustNotLoseInfo(), 1);
assert.equal(ir.redefineHash(), 0);
assert.equal(ir.copyLanguage(), 0);
assert.equal(ir.notNeuralNetInternals(), 1);
assert.equal(ir.stackCount(), 4);
assert.equal(ir.stackAt(0).name, 'IA');
assert.equal(ir.stackAt(1).name, 'LIN');
assert.equal(ir.stackAt(2).name, 'emit7');
assert.equal(ir.stackAt(3).name, 'machine');
assert.match(ir.stackLine(), /emit7/);
assert.match(ir.bitcoinAnalogy(), /PROTOCOL/);
assert.match(ir.agentComplexityTest(), /AGENTS/);
assert.match(ir.aiCriteria(), /semantic_compression/);
assert.match(ir.notHumanCriteria(), /ergonomics/);
assert.equal(ir.decisionShape().proof_required, '');
const dec = ir.aiDecision('unproven_div', 'INV_REFINEMENT_SOUND', 'block_emit');
assert.equal(dec.condition, 'unproven_div');
assert.equal(dec.action, 'block_emit');
assert.equal(ir.pipeCount(), 7);
assert.equal(ir.pipeAt(0), 'goal');
assert.equal(ir.pipeAt(6), 'execute');
assert.equal(ir.haveCount(), 7);
assert.equal(ir.haveAt(6).piece, 'proof_gate');
assert.equal(ir.missCount(), 4);
assert.equal(ir.missAt(0).invented_proofs, 0);
assert.equal(ir.semCompress().codec, 'meaning');
assert.equal(ir.semCompress().not, 'text_zip');
assert.equal(ir.semRefAuth().id, 'AuthService');
assert.equal(ir.semRefAuth().not_name_repeat, 1);
const mem = ir.memByHash('AuthService', 'EXISTING_semantic_hash');
assert.equal(mem.redefine, 0);
assert.match(ir.hashNucleusPath(), /UNTOUCHED/);
assert.equal(ir.incrStateShape().project_model, 'HASH');
assert.match(ir.irNative(), /intent->LIN_semantic_IR->code/);
assert.match(ir.notLegacyPipe(), /not code->AST->IR/);
assert.match(ir.advantageHave(), /content_hash/);
assert.equal(ir.ingestPath(), 'src/lin_agent_ir_ingest.lin');
assert.equal(ir.priorityPath(), 'src/lin_priority.lin');

import { priCount, priById } from '../src/lin_priority_load.mjs';
import { coreHostLang, coreBanner } from '../src/lin_core_phase1_load.mjs';

assert.equal(priCount(), 6);
const p0 = priById('P0');
assert.equal(p0.status, 'SLICE1_DONE');
assert.equal(coreHostLang(), 'rust');
assert.match(coreBanner(), /phase=ast_parser/);

console.log('ok lin_suggest');
