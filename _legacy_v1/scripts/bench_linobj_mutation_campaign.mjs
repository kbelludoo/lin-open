#!/usr/bin/env node
/**
 * LIN Automated Mutation Testing Campaign & Statistical Precision Matrix.
 * 
 * Generates automated randomized mutations across 12 distinct mutation classes:
 *   1.  formatting (whitespace, linebreaks, indents)
 *   2.  comment (block and inline comment injections)
 *   3.  reorder_exports (reordering =ex{...} symbols)
 *   4.  rename_local (alpha-renaming internal local variables)
 *   5.  alter_parameter (changing parameter arity / signature)
 *   6.  alter_type (changing type annotations)
 *   7.  alter_effect (injecting IO / side-effect boundaries)
 *   8.  alter_refinement (tightening/loosening division proofs)
 *   9.  alter_exported_symbol (mutating active exported function logic)
 *   10. alias_reexport (manipulating aliases: 'add as sum')
 *   11. dependency_edge (adding / modifying required dependency hashes)
 *   12. body_semantics (inverting arithmetic operators +, -, *, /)
 * 
 * Computes the confusion matrix:
 *   - TP: Semantic change correctly triggered MISS / Rebuild
 *   - TN: Non-semantic / cosmetic change correctly triggered HIT / Preserved
 *   - FP: Non-semantic change caused unnecessary rebuild (Over-invalidation)
 *   - FN: Semantic change failed to trigger rebuild (Under-invalidation / Soundness Failure)
 * 
 * Metrics:
 *   - Soundness / Recall = TP / (TP + FN)
 *   - Precision = TP / (TP + FP)
 *   - Under-invalidation Rate = FN / (TP + FN)
 *   - Over-invalidation Rate = FP / (TN + FP)
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
import { emitAilFromSource } from '../src/emitter.mjs';
import {
  mutateFormatting,
  mutateComment,
  mutateReorderExports,
  mutateRenameLocal,
  mutateAlterParameter,
  mutateAlterType,
  mutateAlterEffect,
  mutateAlterRefinement,
  mutateAlterExportedSymbol,
  mutateAliasReexport,
  mutateDependencyEdge,
  mutateBodySemantics
} from '../src/lin_mutation_generator_load.mjs';

const SAMPLE_MODULES = [
  {
    id: 'math_core',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!add(a,b){^a+b}\n!sub(a,b){^a-b}\n!mul(a,b){^a*b}\n=ex{add,sub,mul,add as sum}`,
  },
  {
    id: 'stats_utils',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!mean(a,b){s=add(a,b);^(s/2)}\n!diff(a,b){^sub(a,b)}\n=ex{mean,diff}`,
    dependencies: ['math_core'],
  },
  {
    id: 'reporter',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!formatMean(a,b){m=mean(a,b);^m}\n=ex{formatMean}`,
    dependencies: ['stats_utils'],
  },
  {
    id: 'alias_user',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!total(x,y){^sum(x,y)}\n=ex{total}`,
    dependencies: ['math_core'],
  },
  {
    id: 'isolated_str',
    source: `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n!padLeft(s,len){^s}\n=ex{padLeft}`,
    dependencies: [],
  }
];

const MUTATION_CLASSES = [
  'formatting',
  'comment',
  'reorder_exports',
  'rename_local',
  'alter_parameter',
  'alter_type',
  'alter_effect',
  'alter_refinement',
  'alter_exported_symbol',
  'alias_reexport',
  'dependency_edge',
  'body_semantics'
];

/**
 * Generates an automated mutation of a specific class.
 * Returns { mutatedSource, isSemanticChange, targetModuleId, description }
 */
