import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import {
  buildLinobj,
  saveLinobjToCache,
  loadLinobjFromCache,
  buildModuleDAG,
  resolveFineGrainedSymbolInvalidation,
  computeSourceSemanticHash,
  lowerLinobj
} from '../src/linobj.mjs';

console.log('=== Running Adversarial Falsification Campaign on LIN Semantic Layer ===\n');

const tmpCache = path.join(os.tmpdir(), `linobj_adv_${Date.now().toString(36)}`);
fs.mkdirSync(tmpCache, { recursive: true });

try {
  // =========================================================================
  // ATTACK 1: Deep Multi-Hop Aliasing & Re-export Chain
  // A (core: fn_a, helper_unrelated) 
  //   ──► B (re-exports fn_a as alias_b) 
  //   ──► C (re-exports alias_b as alias_c) 
  //   ──► D (re-exports alias_c as alias_d) 
  //   ──► E (consumer of alias_d)
  // =========================================================================
  console.log('--- Attack 1: Deep 4-Hop Alias Chain (A -> B -> C -> D -> E) ---');
  const modA = {
    id: 'mod_a',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!fn_a(x){^x*2}\n!helper_unrelated(x){^x+100}\n=ex{fn_a,helper_unrelated}`,
    dependencies: [],
  };
  const modB = {
    id: 'mod_b',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!fn_a(x){^x*2}\n=ex{fn_a as alias_b}`,
    dependencies: ['mod_a'],
  };
  const modC = {
    id: 'mod_c',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!alias_b(x){^x*2}\n=ex{alias_b as alias_c}`,
    dependencies: ['mod_b'],
  };
  const modD = {
    id: 'mod_d',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!alias_c(x){^x*2}\n=ex{alias_c as alias_d}`,
    dependencies: ['mod_c'],
  };
  const modE = {
    id: 'mod_e',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!consumer(v){^alias_d(v)}\n=ex{consumer}`,
    dependencies: ['mod_d'],
  };

  const chainModules = [modA, modB, modC, modD, modE];
  const chainDAG = buildModuleDAG(chainModules);
  const chainSymbolUsage = {
    mod_b: { mod_a: ['fn_a'] },
    mod_c: { mod_b: ['alias_b'] },
    mod_d: { mod_c: ['alias_c'] },
    mod_e: { mod_d: ['alias_d'] },
  };

  // Case 1A: Mutate fn_a in A -> Must propagate through all 4 alias hops to E
  const mutatedA_fn = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!fn_a(x){^x*3}\n!helper_unrelated(x){^x+100}\n=ex{fn_a,helper_unrelated}`;
  const res1A = resolveFineGrainedSymbolInvalidation(
    chainModules,
    chainDAG,
    { mod_a: mutatedA_fn },
    chainSymbolUsage
  );

  assert.equal(res1A.fineGrained.rebuiltCount, 5, 'Attack 1A: All 5 nodes must be invalidated when root fn_a changes');
  assert.equal(res1A.underInvalidationDetected, false);
  console.log('✔ Attack 1A Defeated: Mutating root fn_a cleanly propagated through 4 alias hops (0% under-invalidation)');

  // Case 1B: Mutate helper_unrelated in A -> E, D, C, B must NOT be invalidated (0% over-invalidation)
  const mutatedA_unrelated = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!fn_a(x){^x*2}\n!helper_unrelated(x){^x+999}\n=ex{fn_a,helper_unrelated}`;
  const res1B = resolveFineGrainedSymbolInvalidation(
    chainModules,
    chainDAG,
    { mod_a: mutatedA_unrelated },
    chainSymbolUsage
  );

  assert.equal(res1B.fineGrained.rebuiltCount, 1, 'Attack 1B: Only mod_a must be rebuilt');
  assert.equal(res1B.overInvalidatedAvoidedCount, 4, 'Attack 1B: Must save all 4 downstream alias nodes from rebuild');
  console.log('✔ Attack 1B Defeated: Mutating unrelated helper preserved all 4 downstream alias nodes (4 rebuilds saved)');

  // =========================================================================
  // ATTACK 2: Ghost Signature / Arity Mutation
  // Change parameter signature without altering internal calculation syntax
  // =========================================================================
  console.log('\n--- Attack 2: Ghost Arity & Signature Mutation ---');
  const modSign1 = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calc(a){^a*2}\n=ex{calc}`;
  const modSign2 = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calc(a,b){^a*2}\n=ex{calc}`;
  
  const objSign1 = buildLinobj(modSign1);
  const objSign2 = buildLinobj(modSign2);
  assert.notEqual(
    objSign1.symbol_graph.export_hashes.calc,
    objSign2.symbol_graph.export_hashes.calc,
    'Attack 2: Changing arity from 1 to 2 must alter symbol contract hash'
  );
  console.log('✔ Attack 2 Defeated: Ghost arity change altered H_contract (Contract: ' + objSign1.symbol_graph.export_hashes.calc + ' -> ' + objSign2.symbol_graph.export_hashes.calc + ')');

  // =========================================================================
  // ATTACK 3: Covert Effect Injection (Pure -> IO / Throw)
  // Value returned on nominal inputs is identical, but side-effect boundaries change
  // =========================================================================
  console.log('\n--- Attack 3: Covert Effect Injection (Pure -> IO) ---');
  const modPure = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!processData(x){^x+1}\n=ex{processData}`;
  const modEffect = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!processData(x){console.log(x);^x+1}\n=ex{processData}`;

  const objPure = buildLinobj(modPure);
  const objEffect = buildLinobj(modEffect);

  assert.notEqual(
    objPure.symbol_graph.export_hashes.processData,
    objEffect.symbol_graph.export_hashes.processData,
    'Attack 3: Injecting console.log effect must change contract hash'
  );
  assert.deepEqual(objPure.effect_manifest.processData, ['Read']);
  assert.deepEqual(objEffect.effect_manifest.processData.sort(), ['IO', 'Read'].sort());
  console.log('✔ Attack 3 Defeated: Side-effect injection triggered H_contract invalidation (Effects: [Read] -> [IO, Read])');

  // =========================================================================
  // ATTACK 4: Export Reordering & Export Stripping
  // =========================================================================
  console.log('\n--- Attack 4: Export Reordering & Export Stripping ---');
  const modEx1 = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!alpha(x){^x}\n!beta(x){^x}\n=ex{alpha,beta}`;
  const modEx2 = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!alpha(x){^x}\n!beta(x){^x}\n=ex{beta,alpha}`;
  const modExStripped = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!alpha(x){^x}\n!beta(x){^x}\n=ex{alpha}`;

  const objEx1 = buildLinobj(modEx1);
  const objEx2 = buildLinobj(modEx2);
  const objExStripped = buildLinobj(modExStripped);

  assert.equal(objEx1.semantic_hash, objEx2.semantic_hash, 'Attack 4A: Export reordering must preserve semantic_hash');
  assert.equal(objEx1.symbol_graph.export_hashes.alpha, objEx2.symbol_graph.export_hashes.alpha);
  assert.equal(objEx1.symbol_graph.export_hashes.beta, objEx2.symbol_graph.export_hashes.beta);
  console.log('✔ Attack 4A Defeated: Export reordering yielded 100% identical semantic and contract hashes');

  assert.ok(!('beta' in objExStripped.symbol_graph.export_hashes), 'Attack 4B: Stripping beta must remove it from export contracts');
  console.log('✔ Attack 4B Defeated: Stripping exported symbol cleanly dropped contract entry');

  // =========================================================================
  // ATTACK 5: Syntactic Churn & Obfuscation Attack (Cosmetic Stress)
  // =========================================================================
  console.log('\n--- Attack 5: Heavy Syntactic Churn & Obfuscation ---');
  const modClean = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!evalPoly(a,b,c,x){sq=(x*x);^((a*sq)+(b*x))+c}\n=ex{evalPoly}`;
  const modObfuscated = `
  // Header comment block
  @LIN:L1c:0.2
  ^schema_once
  ^lossy=true
  ~G{ ?=if #=for ^=ret :else }
  
  /* In-line comment before function */
  !evalPoly( a , b , c , x ) {
    // intermediate comment
    sq = ( x * x ) ;
    
    ^ ( ( a * sq ) + ( b * x ) ) + c ;
  }
  
  // Footer export
  =ex{ evalPoly }
  `;

  const hClean = computeSourceSemanticHash(modClean);
  const hObf = computeSourceSemanticHash(modObfuscated);
  assert.equal(hClean, hObf, 'Attack 5: Heavily obfuscated formatting must yield exact same semantic hash');
  console.log('✔ Attack 5 Defeated: Heavy comment/whitespace churn produced exact same semantic_hash: ' + hClean);

  console.log('\n============================================================');
  console.log('ALL 5 ADVERSARIAL ATTACKS DEFEATED: 0.00% Under-invalidation.');
  console.log('============================================================\n');
} finally {
  try { fs.rmSync(tmpCache, { recursive: true, force: true }); } catch {}
}
