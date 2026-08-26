#!/usr/bin/env node
/**
 * LIN V4 False Positive Taxonomy & Root Cause Analysis.
 * 
 * Inspects all 17 FP cases from Campaign V4, categorizing each into:
 *   1. CONSERVATIVE_DESIRABLE (Semantic change exists theoretically, but unexercised by holdout)
 *   2. CANONICALIZATION_STRICTNESS (Syntactic variation that could be safely normalized)
 *   3. INERT_ANNOTATION (Trailing comment/annotation that triggered module rebuild)
 */
import {
  buildLinobj,
  saveLinobjToCache,
  loadLinobjFromCache,
  buildModuleDAG,
  computeSourceSemanticHash
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

const MUTATOR_POOL = [
  { name: 'formatting', apply: (s) => s.replace(/\+/g, ' + ').replace(/=/g, ' = ').replace(/\n/g, '\n\n  ') },
  { name: 'comment', apply: (s, seed) => `/* block comment ${seed} */\n` + s.replace(/\{/g, '{\n  // line comment\n') },
  { name: 'reorder_exports', apply: (s) => s.replace(/=ex\{([^}]+)\}/, (_, l) => `=ex{${l.split(',').map(x => x.trim()).reverse().join(',')}}`) },
  { name: 'rename_local', apply: (s) => s.replace(/\bres\b/g, 'res_renamed').replace(/\bm\b/g, 'm_renamed').replace(/\bval\b/g, 'val_renamed') },
  { name: 'alter_parameter', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)/, (_, n, p) => `!${n}(${p}${p ? ',' : ''}_extra)`) },
  { name: 'alter_type', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)/, (_, n, p) => `!${n}(${p.split(',').map(x => x + ':string').join(',')})`) },
  { name: 'alter_effect', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)\s*\{/, '!$1($2){\n  console.log("io_audit");') },
  { name: 'alter_refinement', apply: (s) => s.includes('/2') ? s.replace(/\/2\)/, '/0)') : s + '\n// noop_ref' },
  { name: 'alter_exported_symbol', apply: (s) => s.includes('^a+b') ? s.replace(/\^a\+b/, '^a+b+99') : s.replace(/\^val/, '^val+99') },
  { name: 'alias_reexport', apply: (s) => s.includes(' as ') ? s.replace(/add as sum/, 'sub as sum').replace(/calcMean as avg/, 'identity as avg') : s },
  { name: 'dependency_edge', apply: (s, seed) => s + `\n// edge annotation ${seed}` },
  { name: 'body_semantics', apply: (s) => s.includes('+') ? s.replace(/\+/, '-') : s.replace(/\*/, '+') }
];

function evaluateDeepAdversarialOracle(origSource, mutatedSource) {
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

    const keys1 = Object.keys(o1.exports).sort();
    const keys2 = Object.keys(o2.exports).sort();
    if (JSON.stringify(keys1) !== JSON.stringify(keys2)) {
      return { semanticChanged: true, reason: 'EXPORT_KEYS_CHANGED' };
    }

    for (const k of keys1) {
      const f1 = o1.exports[k];
      const f2 = o2.exports[k];
      if (typeof f1 === 'function' && typeof f2 === 'function') {
        if (f1.length !== f2.length) return { semanticChanged: true, reason: `ARITY_CHANGED_${k}` };
      }
    }

    const extractFnTypes = (src) => {
      const matches = src.match(/![A-Za-z0-9_]+\([^)]*\)/g) || [];
      return matches.map(m => {
        const params = m.replace(/![A-Za-z0-9_]+\(/, '').replace(/\)$/, '');
        return params.split(',').map(p => p.includes(':') ? p.split(':')[1].trim() : '').join(',');
      }).join(';');
    };
    if (extractFnTypes(origSource) !== extractFnTypes(mutatedSource)) {
      return { semanticChanged: true, reason: 'TYPE_CONTRACT_CHANGED' };
    }

    const adversarialMatrix = [
      [0, 0], [1, 2], [10, -5], [-40, 80], [100, 200], [7, 3],
      [Number.MAX_SAFE_INTEGER, 1], [Number.MIN_SAFE_INTEGER, -1], [1e12, -1e12],
      [0.1 + 0.2, 0.3], [1e-15, 2e-15], [Math.PI, Math.E],
      [0, -0], [Infinity, 1], [-Infinity, -Infinity], [NaN, 0],
      [0], [1], [-42], [Number.MAX_SAFE_INTEGER], [Math.PI], [NaN], [Infinity], ["test_str"]
    ];

    for (const k of keys1) {
      const f1 = o1.exports[k];
      const f2 = o2.exports[k];
      if (typeof f1 === 'function' && typeof f2 === 'function') {
        for (const inp of adversarialMatrix) {
          const l1 = [], l2 = [];
          const origConsole = console.log;
          let res1, res2, err1 = null, err2 = null;

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

          if (!Object.is(res1, res2) || err1 !== err2 || JSON.stringify(l1) !== JSON.stringify(l2)) {
            return { semanticChanged: true, reason: `ADVERSARIAL_DISCREPANCY_${k}` };
          }
        }
      }
    }

    return { semanticChanged: false, reason: 'IDENTICAL_BEHAVIOR_AND_CONTRACT' };
  } catch (e) {
    return { semanticChanged: true, reason: `PARSE_ERROR: ${e.message}` };
  }
}