function generateMutation(cls, modules, seed) {
  let targetMod = null;
  let mutatedSrc = null;
  let isSemantic = false;
  let desc = '';

  for (let offset = 0; offset < modules.length; offset++) {
    const candidate = modules[(seed + offset) % modules.length];
    const src = candidate.source;

    switch (cls) {
      case 'formatting': {
        mutatedSrc = mutateFormatting(src);
        isSemantic = false;
        desc = `Injected whitespace & indents into ${candidate.id}`;
        break;
      }
      case 'comment': {
        mutatedSrc = mutateComment(src, seed);
        isSemantic = false;
        desc = `Injected comments into ${candidate.id}`;
        break;
      }
      case 'reorder_exports': {
        mutatedSrc = mutateReorderExports(src);
        isSemantic = false;
        desc = `Reordered exports in ${candidate.id}`;
        break;
      }
      case 'rename_local': {
        mutatedSrc = mutateRenameLocal(src);
        isSemantic = false;
        desc = `Alpha-renamed local vars in ${candidate.id}`;
        break;
      }
      case 'alter_parameter': {
        mutatedSrc = mutateAlterParameter(src);
        isSemantic = true;
        desc = `Added parameter in ${candidate.id}`;
        break;
      }
      case 'alter_type': {
        mutatedSrc = mutateAlterType(src);
        isSemantic = true;
        desc = `Altered types in ${candidate.id}`;
        break;
      }
      case 'alter_effect': {
        mutatedSrc = mutateAlterEffect(src);
        isSemantic = true;
        desc = `Injected side-effect into ${candidate.id}`;
        break;
      }
      case 'alter_refinement': {
        mutatedSrc = mutateAlterRefinement(src);
        isSemantic = true;
        desc = `Altered refinement/division proof in ${candidate.id}`;
        break;
      }
      case 'alter_exported_symbol': {
        mutatedSrc = mutateAlterExportedSymbol(src);
        isSemantic = true;
        desc = `Mutated active exported logic in ${candidate.id}`;
        break;
      }
      case 'alias_reexport': {
        mutatedSrc = mutateAliasReexport(src);
        isSemantic = true;
        desc = `Altered alias mapping in ${candidate.id}`;
        break;
      }
      case 'dependency_edge': {
        mutatedSrc = mutateDependencyEdge(src, seed);
        isSemantic = false;
        desc = `Added inert edge metadata to ${candidate.id}`;
        break;
      }
      case 'body_semantics': {
        mutatedSrc = mutateBodySemantics(src);
        isSemantic = true;
        desc = `Inverted arithmetic operator in ${candidate.id}`;
        break;
      }
    }

    if (mutatedSrc && mutatedSrc !== src) {
      targetMod = candidate;
      break;
    }
  }

  if (!targetMod) {
    targetMod = modules[0];
    mutatedSrc = targetMod.source + `\n// fallback comment ${seed}`;
    isSemantic = false;
    desc = `Fallback comment in ${targetMod.id}`;
  }

  return {
    targetId: targetMod.id,
    originalSource: targetMod.source,
    mutatedSource: mutatedSrc,
    isSemanticChange: isSemantic,
    cls,
    description: desc,
  };
}

