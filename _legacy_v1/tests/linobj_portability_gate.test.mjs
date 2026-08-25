import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import {
  buildLinobj,
  saveLinobjToCache,
  loadLinobjFromCache,
  verifyLinobjIntegrity,
  computeSourceSemanticHash,
  lowerLinobj
} from '../src/linobj.mjs';

console.log('=== Running 7-Point LIN Semantic Object Portability Gate ===');

const envA = path.join(os.tmpdir(), `linobj_env_A_${Date.now().toString(36)}`);
const envB = path.join(os.tmpdir(), `linobj_env_B_${Date.now().toString(36)}`);
fs.mkdirSync(envA, { recursive: true });
fs.mkdirSync(envB, { recursive: true });

try {
  // -------------------------------------------------------------------------
  // TEST 1: Identidade Semântica (Mesmo .linobj -> mesmo semantic_hash)
  // -------------------------------------------------------------------------
  const srcBase = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=math
~G{?=if #=for ^=ret :else}
!hypot(a,b){sq=(a*a)+(b*b);^Math.sqrt(sq)}
=ex{hypot}`;

  const linobj1 = buildLinobj(srcBase);
  const linobj2 = buildLinobj(srcBase);
  assert.equal(linobj1.semantic_hash, linobj2.semantic_hash, 'Test 1: Identical source must produce identical semantic_hash');
  console.log('✔ Test 1 PASS: Identical source produces identical semantic_hash');

  // -------------------------------------------------------------------------
  // TEST 2: Rejeição por Corrupção (Integrity Check)
  // -------------------------------------------------------------------------
  saveLinobjToCache(linobj1, envA);
  const rawJson = JSON.parse(fs.readFileSync(path.join(envA, `${linobj1.semantic_hash}.linobj.json`), 'utf8'));
  
  // Tamper with AST body while keeping original hash
  rawJson.canonical_ir.functions[0].body = 'sq=(a*a)-(b*b);^Math.sqrt(sq)';
  const corruptedPath = path.join(envA, `tampered.linobj.json`);
  fs.writeFileSync(corruptedPath, JSON.stringify(rawJson), 'utf8');

  const checkTampered = verifyLinobjIntegrity(rawJson);
  assert.equal(checkTampered.valid, false, 'Test 2: Tampered canonical AST must fail integrity verification');
  assert.match(checkTampered.reason, /HASH_TAMPERED/, 'Test 2: Must report HASH_TAMPERED');
  console.log('✔ Test 2 PASS: Tampered .linobj rejected immediately by cryptographic integrity check');

  // -------------------------------------------------------------------------
  // TEST 3: Cache Miss Semântico (Mudança real de código -> novo hash)
  // -------------------------------------------------------------------------
  const srcSemanticDiff = `@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=math
~G{?=if #=for ^=ret :else}
!hypot(a,b){sq=(a*a)-(b*b);^Math.sqrt(sq)}
=ex{hypot}`;

  const hashDiff = computeSourceSemanticHash(srcSemanticDiff);
  assert.notEqual(hashDiff, linobj1.semantic_hash, 'Test 3: Semantic change must produce different hash');
  const missLookup = loadLinobjFromCache(hashDiff, envA);
  assert.equal(missLookup, null, 'Test 3: Different semantic hash must be a cache MISS');
  console.log('✔ Test 3 PASS: Semantic change produces different hash (Cache MISS)');

  // -------------------------------------------------------------------------
  // TEST 4: Invariância Léxica (Formatação / whitespace / comentários -> MESMO HASH)
  // -------------------------------------------------------------------------
  const srcLexicalDiff = `
  @LIN:L1c:0.2
  ^schema_once ^lossy=true ^ops=math
  ~G{?=if #=for ^=ret :else}
  
  // Different formatting and spaces
  !hypot(  a , b  )  {
    sq = ( a * a ) + ( b * b );
    ^Math.sqrt(sq)
  }
  =ex{ hypot }
  `;

  const hashLexical = computeSourceSemanticHash(srcLexicalDiff);
  assert.equal(hashLexical, linobj1.semantic_hash, 'Test 4: Lexical/whitespace variation must produce the EXACT same semantic_hash');
  const hitLookup = loadLinobjFromCache(hashLexical, envA);
  assert.ok(hitLookup, 'Test 4: Lexical variation must be a direct cache HIT');
  console.log('✔ Test 4 PASS: Lexical/formatting variations yield exact same hash (Cache HIT)');

  // -------------------------------------------------------------------------
  // TEST 5: Invalidação por Dependência Externa
  // -------------------------------------------------------------------------
  const depLinobj = buildLinobj(srcBase, {
    requiredArtifacts: [
      { name: 'math_core', expected_hash: 'abc123expected' }
    ]
  });
  saveLinobjToCache(depLinobj, envA);

  // Dependency matching -> valid
  const loadedValidDep = loadLinobjFromCache(depLinobj.semantic_hash, envA, {
    currentDependencyMap: { math_core: 'abc123expected' }
  });
  assert.ok(loadedValidDep, 'Test 5: Matching dependency must be valid');

  // Dependency altered -> invalid / rejected
  const loadedInvalidDep = loadLinobjFromCache(depLinobj.semantic_hash, envA, {
    currentDependencyMap: { math_core: 'DIFFERENT_HASH_999' }
  });
  assert.deepEqual(loadedInvalidDep, {
    error: 'DEPENDENCY_INVALIDATED',
    detail: 'External dependency hash changed'
  }, 'Test 5: Changed dependency must invalidate cache');
  console.log('✔ Test 5 PASS: Dependency changes invalidate cache correctly');

  // -------------------------------------------------------------------------
  // TEST 6: Portabilidade Cruzada (Ambiente A -> Ambiente B)
  // -------------------------------------------------------------------------
  const artifactA = fs.readFileSync(path.join(envA, `${linobj1.semantic_hash}.linobj.json`), 'utf8');
  // Transfer to Environment B
  fs.writeFileSync(path.join(envB, `${linobj1.semantic_hash}.linobj.json`), artifactA, 'utf8');

  const loadedInB = loadLinobjFromCache(linobj1.semantic_hash, envB);
  assert.ok(loadedInB, 'Test 6: Transferred .linobj must load and verify in Environment B');
  assert.equal(loadedInB.semantic_hash, linobj1.semantic_hash);
  console.log('✔ Test 6 PASS: Pre-verified .linobj transferred from Machine A to Machine B accepted cleanly');

  // -------------------------------------------------------------------------
  // TEST 7: Equivalência Comportamental e Lowering Determinístico
  // -------------------------------------------------------------------------
  const loweredInA = lowerLinobj(linobj1, 'js');
  const loweredInB = lowerLinobj(loadedInB, 'js');
  assert.equal(loweredInA.code, loweredInB.code, 'Test 7: Lowered JS code in A and B must be bit-identical');

  const evalWrapper = `(function(){\nconst module = { exports: {} };\nconst exports = module.exports;\n${loweredInB.code}\nreturn typeof module.exports === 'function' ? module.exports : module.exports.hypot;\n})()`;
  const fn = eval(evalWrapper);
  assert.equal(fn(3, 4), 5, 'Test 7: Oracle validation (hypot(3,4) == 5)');
  assert.equal(fn(6, 8), 10, 'Test 7: Oracle validation (hypot(6,8) == 10)');
  console.log('✔ Test 7 PASS: Independent lowering in Environment B achieves 100% behavioral equivalence against oracle');

  console.log('\n============================================================');
  console.log('All 7 Portability & Semantic Object Gates PASSED with 100% integrity.');
  console.log('============================================================\n');
} finally {
  try { fs.rmSync(envA, { recursive: true, force: true }); } catch {}
  try { fs.rmSync(envB, { recursive: true, force: true }); } catch {}
}
