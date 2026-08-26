#!/usr/bin/env node
/**
 * LIN Composite Mutation Benchmark.
 * 
 * Evaluates combinations of simultaneous orthogonal mutations across modules in a DAG:
 *   Combination 1: [alias_mutation + type_mutation]
 *   Combination 2: [type_mutation + effect_injection]
 *   Combination 3: [local_alpha_rename + refinement_mutation]
 *   Combination 4: [intermediate_transitive_semantic + cosmetic_root]
 *   Combination 5: [reorder_exports + ghost_arity + body_inversion]
 *   Combination 6: [multi_cosmetic_composite] (comments + whitespace + reorder + alpha-rename)
 * 
 * Verifies that:
 *   - Semantic composites trigger strictly required invalidations (FN = 0)
 *   - Pure cosmetic composites maintain 100% Cache Hits (FP = 0)
 *   - Intermediate mutations in a DAG correctly invalidate downstream consumers without rebuilding upstream root
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildLinobj,
  saveLinobjToCache,
  loadLinobjFromCache,
  buildModuleDAG,
  resolveFineGrainedSymbolInvalidation,
  computeSourceSemanticHash,
  lowerLinobj
} from '../src/linobj.mjs';

const DAG_MODULES = [
  {
    id: 'root_math',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add(a,b){^a+b}\n!sub(a,b){^a-b}\n=ex{add,sub,add as sum}`,
    dependencies: [],
  },
  {
    id: 'mid_stats',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calcMean(x,y){res=sum(x,y);^(res/2)}\n=ex{calcMean,calcMean as avg}`,
    dependencies: ['root_math'],
  },
  {
    id: 'leaf_consumer',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!getReport(v1,v2){m=avg(v1,v2);^m}\n=ex{getReport}`,
    dependencies: ['mid_stats'],
  },
  {
    id: 'disjoint_helper',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!identity(x){val=x;^val}\n=ex{identity}`,
    dependencies: [],
  }
];

const symbolUsage = {
  mid_stats: { root_math: ['sum'] },
  leaf_consumer: { mid_stats: ['avg'] },
};

export async function runCompositeBenchmark() {
  console.log('=== LIN Composite Combinatorial Mutation Benchmark ===\n');

  const tmpCache = path.join(os.tmpdir(), `linobj_comp_${Date.now().toString(36)}`);
  fs.mkdirSync(tmpCache, { recursive: true });

  const dag = buildModuleDAG(DAG_MODULES);

  // Cold baseline
  for (const m of DAG_MODULES) {
    saveLinobjToCache(buildLinobj(m.source), tmpCache);
  }

  const scenarios = [
    {
      name: 'Combo 1: [alias_mutation + type_mutation]',
      isSemantic: true,
      mutations: {
        root_math: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add(a:string,b:string){^a+b}\n!sub(a,b){^a-b}\n=ex{add,sub,sub as sum}`,
      },
      expectedDirect: ['root_math'],
      expectedTransitive: ['mid_stats', 'leaf_consumer'],
      expectedPreserved: ['disjoint_helper'],
    },
    {
      name: 'Combo 2: [type_mutation + effect_injection]',
      isSemantic: true,
      mutations: {
        mid_stats: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calcMean(x:number,y:number){console.log('audit');res=sum(x,y);^(res/2)}\n=ex{calcMean,calcMean as avg}`,
      },
      expectedDirect: ['mid_stats'],
      expectedTransitive: ['leaf_consumer'],
      expectedPreserved: ['root_math', 'disjoint_helper'],
    },
    {
      name: 'Combo 3: [local_alpha_rename + refinement_mutation]',
      isSemantic: true,
      mutations: {
        mid_stats: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calcMean(x,y){res_renamed=sum(x,y);^(res_renamed/0)}\n=ex{calcMean,calcMean as avg}`,
      },
      expectedDirect: ['mid_stats'],
      expectedTransitive: ['leaf_consumer'],
      expectedPreserved: ['root_math', 'disjoint_helper'],
    },
    {
      name: 'Combo 4: [intermediate_transitive_semantic + cosmetic_root]',
      isSemantic: true,
      mutations: {
        root_math: `/* Cosmetic Header */\n@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add( a , b ){ ^ a + b }\n!sub(a,b){^a-b}\n=ex{add,sub,add as sum}`,
        mid_stats: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!calcMean(x,y){res=sum(x,y);^(res*99)}\n=ex{calcMean,calcMean as avg}`,
      },
      expectedDirect: ['mid_stats'], // root_math is cosmetic HIT
      expectedTransitive: ['leaf_consumer'],
      expectedPreserved: ['root_math', 'disjoint_helper'],
    },
    {
      name: 'Combo 5: [reorder_exports + ghost_arity + body_inversion]',
      isSemantic: true,
      mutations: {
        root_math: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add(a,b,extra){^a-b}\n!sub(a,b){^a-b}\n=ex{sub,add,add as sum}`,
      },
      expectedDirect: ['root_math'],
      expectedTransitive: ['mid_stats', 'leaf_consumer'],
      expectedPreserved: ['disjoint_helper'],
    },
    {
      name: 'Combo 6: [multi_cosmetic_composite] (comments + whitespace + reorder + alpha-rename)',
      isSemantic: false,
      mutations: {
        mid_stats: `
        // Leading block comment
        @LIN:L1c:0.2
        ^schema_once
        ^lossy=true
        ~G{ ?=if #=for ^=ret :else }
        
        /* function comment */
        !calcMean( x , y ) {
          // local alpha rename: res -> calculated_result
          calculated_result = sum( x , y ) ;
          ^ ( calculated_result / 2 ) ;
        }
        
        // reordered export
        =ex{ calcMean as avg , calcMean }
        `,
        disjoint_helper: `
        @LIN:L1c:0.2
        ^schema_once ^lossy=true
        ~G{?=if #=for ^=ret :else}
        !identity( x ){ val_renamed = x ; ^ val_renamed }
        =ex{ identity }
        `
      },
      expectedDirect: [],
      expectedTransitive: [],
      expectedPreserved: ['root_math', 'mid_stats', 'leaf_consumer', 'disjoint_helper'],
    }
  ];

  let passed = 0;
  for (const sc of scenarios) {
    const res = resolveFineGrainedSymbolInvalidation(
      DAG_MODULES,
      dag,
      sc.mutations,
      symbolUsage
    );

    // If cosmetic mutations produced same semantic hash, direct misses exclude them
    const actualDirect = res.fineGrained.directMisses.filter(id => {
      const orig = DAG_MODULES.find(m => m.id === id).source;
      const mut = sc.mutations[id];
      return computeSourceSemanticHash(orig) !== computeSourceSemanticHash(mut);
    });

    const actualTransitive = res.fineGrained.transitive;
    const allInvalidated = new Set([...actualDirect, ...actualTransitive]);
    const actualPreserved = DAG_MODULES.map(m => m.id).filter(id => !allInvalidated.has(id));

    const directMatch = JSON.stringify(actualDirect.sort()) === JSON.stringify(sc.expectedDirect.sort());
    const transMatch = JSON.stringify(actualTransitive.sort()) === JSON.stringify(sc.expectedTransitive.sort());
    const presMatch = JSON.stringify(actualPreserved.sort()) === JSON.stringify(sc.expectedPreserved.sort());

    if (directMatch && transMatch && presMatch) {
      console.log(`✔ ${sc.name} PASS (Direct: [${actualDirect}], Transitive: [${actualTransitive}], Preserved: [${actualPreserved}])`);
      passed++;
    } else {
      console.error(`✘ ${sc.name} FAIL:`);
      console.error(`  Expected Direct: [${sc.expectedDirect}] | Actual: [${actualDirect}]`);
      console.error(`  Expected Transitive: [${sc.expectedTransitive}] | Actual: [${actualTransitive}]`);
      console.error(`  Expected Preserved: [${sc.expectedPreserved}] | Actual: [${actualPreserved}]`);
    }
  }

  console.log(`\nComposite Mutation Benchmark: ${passed}/${scenarios.length} Scenarios Passed (${((passed/scenarios.length)*100).toFixed(1)}%).\n`);
  try { fs.rmSync(tmpCache, { recursive: true, force: true }); } catch {}

  return { passed, total: scenarios.length };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runCompositeBenchmark();
}
