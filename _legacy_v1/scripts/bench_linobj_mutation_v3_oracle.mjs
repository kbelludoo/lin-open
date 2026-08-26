#!/usr/bin/env node
/**
 * LIN Mutation Campaign V3: Independent External Behavioral & Contract Oracle.
 * 
 * Eliminates circular ground-truth evaluation:
 * Ground truth is determined EXCLUSIVELY by an external holdout runtime evaluator:
 *   1. Executes original vs mutated functions on a dense matrix of holdout inputs.
 *   2. Evaluates return values, throw behavior, side-effect output, and parameter length.
 *   3. Declares TRUE SEMANTIC CHANGE if and only if external observable behavior,
 *      signature, effect, or contract differs in the independent JS engine.
 * 
 * Verifies LIN's .linobj invalidator against this external independent oracle across
 * 200 combinatorial composite vectors.
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
import { compileLiaToJs } from '../src/compiler.mjs';

const BASE_DAG_MODULES = [
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

import { getMutatorPool } from '../src/lin_mutation_generator_load.mjs';
const MUTATOR_POOL = getMutatorPool();

/**
 * INDEPENDENT EXTERNAL ORACLE
 * Evaluates behavioral equivalence and contract difference directly in V8 runtime
 * WITHOUT using LIN's contentHash or canonicalize functions.
 */
function evaluateIndependentExternalOracle(origSource, mutatedSource) {
  try {
    const jsOrig = compileLiaToJs(origSource).js;
    const jsMut = compileLiaToJs(mutatedSource).js;

    const evalMod = (jsCode) => {
      const logs = [];
      const env = {
        console: { log: (...args) => logs.push(args.join(' ')) },
        module: { exports: {} },
      };
      const fn = new Function('console', 'module', 'exports', `${jsCode}; return module.exports;`);
      const exp = fn(env.console, env.module, env.module.exports);
      const normalizedExports = typeof exp === 'function' ? { [exp.name || 'default']: exp } : (exp || {});
      return { exports: normalizedExports, logs };
    };

    const o1 = evalMod(jsOrig);
    const o2 = evalMod(jsMut);

    // 1. Compare Export Keys (including Aliases)
    const keys1 = Object.keys(o1.exports).sort();
    const keys2 = Object.keys(o2.exports).sort();
    if (JSON.stringify(keys1) !== JSON.stringify(keys2)) {
      return { semanticChanged: true, reason: 'EXPORT_KEYS_CHANGED' };
    }

    // 2. Compare Function Arity (Signature)
    for (const k of keys1) {
      const f1 = o1.exports[k];
      const f2 = o2.exports[k];
      if (typeof f1 === 'function' && typeof f2 === 'function') {
        if (f1.length !== f2.length) {
          return { semanticChanged: true, reason: `ARITY_CHANGED_FOR_${k}` };
        }
      }
    }

    // 3. Dense Matrix Holdout Behavioral & Side-Effect Evaluation
    const testInputs = [
      [0, 0], [1, 2], [10, -5], [-40, 80], [100, 200], [7, 3], [0, 5], [-1, -1]
    ];

    for (const k of keys1) {
      const f1 = o1.exports[k];
      const f2 = o2.exports[k];
      if (typeof f1 === 'function' && typeof f2 === 'function') {
        for (const inp of testInputs) {
          const l1 = [];
          const l2 = [];
          const origConsole = console.log;
          let res1, res2;
          let err1 = null, err2 = null;

          try {
            console.log = (...args) => l1.push(args.join(' '));
            res1 = f1(...inp);
          } catch (e) {
            err1 = e.message;
          } finally {
            console.log = origConsole;
          }

          try {
            console.log = (...args) => l2.push(args.join(' '));
            res2 = f2(...inp);
          } catch (e) {
            err2 = e.message;
          } finally {
            console.log = origConsole;
          }

          // Check for discrepancy in return values, throws, or side-effect logs
          if (err1 !== err2 || res1 !== res2 || JSON.stringify(l1) !== JSON.stringify(l2)) {
            return {
              semanticChanged: true,
              reason: `BEHAVIOR_DISCREPANCY_${k}_ON_[${inp}]: (${res1} vs ${res2}, err: ${err1} vs ${err2}, logs: ${l1.length} vs ${l2.length})`
            };
          }
        }
      }
    }

    // Check type annotations in AST header if explicit
    const hasType1 = /:[a-zA-Z]/.test(origSource);
    const hasType2 = /:[a-zA-Z]/.test(mutatedSource);
    if (hasType1 !== hasType2) {
      return { semanticChanged: true, reason: 'TYPE_CONTRACT_CHANGED' };
    }

    return { semanticChanged: false, reason: 'IDENTICAL_BEHAVIOR_AND_CONTRACT' };
  } catch (e) {
    // Compilation / Syntax failure in mutated source is a breaking semantic change
    return { semanticChanged: true, reason: `PARSE_ERROR: ${e.message}` };
  }
}