console.log('=== Detailed Breakdown of the 17 False Positives in Campaign V4 ===\n');

const fpCases = [];

for (let trial = 0; trial < 200; trial++) {
  const k = 2 + (trial % 3);
  const chosenIndices = [];
  for (let j = 0; j < k; j++) {
    const idx = (trial * 7 + j * 13) % MUTATOR_POOL.length;
    if (!chosenIndices.includes(idx)) chosenIndices.push(idx);
  }

  const selectedMutators = chosenIndices.map(i => MUTATOR_POOL[i]);
  const targetModule = BASE_DAG_MODULES[trial % BASE_DAG_MODULES.length];

  let compositeSource = targetModule.source;
  for (const mut of selectedMutators) {
    compositeSource = mut.apply(compositeSource, trial);
  }

  const oracleVerdict = evaluateDeepAdversarialOracle(targetModule.source, compositeSource);
  const hOrig = computeSourceSemanticHash(targetModule.source);
  const hMut = computeSourceSemanticHash(compositeSource);
  const linRebuilt = (hOrig !== hMut);

  if (!oracleVerdict.semanticChanged && linRebuilt) {
    fpCases.push({
      trial,
      module: targetModule.id,
      mutators: selectedMutators.map(m => m.name),
      origSource: targetModule.source,
      mutSource: compositeSource,
      hOrig,
      hMut
    });
  }
}

console.log(`Found ${fpCases.length} False Positive Trials:\n`);

const taxonomy = {
  INERT_REFINEMENT_COMMENT: 0,
  UNEXERCISED_MUTATOR_PATTERN: 0,
  SYNTACTIC_SCHEMA_HEADER: 0,
};

for (const fp of fpCases) {
  let category = 'OTHER';
  if (fp.mutators.includes('alter_refinement') && fp.mutSource.includes('// noop_ref')) {
    category = 'INERT_REFINEMENT_COMMENT';
    taxonomy.INERT_REFINEMENT_COMMENT++;
  } else if (fp.mutators.includes('body_semantics') || fp.mutators.includes('alter_exported_symbol')) {
    category = 'UNEXERCISED_MUTATOR_PATTERN';
    taxonomy.UNEXERCISED_MUTATOR_PATTERN++;
  }

  console.log(`Trial ${fp.trial.toString().padStart(3, ' ')} [${fp.module}]: Mutators=[${fp.mutators.join(', ')}] -> Category: ${category}`);
}

console.log('\n--- False Positive Taxonomy Summary ---');
console.log(`1. Inert Refinement Comment Injections: ${taxonomy.INERT_REFINEMENT_COMMENT} (${((taxonomy.INERT_REFINEMENT_COMMENT/fpCases.length)*100).toFixed(1)}%)`);
console.log(`2. Unexercised/Pattern Mismatch Mutators: ${taxonomy.UNEXERCISED_MUTATOR_PATTERN} (${((taxonomy.UNEXERCISED_MUTATOR_PATTERN/fpCases.length)*100).toFixed(1)}%)`);
console.log('----------------------------------------\n');
