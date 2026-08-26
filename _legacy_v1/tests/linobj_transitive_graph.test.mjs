import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import {
  buildLinobj,
  saveLinobjToCache,
  loadLinobjFromCache,
  buildModuleDAG,
  resolveTransitiveInvalidation,
  buildIncrementalDAG,
  computeSourceSemanticHash
} from '../src/linobj.mjs';

console.log('=== Running Transitive Dependency & Rebuild Amplification Gate ===');

const tmpCache = path.join(os.tmpdir(), `linobj_transitive_test_${Date.now().toString(36)}`);
fs.mkdirSync(tmpCache, { recursive: true });

try {
  // 1. Define Module DAG:
  //    A (core_math) ──► B (stats_calc) ──► C (report_gen)
  //    D (string_utils) [independent]
  //    E (logger) [independent]
  const MODULES = [
    {
      id: 'core_math',
      source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add(a,b){^a+b}\n=ex{add}`,
      dependencies: [],
    },
    {
      id: 'stats_calc',
      source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calcMean(a,b){sum=add(a,b);^sum}\n=ex{calcMean}`,
      dependencies: ['core_math'],
    },
    {
      id: 'report_gen',
      source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!genReport(v1,v2){m=calcMean(v1,v2);^m}\n=ex{genReport}`,
      dependencies: ['stats_calc'],
    },
    {
      id: 'string_utils',
      source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!pad(s){^s+' '}\n=ex{pad}`,
      dependencies: [],
    },
    {
      id: 'logger',
      source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!log(msg){^msg}\n=ex{log}`,
      dependencies: [],
    }
  ];

  const dag = buildModuleDAG(MODULES);
  assert.equal(dag.totalModules, 5);
  assert.deepEqual([...dag.reverseDeps.get('core_math')], ['stats_calc']);
  assert.deepEqual([...dag.reverseDeps.get('stats_calc')], ['report_gen']);
  console.log('✔ DAG Structure: A -> B -> C, D & E disjoint');

  // -------------------------------------------------------------------------
  // SCENARIO 1: Cold Baseline Compilation
  // -------------------------------------------------------------------------
  const baseline = buildIncrementalDAG(MODULES, dag, tmpCache);
  assert.equal(baseline.cacheHits, 0);
  assert.equal(baseline.rebuiltCount, 5);
  assert.equal(baseline.amplificationFactor, 1.0);
  console.log('✔ Scenario 1 PASS: Baseline cold build compiled 5/5 modules');

  // -------------------------------------------------------------------------
  // SCENARIO 2: Zero-Change Warm Rebuild
  // -------------------------------------------------------------------------
  const zeroChange = buildIncrementalDAG(MODULES, dag, tmpCache);
  assert.equal(zeroChange.cacheHits, 5);
  assert.equal(zeroChange.rebuiltCount, 0);
  assert.equal(zeroChange.amplificationFactor, 0.0);
  console.log('✔ Scenario 2 PASS: 0-change build achieved 5/5 Cache Hits (amplification = 0.0)');

  // -------------------------------------------------------------------------
  // SCENARIO 3: Root Mutation A (core_math modified)
  // Expected: A = Direct Miss; B & C = Transitive Invalidation; D & E = 100% HIT
  // -------------------------------------------------------------------------
  const mutatedA = {
    ...MODULES[0],
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add(a,b){res=a+b;^res}\n=ex{add}`,
  };
  const impactA = resolveTransitiveInvalidation(dag, ['core_math']);
  assert.deepEqual(impactA.directMisses, ['core_math']);
  assert.deepEqual(impactA.transitiveInvalidations.sort(), ['report_gen', 'stats_calc'].sort());
  assert.equal(impactA.unaffectedModules, 2); // D and E
  assert.equal(impactA.amplificationFactor, 3 / 5); // 0.60

  const buildA = buildIncrementalDAG(MODULES, dag, tmpCache, {
    core_math: mutatedA.source,
  });
  assert.equal(buildA.cacheHits, 2); // D and E
  assert.equal(buildA.rebuiltCount, 3); // A, B, C
  assert.equal(buildA.amplificationFactor, 0.60);
  console.log('✔ Scenario 3 PASS: Mutating root A transitively invalidated B & C, preserved D & E (Amplification = 0.60)');

  // -------------------------------------------------------------------------
  // SCENARIO 4: Cosmetic / Whitespace Edit in Root A
  // Expected: Same semantic hash -> Amplification Factor = 0.0 (5/5 Cache Hits)
  // -------------------------------------------------------------------------
  const cosmeticA = `
  @LIN:L1c:0.2
  ^schema_once ^lossy=true
  ~G{?=if #=for ^=ret :else}
  
  // Extra comments and spaces
  !add(  a , b  )  {
    res = a + b ;
    ^res
  }
  =ex{ add }
  `;
  const buildCosmetic = buildIncrementalDAG(MODULES, dag, tmpCache, {
    core_math: cosmeticA,
  });
  assert.equal(buildCosmetic.cacheHits, 5);
  assert.equal(buildCosmetic.rebuiltCount, 0);
  assert.equal(buildCosmetic.amplificationFactor, 0.0);
  console.log('✔ Scenario 4 PASS: Cosmetic edit in A yielded exact same semantic hash (Amplification = 0.0)');

  // -------------------------------------------------------------------------
  // SCENARIO 5: Leaf Mutation C (report_gen modified)
  // Expected: C = Direct Miss; A, B, D, E = 100% Cache HIT (Amplification = 0.20)
  // -------------------------------------------------------------------------
  const mutatedC = `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!genReport(v1,v2){m=calcMean(v1,v2);^m*2}\n=ex{genReport}`;
  const impactC = resolveTransitiveInvalidation(dag, ['report_gen']);
  assert.deepEqual(impactC.directMisses, ['report_gen']);
  assert.deepEqual(impactC.transitiveInvalidations, []);
  assert.equal(impactC.amplificationFactor, 0.20);

  const buildC = buildIncrementalDAG(MODULES, dag, tmpCache, {
    report_gen: mutatedC,
  });
  assert.equal(buildC.cacheHits, 4); // A, B, D, E
  assert.equal(buildC.rebuiltCount, 1); // C
  assert.equal(buildC.amplificationFactor, 0.20);
  console.log('✔ Scenario 5 PASS: Mutating leaf C rebuilt only C, preserved A, B, D, E (Amplification = 0.20)');

  // -------------------------------------------------------------------------
  // SCENARIO 6: Source Restoration of A
  // Expected: Instant re-hit of original baseline cache (0 rebuilds)
  // -------------------------------------------------------------------------
  const buildRestored = buildIncrementalDAG(MODULES, dag, tmpCache, {
    core_math: MODULES[0].source,
    report_gen: MODULES[2].source,
  });
  assert.equal(buildRestored.cacheHits, 5);
  assert.equal(buildRestored.rebuiltCount, 0);
  assert.equal(buildRestored.amplificationFactor, 0.0);
  console.log('✔ Scenario 6 PASS: Restoring source instantly rehydrated baseline cache (Amplification = 0.0)');

  console.log('\n============================================================');
  console.log('Transitive Dependency & Rebuild Amplification Gate PASSED (100%).');
  console.log('============================================================\n');
} finally {
  try { fs.rmSync(tmpCache, { recursive: true, force: true }); } catch {}
}
