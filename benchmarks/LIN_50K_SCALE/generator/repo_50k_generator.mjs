// 50,000 Lines of Code Dual-Emitter: JS Modular System + Native LIN (.lin)

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const JS_DIR = path.join(ROOT, 'repo_js');
const LIN_DIR = path.join(ROOT, 'repo_lin');

const MODULE_DOMAINS = [
  'math_algebra',
  'tensor_ops',
  'string_parser',
  'token_stream',
  'ast_graph',
  'symbol_table',
  'crypto_hash',
  'data_struct',
  'state_machine',
  'pipeline_exec'
];

export function generate50kCodebase(numModules = 130) {
  console.log(`[+] Generating 50k LOC Codebase across ${numModules} modules in JS and Native LIN...`);

  fs.rmSync(JS_DIR, { recursive: true, force: true });
  fs.rmSync(LIN_DIR, { recursive: true, force: true });
  fs.mkdirSync(path.join(JS_DIR, 'src'), { recursive: true });
  fs.mkdirSync(path.join(JS_DIR, 'tests'), { recursive: true });
  fs.mkdirSync(path.join(LIN_DIR, 'src'), { recursive: true });

  const moduleIndex = [];
  let totalJSLines = 0;
  let totalLINLines = 0;

  for (let m = 0; m < numModules; m++) {
    const domain = MODULE_DOMAINS[m % MODULE_DOMAINS.length];
    const modTag = `m${String(m).padStart(3, '0')}`;
    const modName = `mod_${String(m).padStart(3, '0')}_${domain}`;
    const jsPath = path.join(JS_DIR, 'src', `${modName}.js`);
    const linPath = path.join(LIN_DIR, 'src', `${modName}.lin`);

    const functions = [];
    const numFuncs = 12; // 12 functions per module

    for (let f = 0; f < numFuncs; f++) {
      const fnName = `${modTag}_${domain}_fn_${f}`;
      functions.push({
        name: fnName,
        idx: f,
        effect: f % 4 === 0 ? 'Pure' : f % 4 === 1 ? 'Read' : f % 4 === 2 ? 'Write' : 'Pure',
        invariants: [
          `ret !== undefined`,
          `typeof ret === "number"`
        ]
      });
    }

    // Build JS Content
    let jsContent = `// Module: ${modName} (50k LOC Scale Target)\n\n`;
    if (m > 0) {
      const prevMod = moduleIndex[m - 1];
      jsContent += `import { ${prevMod.functions[0].name} } from './${prevMod.name}.js';\n\n`;
    }

    for (const fn of functions) {
      jsContent += `/**\n * @function ${fn.name}\n * Effect: *(${fn.effect})\n */\n`;
      jsContent += `export function ${fn.name}(x, y = 10, config = {}) {\n`;
      jsContent += `  if (x === null || x === undefined) {\n`;
      jsContent += `    return 0;\n`;
      jsContent += `  }\n`;
      jsContent += `  let accumulator = typeof x === 'number' ? x : 42;\n`;
      jsContent += `  let multiplier = typeof y === 'number' ? y : 2;\n`;
      jsContent += `  let state = config.initialState || 'READY';\n`;
      jsContent += `  \n`;
      jsContent += `  // Algorithmic processing loop\n`;
      jsContent += `  for (let step = 0; step < 8; step++) {\n`;
      jsContent += `    if (step % 2 === 0) {\n`;
      jsContent += `      accumulator = (accumulator * multiplier + step) % 10007;\n`;
      jsContent += `    } else {\n`;
      jsContent += `      accumulator = (accumulator - step * 3 + 10007) % 10007;\n`;
      jsContent += `    }\n`;
      jsContent += `    if (accumulator < 0) accumulator = 0;\n`;
      jsContent += `  }\n`;
      jsContent += `  \n`;
      jsContent += `  // Validation branch\n`;
      jsContent += `  if (state === 'READY') {\n`;
      jsContent += `    state = 'PROCESSED';\n`;
      jsContent += `  } else {\n`;
      jsContent += `    state = 'FALLBACK';\n`;
      jsContent += `  }\n`;
      jsContent += `  \n`;
      if (m > 0 && fn.idx === 0) {
        const prevFn = moduleIndex[m - 1].functions[0].name;
        jsContent += `  const chainVal = ${prevFn}(accumulator, 2);\n`;
        jsContent += `  accumulator = (accumulator + chainVal) % 10007;\n`;
      }
      jsContent += `  return accumulator;\n`;
      jsContent += `}\n\n`;
    }

    // Build LIN Content (.lin)
    let linContent = `@m{name="${modName}" domain="${domain}"}\n`;
    if (m > 0) {
      const prevMod = moduleIndex[m - 1];
      linContent += `~dep{mod="${prevMod.name}" sym="${prevMod.functions[0].name}"}\n`;
    }
    linContent += `\n`;

    for (const fn of functions) {
      linContent += `!fn ${fn.name}(x, y, config) *(${fn.effect}) {\n`;
      for (const inv of fn.invariants) {
        linContent += `  %inv{${inv}}\n`;
      }
      linContent += `  ?(!x) ^0\n`;
      linContent += `  $acc = (typeof x == 'num' ? x : 42)\n`;
      linContent += `  $mul = (typeof y == 'num' ? y : 2)\n`;
      linContent += `  #step(0..8) {\n`;
      linContent += `    ?(step % 2 == 0) $acc = ($acc * $mul + step) % 10007\n`;
      linContent += `    : $acc = ($acc - step * 3 + 10007) % 10007\n`;
      linContent += `  }\n`;
      if (m > 0 && fn.idx === 0) {
        const prevFn = moduleIndex[m - 1].functions[0].name;
        linContent += `  $acc = ($acc + ${prevFn}($acc, 2)) % 10007\n`;
      }
      linContent += `  ^$acc\n`;
      linContent += `}\n\n`;
    }

    fs.writeFileSync(jsPath, jsContent, 'utf8');
    fs.writeFileSync(linPath, linContent, 'utf8');

    const jsLines = jsContent.split('\n').length;
    const linLines = linContent.split('\n').length;
    totalJSLines += jsLines;
    totalLINLines += linLines;

    moduleIndex.push({
      name: modName,
      jsPath: `src/${modName}.js`,
      linPath: `src/${modName}.lin`,
      functions
    });
  }

  // Generate Test Runner for JS
  let testRunnerContent = `// 50k LOC Global Test Suite\nimport assert from 'assert';\n\n`;
  for (let m = 0; m < moduleIndex.length; m++) {
    const mod = moduleIndex[m];
    testRunnerContent += `import { ${mod.functions[0].name} } from '../src/${mod.name}.js';\n`;
  }
  testRunnerContent += `\nlet passed = 0;\nlet failed = 0;\n\n`;
  testRunnerContent += `try {\n`;
  for (let m = 0; m < moduleIndex.length; m++) {
    const mod = moduleIndex[m];
    const fnName = mod.functions[0].name;
    testRunnerContent += `  assert(typeof ${fnName}(10) === 'number', '${fnName} must return number');\n`;
    testRunnerContent += `  passed++;\n`;
  }
  testRunnerContent += `  console.log('Overall: PASS (' + passed + ' tests passed)');\n`;
  testRunnerContent += `} catch (err) {\n`;
  testRunnerContent += `  console.error('Overall: FAIL', err.message);\n`;
  testRunnerContent += `  process.exit(1);\n`;
  testRunnerContent += `}\n`;

  fs.writeFileSync(path.join(JS_DIR, 'tests/test_runner.js'), testRunnerContent, 'utf8');
  totalJSLines += testRunnerContent.split('\n').length;

  const manifest = {
    total_js_lines: totalJSLines,
    total_lin_lines: totalLINLines,
    compression_ratio: Number((totalJSLines / totalLINLines).toFixed(2)),
    num_modules: moduleIndex.length,
    total_functions: moduleIndex.length * 12,
    modules: moduleIndex
  };

  fs.writeFileSync(path.join(ROOT, 'dataset/50k_manifest.json'), JSON.stringify(manifest, null, 2));

  console.log(`[+] 50k Codebase Generated Successfully!`);
  console.log(`    - Total JS Lines: ${totalJSLines.toLocaleString()} lines across ${numModules} modules`);
  console.log(`    - Total LIN Lines: ${totalLINLines.toLocaleString()} lines (.lin native)`);
  console.log(`    - Structural Compression Ratio: ${manifest.compression_ratio}x`);
  return manifest;
}

generate50kCodebase(130);
