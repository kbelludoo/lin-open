/**
 * Test: Full Dogfooding & Integration Test for all src/*.lin components.
 * Exercises loaders and verifies live on-the-fly compilation and execution.
 */
import assert from 'node:assert/strict';

import { inferType, inferParamType, inferReturnType, inferFnSignature, isPureBody, unifyTypes } from '../src/lin_type_infer_load.mjs';
import { astNode, astFn, astIf, astFor, astAssign, astReturn, astCall, astLiteral, astIdent, walkAst, transformAst, astToLin, astBodyToLin, astToJson, astFromJson } from '../src/lin_ast_data_load.mjs';
import { parseSemanticBlock, parseSection, parseInputTypes, parseRules, parseConstraints, parseEffects, parseTarget } from '../src/semantic_parser_load.mjs';
import { decideTarget, selectByProfile, validateConstraints, executeRules, evalSimpleExpr } from '../src/semantic_runtime_load.mjs';
import { gate11_taxonomy } from '../src/gate11_taxonomy_load.mjs';
import { extractNativeFns, extractPy, extractGo, extractC, extractRs, extractJava } from '../src/extract_native_load.mjs';
import { b6_logic_oracle } from '../src/b6_logic_oracle_load.mjs';
import { b6_logic_v2_generator } from '../src/b6_logic_v2_generator_load.mjs';
import { compareTargets } from '../src/compare_targets_load.mjs';
import { emitHostPick } from '../src/emit_host_pick_load.mjs';
import { emitMojo } from '../src/emit_mojo_load.mjs';
import { emitSql } from '../src/emit_sql_load.mjs';
import { emitWat } from '../src/emit_wat_load.mjs';
import { cloneLinFullRepoGate } from '../src/clone_lin_full_repo_gate_load.mjs';

// 1. lin_type_infer
assert.equal(inferType('42'), 'int');
assert.equal(inferType('"hello"'), 'str');
assert.equal(inferType('true'), 'bool');
assert.equal(inferType('[1,2,3]'), 'list');
assert.equal(inferParamType('len', []), 'int');
assert.equal(inferParamType('str', []), 'str');
assert.equal(isPureBody('const a = 1; return a;'), true);
assert.equal(isPureBody('console.log(1);'), false);

// 2. lin_ast_data
const node = astNode('literal', 42, []);
assert.equal(node.type, 'literal');
assert.equal(node.value, 42);
const fnNode = astFn('testFn', [astNode('ident', 'x', [])], [astReturn(42)]);
assert.equal(fnNode.type, 'fn');
assert.equal(fnNode.value, 'testFn');

// 3. semantic_parser
const block = parseSemanticBlock('@CONCEPT TestBlock {\nINPUT: { x: int }\nEFFECT: { pure }\n}');
assert.equal(block.concept, 'TestBlock');
assert.ok(block.input.length > 0);

// 4. semantic_runtime
const prof = selectByProfile('performance', ['rust', 'ts', 'js']);
assert.equal(prof, 'rust');
const target = decideTarget({ effect: ['pure'] }, ['rust', 'c', 'js']);
assert.equal(target, 'rust');

// 5. extract_native
const pyFns = extractPy('def calculate_hash(data): pass');
assert.ok(Array.isArray(pyFns));

// 6. logic / gates
assert.equal(typeof gate11_taxonomy, 'function');
assert.equal(typeof b6_logic_oracle, 'function');
assert.equal(typeof b6_logic_v2_generator, 'function');
assert.equal(typeof compareTargets, 'function');
assert.equal(typeof emitHostPick, 'function');
assert.equal(typeof emitMojo, 'function');
assert.equal(typeof emitSql, 'function');
assert.equal(typeof emitWat, 'function');
assert.equal(typeof cloneLinFullRepoGate, 'function');

console.log('ok all_dogfooded_components_test');
