#!/usr/bin/env node
/**
 * Gate 11 False Positive Audit — Real-World Production Corpus.
 *
 * Replays the exact Gate 11 benchmark (289 modules: dayjs + underscore),
 * captures every FP case with full diagnostics, and classifies each into
 * a root-cause taxonomy.
 *
 * Output:
 *   1. Per-FP detailed record (file, mutators, source diff, hash diff, oracle reason)
 *   2. Taxonomy summary with counts and percentages
 *   3. gate11_fp_audit.json artifact for downstream analysis
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import {
  buildLinobj,
  computeSourceSemanticHash,
} from '../src/linobj.mjs';
import { emitAilFromSource } from '../src/emitter.mjs';
import { compileLiaToJs } from '../src/compiler.mjs';
import { parseLia } from '../src/compiler.mjs';

const REPOS = [
  {
    name: 'dayjs',
    url: 'https://github.com/iamkun/dayjs.git',
    filterExt: ['.js'],
    exclude: ['test', 'benchmark', 'node_modules'],
    sampleCap: 185,
  },
  {
    name: 'underscore',
    url: 'https://github.com/jashkenas/underscore.git',
    filterExt: ['.js', '.mjs'],
    exclude: ['test', 'docs', 'node_modules'],
    sampleCap: 115,
  },
];

const MUTATOR_POOL = [
  { name: 'formatting', apply: (s) => s.replace(/([A-Za-z0-9_])\+([A-Za-z0-9_])/g, '$1 + $2').replace(/([A-Za-z0-9_])=([A-Za-z0-9_])/g, '$1 = $2').replace(/\n/g, '\n\n  ') },
  { name: 'comment', apply: (s, seed) => `/* block comment ${seed} */\n` + s.replace(/^!([A-Za-z0-9_]+)/gm, '// fn comment\n!$1') },
  { name: 'reorder_exports', apply: (s) => s.replace(/=ex\{([^}]+)\}/, (_, l) => `=ex{${l.split(',').map(x => x.trim()).reverse().join(',')}}`) },
  { name: 'rename_local', apply: (s) => s.replace(/\b_temp\b/g, '_temp_renamed').replace(/\blocal_var\b/g, 'local_var_renamed').replace(/\b_i\b/g, '_i_renamed').replace(/\b_val\b/g, '_val_renamed') },
  { name: 'alter_parameter', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)/, (_, n, p) => `!${n}(${p}${p ? ',' : ''}_extra)`) },
  { name: 'alter_type', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)/, (_, n, p) => `!${n}(${p.split(',').map(x => x + ':string').join(',')})`) },
  { name: 'alter_effect', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)\s*\{/, '!$1($2){\n  console.log("io_audit");\n') },
  { name: 'alter_refinement', apply: (s) => s.includes('/2') ? s.replace(/\/2\)/, '/0)') : s + '\n// noop_ref' },
  { name: 'alter_exported_symbol', apply: (s) => s.replace(/!([A-Za-z0-9_]+)\(([^)]*)\)\s*\{/, '!$1($2){\n  __mut_flag = 99;\n') },
  { name: 'alias_reexport', apply: (s) => s.includes(' as ') ? s.replace(/ as ([a-zA-Z0-9_]+)/, ' as $1_aliased') : s },
  { name: 'dependency_edge', apply: (s, seed) => s + `\n// edge annotation ${seed}` },
  { name: 'body_semantics', apply: (s) => s.includes('+') ? s.replace(/\+/, '-') : s.replace(/\*/, '+') },
];

// ─── Deep Adversarial Oracle (identical to Gate 11 benchmark) ───────────────

function isDeepEquivalent(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a === 'function' && typeof b === 'function') {
    const cleanA = a.toString().replace(/\/\*[\s\S]*?\*\/|\/\/[^\r\n]*/g, '').replace(/\s+/g, '');
    const cleanB = b.toString().replace(/\/\*[\s\S]*?\*\/|\/\/[^\r\n]*/g, '').replace(/\s+/g, '');
    return cleanA === cleanB;
  }
  if (typeof a === 'object' && a !== null && typeof b === 'object' && b !== null) {
    try { return JSON.stringify(a) === JSON.stringify(b); } catch { return false; }
  }
  return false;
}

