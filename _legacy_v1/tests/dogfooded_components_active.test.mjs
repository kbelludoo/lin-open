/**
 * Test: Dogfooded execution of newly connected LIN modules:
 * lin_effects, refinement_types, lin_rules_engine, lin_actors
 */
import assert from 'node:assert/strict';
import { inferEffects, validateEffects, emitEffectAnnotation } from '../src/lin_effects_load.mjs';
import { parseRefinement, emitRangeGuard, emitNonEmptyGuard } from '../src/refinement_types_load.mjs';
import { createKnowledgeBase, assertFact, assertRule, queryFact, applyRules, inferRequirements, checkConstraints, kbToLin } from '../src/lin_rules_engine_load.mjs';
import { spawnActor, createSupervisor } from '../src/lin_actors_load.mjs';

// 1. lin_effects
const eff1 = inferEffects('const fs = require("fs"); fs.readFileSync("x");', []);
assert.ok(eff1.includes('io'), 'Should infer IO effect');

const effPure = inferEffects('const a = 1 + 2; return a;', []);
assert.ok(effPure.includes('pure'), 'Should infer pure effect');

const viol = validateEffects(['pure'], ['io', 'state']);
assert.ok(viol.includes('io') && viol.includes('state'), 'Should detect effect violations');

const ann = emitEffectAnnotation(['io', 'async'], 'ts');
assert.equal(ann, '/* @effects: io, async */');

// 2. refinement_types
const ref1 = parseRefinement('int{0..100}');
assert.equal(ref1.base, 'int');
assert.equal(ref1.constraints[0].kind, 'range');
assert.equal(ref1.constraints[0].min, 0);
assert.equal(ref1.constraints[0].max, 100);

const refNonEmpty = parseRefinement('list{non_empty}');
assert.equal(refNonEmpty.base, 'list');
assert.equal(refNonEmpty.constraints[0].kind, 'non_empty');

const guard = emitRangeGuard('x', 0, 100, 'ts');
assert.ok(guard.includes('throw new RangeError'), 'Range guard emitted');

// 3. lin_rules_engine
const kb = createKnowledgeBase();
assertFact(kb, 'A', 'requires', 'B');
assertFact(kb, 'B', 'requires', 'C');
const reqs = inferRequirements(kb, 'A');
assert.ok(reqs.includes('B') && reqs.includes('C'), 'Transitive requirements inferred');

// 4. lin_actors
const actor = spawnActor('worker', null, { refcap: 'val' });
assert.equal(actor.name, 'worker');
assert.equal(actor.alive, true);
const sendRes = actor.send({ task: 'compute' });
assert.equal(sendRes.ok, true);

console.log('ok dogfooded_components_active_test');