export async function runMutationCampaign(iterations = 240) {
  console.log(`=== LIN Automated Mutation Campaign (${iterations} Mutations across 12 Classes) ===\n`);

  const tmpCache = path.join(os.tmpdir(), `linobj_mut_camp_${Date.now().toString(36)}`);
  fs.mkdirSync(tmpCache, { recursive: true });

  const dag = buildModuleDAG(SAMPLE_MODULES);

  // 1. Establish Cold Baseline in Cache
  for (const m of SAMPLE_MODULES) {
    const obj = buildLinobj(m.source);
    saveLinobjToCache(obj, tmpCache);
  }

  let TP = 0; // Semantic change -> Correctly detected as MISS
  let TN = 0; // Cosmetic/Non-semantic -> Correctly detected as HIT
  let FP = 0; // Non-semantic change -> Incorrectly triggered MISS (Over-invalidation)
  let FN = 0; // Semantic change -> Failed to detect, gave HIT (Under-invalidation / Soundness Failure)

  const classStats = {};
  for (const cls of MUTATION_CLASSES) {
    classStats[cls] = { total: 0, TP: 0, TN: 0, FP: 0, FN: 0 };
  }

  for (let i = 0; i < iterations; i++) {
    const cls = MUTATION_CLASSES[i % MUTATION_CLASSES.length];
    const mut = generateMutation(cls, SAMPLE_MODULES, i);

    // Compute semantic hash of mutated code
    const originalHash = computeSourceSemanticHash(mut.originalSource);
    const mutatedHash = computeSourceSemanticHash(mut.mutatedSource);
    const hashChanged = (originalHash !== mutatedHash);

    // Also check symbol-level contract hashes
    const origObj = buildLinobj(mut.originalSource);
    const newObj = buildLinobj(mut.mutatedSource);
    let contractChanged = false;
    for (const [sym, h] of Object.entries(newObj.symbol_graph.export_hashes || {})) {
      if (origObj.symbol_graph.export_hashes?.[sym] !== h) contractChanged = true;
    }

    const detectedAsMiss = hashChanged || contractChanged;

    classStats[cls].total++;

    if (mut.isSemanticChange) {
      if (detectedAsMiss) {
        TP++;
        classStats[cls].TP++;
      } else {
        FN++;
        classStats[cls].FN++;
        console.error(`[CRITICAL UNDER-INVALIDATION] Mutation ${cls} failed to trigger rebuild: ${mut.description}`);
      }
    } else {
      if (!detectedAsMiss) {
        TN++;
        classStats[cls].TN++;
      } else {
        FP++;
        classStats[cls].FP++;
      }
    }
  }

  const totalSemantic = TP + FN;
  const totalNonSemantic = TN + FP;
  const recall = totalSemantic > 0 ? (TP / (TP + FN)) : 1.0;
  const precision = (TP + FP) > 0 ? (TP / (TP + FP)) : 1.0;
  const underInvalidationRate = totalSemantic > 0 ? (FN / totalSemantic) : 0.0;
  const overInvalidationRate = totalNonSemantic > 0 ? (FP / totalNonSemantic) : 0.0;
  const accuracy = (TP + TN) / iterations;

  // Print Results Table
  console.log('| Mutation Class | Total Samples | TP (Sound Miss) | TN (Sound Hit) | FP (Over-inv) | FN (Under-inv) | Recall / Soundness |');
  console.log('| :--- | :---: | :---: | :---: | :---: | :---: | :---: |');
  for (const cls of MUTATION_CLASSES) {
    const s = classStats[cls];
    const rec = (s.TP + s.FN) > 0 ? `${((s.TP / (s.TP + s.FN)) * 100).toFixed(1)}%` : 'N/A (Non-sem)';
    console.log(`| **${cls}** | ${s.total} | ${s.TP} | ${s.TN} | ${s.FP} | **${s.FN}** | **${rec}** |`);
  }

  console.log('\n============================================================');
  console.log('                 STATISTICAL PRECISION MATRIX               ');
  console.log('============================================================');
  console.log(`Total Mutations Evaluated: ${iterations}`);
  console.log(`Semantic Mutations: ${totalSemantic} | Non-Semantic Mutations: ${totalNonSemantic}`);
  console.log(`True Positives (Sound Rebuilds):    ${TP}`);
  console.log(`True Negatives (Preserved Hits):     ${TN}`);
  console.log(`False Positives (Over-invalidation): ${FP}`);
  console.log(`False Negatives (Under-invalidation): ${FN}`);
  console.log('------------------------------------------------------------');
  console.log(`Soundness / Recall:        ${(recall * 100).toFixed(2)}%`);
  console.log(`Precision:                 ${(precision * 100).toFixed(2)}%`);
  console.log(`Under-invalidation Rate:   ${(underInvalidationRate * 100).toFixed(2)}% (Target: 0.00%)`);
  console.log(`Over-invalidation Rate:    ${(overInvalidationRate * 100).toFixed(2)}%`);
  console.log(`Overall Accuracy:          ${(accuracy * 100).toFixed(2)}%`);
  console.log('============================================================\n');

  try { fs.rmSync(tmpCache, { recursive: true, force: true }); } catch {}

  return {
    iterations,
    TP, TN, FP, FN,
    recall,
    precision,
    underInvalidationRate,
    overInvalidationRate,
    accuracy,
    classStats
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runMutationCampaign(240);
}