function evaluateDeepAdversarialOracle(origSource, mutatedSource) {
  try {
    const jsOrig = compileLiaToJs(origSource).js;
    const jsMut = compileLiaToJs(mutatedSource).js;

    const evalMod = (jsCode) => {
      const logs = [];
      const fakeConsole = {
        log: (...args) => logs.push(args.join(' ')),
        warn: (...args) => logs.push(args.join(' ')),
        error: (...args) => logs.push(args.join(' ')),
        info: (...args) => logs.push(args.join(' ')),
      };
      const env = {
        console: fakeConsole,
        process: { env: { NODE_ENV: 'test' }, exit: () => {} },
        module: { exports: {} },
        setTimeout: () => 0, clearTimeout: () => {},
        setInterval: () => 0, clearInterval: () => {},
        setImmediate: () => 0, clearImmediate: () => {},
      };
      const fn = new Function(
        'console', 'process', 'module', 'exports',
        'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
        'setImmediate', 'clearImmediate',
        `${jsCode}; return module.exports;`
      );
      const exp = fn(env.console, env.process, env.module, env.module.exports,
        env.setTimeout, env.clearTimeout, env.setInterval, env.clearInterval,
        env.setImmediate, env.clearImmediate);
      const normalizedExports = typeof exp === 'function'
        ? { [exp.name || 'default']: exp }
        : (exp || {});
      return { exports: normalizedExports, logs, fakeConsole };
    };

    const o1 = evalMod(jsOrig);
    const o2 = evalMod(jsMut);

    const keys1 = Object.keys(o1.exports).sort();
    const keys2 = Object.keys(o2.exports).sort();
    if (JSON.stringify(keys1) !== JSON.stringify(keys2)) {
      return { semanticChanged: true, reason: `EXPORT_KEYS_CHANGED: [${keys1}] vs [${keys2}]` };
    }

    for (const k of keys1) {
      const f1 = o1.exports[k];
      const f2 = o2.exports[k];
      if (typeof f1 === 'function' && typeof f2 === 'function') {
        if (f1.length !== f2.length) {
          return { semanticChanged: true, reason: `ARITY_CHANGED_FOR_${k}: (${f1.length} vs ${f2.length})` };
        }
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
      [1000, 1], [-1000, -1],
      [0.1 + 0.2, 0.3], [1e-15, 2e-15], [Math.PI, Math.E],
      [0, -0], [NaN, 0],
      [0], [1], [-42], [1000], [Math.PI], [NaN], ["test_str"],
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
            console.log = (...a) => l1.push(a.join(' '));
            o1.fakeConsole.log = (...a) => l1.push(a.join(' '));
            res1 = f1(...inp);
          } catch (e) { err1 = e.message; } finally { console.log = origConsole; }
          try {
            console.log = (...a) => l2.push(a.join(' '));
            o2.fakeConsole.log = (...a) => l2.push(a.join(' '));
            res2 = f2(...inp);
          } catch (e) { err2 = e.message; } finally { console.log = origConsole; }

          const resultsIdentical = isDeepEquivalent(res1, res2);
          const errorsIdentical = (err1 === err2);
          const logsIdentical = JSON.stringify(l1) === JSON.stringify(l2);
          if (!resultsIdentical || !errorsIdentical || !logsIdentical) {
            return {
              semanticChanged: true,
              reason: `ADVERSARIAL_DISCREPANCY_${k}_ON_[${inp}]: res:(${res1} vs ${res2}), err:(${err1} vs ${err2}), logs_diff:(${l1.length} vs ${l2.length})`
            };
          }
        }
      }
    }

    return { semanticChanged: false, reason: 'IDENTICAL_BEHAVIOR_AND_CONTRACT' };
  } catch (e) {
    return { semanticChanged: true, reason: `PARSE_ERROR: ${e.message}` };
  }
}

// ─── FP Root-Cause Classifier ───────────────────────────────────────────────