export async function runMutationCampaignV3(totalTrials = 200) {
  console.log(`=== LIN Mutation Campaign V3: Independent External Behavioral & Contract Oracle ===\n`);
  console.log(`Evaluating ${totalTrials} composite vectors against holdout V8 runtime execution...\n`);

  const tmpCache = path.join(os.tmpdir(), `linobj_v3_oracle_${Date.now().toString(36)}`);
  fs.mkdirSync(tmpCache, { recursive: true });

  const dag = buildModuleDAG(BASE_DAG_MODULES);

  // Establish cold baseline
  for (const m of BASE_DAG_MODULES) {
    saveLinobjToCache(buildLinobj(m.source), tmpCache);
  }

  let TP = 0; // Oracle: Semantic Change -> LIN: Rebuilt (MISS)
  let TN = 0; // Oracle: No Semantic Change -> LIN: Preserved (HIT)
  let FP = 0; // Oracle: No Semantic Change -> LIN: Rebuilt (Over-invalidation)
  let FN = 0; // Oracle: Semantic Change -> LIN: Missed/Preserved (Under-invalidation / Soundness Failure)

  for (let trial = 0; trial < totalTrials; trial++) {
    // Pick 2 to 4 mutators deterministically
    const k = 2 + (trial % 3);
    const chosenIndices = [];
    for (let j = 0; j < k; j++) {
      const idx = (trial * 7 + j * 13) % MUTATOR_POOL.length;
      if (!chosenIndices.includes(idx)) chosenIndices.push(idx);
    }

    const selectedMutators = chosenIndices.map(i => MUTATOR_POOL[i]);
    const targetModule = BASE_DAG_MODULES[trial % BASE_DAG_MODULES.length];

    // Apply mutators cumulatively
    let compositeSource = targetModule.source;
    for (const mut of selectedMutators) {
      compositeSource = mut.apply(compositeSource, trial);
    }

    // 1. GROUND TRUTH from External Independent Oracle (V8 Runtime Execution)
    const oracleVerdict = evaluateIndependentExternalOracle(targetModule.source, compositeSource);
    const isGroundTruthSemanticChange = oracleVerdict.semanticChanged;

    // 2. LIN PREDICTION (.linobj Content-Addressed Cache Lookup)
    const mutHash = computeSourceSemanticHash(compositeSource);
    const cachedObj = loadLinobjFromCache(mutHash, tmpCache);
    const linTriggeredRebuild = (!cachedObj || cachedObj.error);

    if (isGroundTruthSemanticChange) {
      if (linTriggeredRebuild) {
        TP++;
      } else {
        FN++;
        console.error(`[SOUNDNESS FAILURE] Trial ${trial}: Oracle flagged change (${oracleVerdict.reason}) but LIN preserved cache!`);
      }
    } else {
      if (!linTriggeredRebuild) {
        TN++;
      } else {
        FP++;
        console.warn(`[OVER-INVALIDATION] Trial ${trial}: Oracle verified 100% behavioral equivalence, but LIN rebuilt!`);
      }
    }
  }

  const totalSemantic = TP + FN;
  const totalNonSemantic = TN + FP;
  const recall = totalSemantic > 0 ? (TP / (TP + FN)) : 1.0;
  const precision = (TP + FP) > 0 ? (TP / (TP + FP)) : 1.0;
  const underInvalidationRate = totalSemantic > 0 ? (FN / totalSemantic) : 0.0;
  const overInvalidationRate = totalNonSemantic > 0 ? (FP / totalNonSemantic) : 0.0;
  const accuracy = (TP + TN) / totalTrials;

  console.log('============================================================');
  console.log('       INDEPENDENT EXTERNAL ORACLE PRECISION MATRIX         ');
  console.log('============================================================');
  console.log(`Total Composite Vectors Evaluated:   ${totalTrials}`);
  console.log(`Ground-Truth Semantic Mutations:     ${totalSemantic}`);
  console.log(`Ground-Truth Cosmetic Equivalences:  ${totalNonSemantic}`);
  console.log('------------------------------------------------------------');
  console.log(`True Positives (Sound Rebuilds):     ${TP}`);
  console.log(`True Negatives (Preserved Hits):      ${TN}`);
  console.log(`False Positives (Over-invalidation):  ${FP}`);
  console.log(`False Negatives (Under-invalidation):  ${FN}`);
  console.log('------------------------------------------------------------');
  console.log(`Soundness / Recall:        ${(recall * 100).toFixed(2)}%`);
  console.log(`Precision:                 ${(precision * 100).toFixed(2)}%`);
  console.log(`Under-invalidation Rate:   ${(underInvalidationRate * 100).toFixed(2)}% (Target: 0.00%)`);
  console.log(`Over-invalidation Rate:    ${(overInvalidationRate * 100).toFixed(2)}%`);
  console.log(`Overall Accuracy:          ${(accuracy * 100).toFixed(2)}%`);
  console.log('============================================================\n');

  try { fs.rmSync(tmpCache, { recursive: true, force: true }); } catch {}

  return {
    totalTrials,
    totalSemantic,
    totalNonSemantic,
    TP, TN, FP, FN,
    recall,
    precision,
    underInvalidationRate,
    overInvalidationRate,
    accuracy,
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runMutationCampaignV3(200);
}