function classifyFP(origSource, mutatedSource, mutatorNames, oracleReason) {
  const prog = parseLia(origSource);
  const mutProg = parseLia(mutatedSource);
  const origExports = new Set((prog.exports || []).map(e => {
    const m = e.match(/^(\S+)\s+as\s+(\S+)$/);
    return m ? m[2] : e.trim();
  }));
  const origFnNames = new Set((prog.fns || []).map(f => f.name));

  // 1. Check if mutation only affected non-exported (internal) functions
  const origFnMap = {};
  for (const f of (prog.fns || [])) origFnMap[f.name] = f;
  const mutFnMap = {};
  for (const f of (mutProg.fns || [])) mutFnMap[f.name] = f;

  const changedFnNames = [];
  for (const name of Object.keys(mutFnMap)) {
    const origFn = origFnMap[name];
    if (!origFn) { changedFnNames.push(name); continue; }
    const origCanon = JSON.stringify({ p: origFn.params, b: origFn.body });
    const mutCanon = JSON.stringify({ p: mutFnMap[name].params, b: mutFnMap[name].body });
    if (origCanon !== mutCanon) changedFnNames.push(name);
  }
  const addedFnNames = Object.keys(mutFnMap).filter(n => !(n in origFnMap));

  const allChangedAreInternal = changedFnNames.every(n => !origExports.has(n)) && addedFnNames.every(n => !origExports.has(n));
  const anyExportChanged = changedFnNames.some(n => origExports.has(n));

  // 2. Check export list changes
  const mutExports = new Set((mutProg.exports || []).map(e => {
    const m = e.match(/^(\S+)\s+as\s+(\S+)$/);
    return m ? m[2] : e.trim();
  }));
  const exportListChanged = JSON.stringify([...origExports].sort()) !== JSON.stringify([...mutExports].sort());

  // 3. Check parameter signature changes
  const paramChanged = changedFnNames.some(n => {
    const o = origFnMap[n];
    const m = mutFnMap[n];
    return o && m && o.params !== m.params;
  });

  // 4. Check for effect injection (console.log, side effects)
  const effectInjected = mutatorNames.includes('alter_effect');

  // 5. Check for dead code injection
  const deadCodeInjected = mutatorNames.includes('alter_exported_symbol') || mutatorNames.includes('dependency_edge');

  // 6. Check for body operator change
  const bodyOperatorChanged = mutatorNames.includes('body_semantics');

  // 7. Check for type annotation change
  const typeChanged = mutatorNames.includes('alter_type');

  // Classification logic
  if (exportListChanged && anyExportChanged) {
    // Export list itself changed (alias rename, export reorder that affects hash)
    if (mutatorNames.includes('alias_reexport')) {
      return 'EXPORT_ALIAS_CONSERVatism';
    }
    if (mutatorNames.includes('reorder_exports')) {
      return 'EXPORT_ORDER_HASH_IMPACT';
    }
    return 'EXPORT_LIST_CHANGE';
  }

  if (paramChanged) {
    return 'PARAMETER_SIGNATURE_CHANGE';
  }

  if (typeChanged) {
    return 'TYPE_ANNOTATION_CHANGE';
  }

  if (allChangedAreInternal && changedFnNames.length > 0) {
    if (effectInjected) {
      return 'EFFECT_TO_NON_EXPORTED';
    }
    if (deadCodeInjected) {
      return 'DEAD_CODE_IN_NON_EXPORTED';
    }
    if (bodyOperatorChanged) {
      return 'BODY_SEMANTICS_IN_HELPER';
    }
    return 'INTERNAL_FUNCTION_CHANGE';
  }

  if (deadCodeInjected && anyExportChanged) {
    return 'DEAD_CODE_IN_EXPORTED';
  }

  if (effectInjected && anyExportChanged) {
    return 'EFFECT_IN_EXPORTED';
  }

  if (bodyOperatorChanged && anyExportChanged) {
    return 'BODY_SEMANTICS_IN_EXPORTED';
  }

  // Check for additive-only changes (comments, annotations, newlines)
  if (mutatorNames.includes('comment') || mutatorNames.includes('dependency_edge')) {
    return 'ANNOTATION_INERT';
  }

  if (mutatorNames.includes('formatting')) {
    return 'FORMATTING_CANONICALIZATION_GAP';
  }

  if (mutatorNames.includes('rename_local')) {
    return 'LOCAL_RENAME_ALPHA_GAP';
  }

  // Fallback: analyze what actually changed
  if (changedFnNames.length === 0 && addedFnNames.length === 0) {
    // Only exports or consts changed
    if (exportListChanged) return 'EXPORT_REORDER_OR_HASH';
    return 'CONST_OR_HEADER_CHANGE';
  }

  return 'MIXED_CAUSE';
}

// ─── File walker ─────────────────────────────────────────────────────────────

function walkFiles(dir, exts, excludes) {
  const results = [];
  function walk(current) {
    for (const item of fs.readdirSync(current)) {
      const full = path.join(current, item);
      const stat = fs.statSync(full);
      if (stat.isDirectory()) {
        if (!excludes.some(ex => item === ex || full.includes(`/${ex}/`))) walk(full);
      } else if (stat.isFile() && exts.some(ext => item.endsWith(ext))) {
        results.push(full);
      }
    }
  }
  walk(dir);
  return results;
}

// ─── Main audit ──────────────────────────────────────────────────────────────

async function runAudit() {
  console.log('=== Gate 11 False Positive Audit — Real-World Corpus ===\n');

  const allFP = [];
  let totalEvaluated = 0;
  let totalTP = 0, totalTN = 0, totalFP = 0, totalFN = 0;
  let totalSemantic = 0, totalNonSemantic = 0;

  for (const repo of REPOS) {
    console.log(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    console.log(`Repository: [${repo.name}]`);
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);

    const cloneDir = path.join(os.tmpdir(), `gate11_fp_${repo.name}_${Date.now().toString(36)}`);
    try {
      execSync(`git clone --depth 1 ${repo.url} "${cloneDir}"`, { stdio: 'pipe' });
      const srcFiles = walkFiles(cloneDir, repo.filterExt, repo.exclude);

      const modules = [];
      for (const file of srcFiles) {
        if (modules.length >= repo.sampleCap) break;
        const srcText = fs.readFileSync(file, 'utf8');
        try {
          const lin = emitAilFromSource(srcText, { shortenLocals: false });
          if (lin && /![A-Za-z_]/.test(lin)) {
            const relPath = path.relative(cloneDir, file);
            const linText = lin.replace(/^@LIA:/, '@LIN:').replace(/^@AIL:/, '@LIN:');
            const jsRes = compileLiaToJs(linText);
            if (jsRes && jsRes.js) {
              modules.push({ file: relPath, sourceText: srcText, linText });
            }
          }
        } catch {}
      }

      console.log(`[CORPUS] Extracted ${modules.length} production LIN modules`);

      let repoFP = 0;

      for (let idx = 0; idx < modules.length; idx++) {
        const m = modules[idx];
        const k = 2 + (idx % 3);
        const chosenIndices = [];
        for (let j = 0; j < k; j++) {
          const mIdx = (idx * 7 + j * 13) % MUTATOR_POOL.length;
          if (!chosenIndices.includes(mIdx)) chosenIndices.push(mIdx);
        }
        const selectedMutators = chosenIndices.map(i => MUTATOR_POOL[i]);

        let mutatedLin = m.linText;
        for (const mut of selectedMutators) {
          mutatedLin = mut.apply(mutatedLin, idx);
        }

        const oracleVerdict = evaluateDeepAdversarialOracle(m.linText, mutatedLin);
        const isGroundTruthSemantic = oracleVerdict.semanticChanged;

        const hOrig = computeSourceSemanticHash(m.linText);
        const hMut = computeSourceSemanticHash(mutatedLin);
        const linRebuilt = (hOrig !== hMut);

        totalEvaluated++;
        if (isGroundTruthSemantic) {
          totalSemantic++;
          if (linRebuilt) totalTP++;
          else { totalFN++; console.error(`[FN] ${m.file} — ${oracleVerdict.reason}`); }
        } else {
          totalNonSemantic++;
          if (!linRebuilt) totalTN++;
          else {
            totalFP++;
            repoFP++;

            const category = classifyFP(
              m.linText, mutatedLin,
              selectedMutators.map(x => x.name),
              oracleVerdict.reason
            );

            allFP.push({
              repo: repo.name,
              file: m.file,
              trialIdx: idx,
              mutators: selectedMutators.map(x => x.name),
              category,
              oracleReason: oracleVerdict.reason,
              hOrig,
              hMut,
              origLinPreview: m.linText.slice(0, 300),
              mutatedLinPreview: mutatedLin.slice(0, 300),
            });
          }
        }
      }

      console.log(`[RESULTS] FP in ${repo.name}: ${repoFP}/${modules.length - (totalTP + totalFN - allFP.length)}`);
    } catch (e) {
      console.error(`Error processing ${repo.name}:`, e.message);
    } finally {
      try { fs.rmSync(cloneDir, { recursive: true, force: true }); } catch {}
    }
  }

  // ─── Taxonomy ────────────────────────────────────────────────────────────

  const taxonomy = {};
  for (const fp of allFP) {
    taxonomy[fp.category] = (taxonomy[fp.category] || 0) + 1;
  }

  const sortedTaxonomy = Object.entries(taxonomy).sort((a, b) => b[1] - a[1]);

  console.log('\n╔══════════════════════════════════════════════════════════╗');
  console.log('║        GATE 11 FALSE POSITIVE AUDIT — RESULTS          ║');
  console.log('╚══════════════════════════════════════════════════════════╝\n');

  console.log(`Total modules evaluated:  ${totalEvaluated}`);
  console.log(`Semantic mutations:       ${totalSemantic}`);
  console.log(`Cosmetic equivalences:    ${totalNonSemantic}`);
  console.log('────────────────────────────────────────────────────────');
  console.log(`TP:  ${totalTP}    TN: ${totalTN}`);
  console.log(`FP:  ${totalFP}    FN: ${totalFN}`);
  console.log('────────────────────────────────────────────────────────');
  console.log(`Recall:     ${(totalTP / (totalSemantic || 1) * 100).toFixed(2)}%`);
  console.log(`Precision:  ${(totalTP / ((totalTP + totalFP) || 1) * 100).toFixed(2)}%`);
  console.log(`Over-invalidation: ${(totalFP / (totalNonSemantic || 1) * 100).toFixed(2)}%`);
  console.log(`Accuracy:   ${((totalTP + totalTN) / (totalEvaluated || 1) * 100).toFixed(2)}%`);

  console.log('\n┌──────────────────────────────────────────────────────────┐');
  console.log('│              FP ROOT-CAUSE TAXONOMY                     │');
  console.log('├──────────────────────────────────────────────────────────┤');
  for (const [cat, count] of sortedTaxonomy) {
    const pct = (count / (totalFP || 1) * 100).toFixed(1);
    const bar = '█'.repeat(Math.round(count / (totalFP || 1) * 40));
    console.log(`│ ${cat.padEnd(38)} ${String(count).padStart(3)} (${pct.padStart(5)}%) ${bar}`);
  }
  console.log('└──────────────────────────────────────────────────────────┘');

  // ─── Per-category detail ──────────────────────────────────────────────────

  console.log('\n┌──────────────────────────────────────────────────────────┐');
  console.log('│           PER-CATEGORY FP DETAILS                       │');
  console.log('└──────────────────────────────────────────────────────────┘');

  for (const [cat] of sortedTaxonomy) {
    const cases = allFP.filter(fp => fp.category === cat);
    console.log(`\n▸ ${cat} (${cases.length} cases)`);
    for (const c of cases.slice(0, 5)) {
      console.log(`  [${c.repo}] ${c.file}`);
      console.log(`    mutators: ${c.mutators.join(', ')}`);
      console.log(`    oracle: ${c.oracleReason.slice(0, 80)}`);
    }
    if (cases.length > 5) console.log(`  ... and ${cases.length - 5} more`);
  }

  // ─── Save artifact ────────────────────────────────────────────────────────

  const artifact = {
    gate: 'GATE_11_FP_AUDIT',
    timestamp: new Date().toISOString(),
    summary: {
      totalEvaluated,
      totalSemantic,
      totalNonSemantic,
      totalTP, totalTN, totalFP, totalFN,
      recall: totalTP / (totalSemantic || 1),
      precision: totalTP / ((totalTP + totalFP) || 1),
      overInvalidation: totalFP / (totalNonSemantic || 1),
      accuracy: (totalTP + totalTN) / (totalEvaluated || 1),
    },
    taxonomy: Object.fromEntries(sortedTaxonomy),
    fpCases: allFP,
  };

  const outPath = path.join(process.cwd(), 'gate11_fp_audit.json');
  fs.writeFileSync(outPath, JSON.stringify(artifact, null, 2));
  console.log(`\n[ARTIFACT] Written to ${outPath}`);

  return artifact;
}

runAudit();
