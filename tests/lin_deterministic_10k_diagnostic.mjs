import { execFileSync } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import assert from 'node:assert/strict';

const RUST_DIR = path.resolve('src_rust');
const RUST_BIN = path.resolve('bin/lin_rust');
const MAIN_RS = path.resolve(RUST_DIR, 'src/main.rs');
const BACKUP_MAIN_RS = path.resolve(RUST_DIR, 'src/main.rs.bak');

const SEED = 20260821;
const TOTAL_PROGRAMS = 10000;
const BATCH_SIZE = 1000;
const MAX_DEPTH = 4;

console.log('================================================================');
console.log(`   DIAGNÓSTICO DETERMINÍSTICO 10K (PRNG SEED: ${SEED})          `);
console.log('================================================================\n');

// ---------------------------------------------------------------------------------
// 1. PRNG DETERMINÍSTICO LCG
// ---------------------------------------------------------------------------------
let state = SEED;
function seededRandom() {
  state = (state * 1664525 + 1013904223) % 4294967296;
  return state / 4294967296;
}

function randomChoice(arr) {
  return arr[Math.floor(seededRandom() * arr.length)];
}

function randomInt(min, max) {
  return Math.floor(seededRandom() * (max - min + 1)) + min;
}

// ---------------------------------------------------------------------------------
// 2. GERADOR DETERMINÍSTICO DE EXPRESSÕES PURAS COM NÓS DE LOOP INVENTARIADOS
// ---------------------------------------------------------------------------------
const BIN_OPS = ['+', '-', '*', '==', '!=', '<', '>', '<=', '>=', '&&', '||'];

function generateAst(depth, vars) {
  if (depth <= 1 || seededRandom() < 0.25) {
    const leafKind = seededRandom();
    if (leafKind < 0.4 && vars.length > 0) {
      return { type: 'var', name: randomChoice(vars) };
    } else if (leafKind < 0.7) {
      return { type: 'num', value: randomInt(-20, 50) };
    } else if (leafKind < 0.85) {
      return { type: 'str', value: `str_${randomInt(1, 50)}` };
    } else {
      return { type: 'bool', value: seededRandom() < 0.5 };
    }
  }

  const opKind = seededRandom();
  if (opKind < 0.6) {
    const op = randomChoice(BIN_OPS);
    const left = generateAst(depth - 1, vars);
    const right = generateAst(depth - 1, vars);
    return { type: 'binary', op, left, right };
  } else if (opKind < 0.8) {
    const len = randomInt(1, 3);
    const elements = [];
    for (let i = 0; i < len; i++) elements.push(generateAst(depth - 1, vars));
    return { type: 'array', elements };
  } else {
    return { type: 'unary', op: '!', arg: generateAst(depth - 1, vars) };
  }
}

function emitLin(node) {
  switch (node.type) {
    case 'var': return node.name;
    case 'num': return String(node.value);
    case 'str': return `"${node.value}"`;
    case 'bool': return String(node.value);
    case 'binary': return `(${emitLin(node.left)}${node.op}${emitLin(node.right)})`;
    case 'unary': return `(!${emitLin(node.arg)})`;
    case 'array': return `[${node.elements.map(emitLin).join(',')}]`;
    default: return 'null';
  }
}

function emitJs(node) {
  switch (node.type) {
    case 'var': return node.name;
    case 'num': return String(node.value);
    case 'str': return `"${node.value}"`;
    case 'bool': return String(node.value);
    case 'binary': return `(${emitJs(node.left)} ${node.op} ${emitJs(node.right)})`;
    case 'unary': return `(!${emitJs(node.arg)})`;
    case 'array': return `[${node.elements.map(emitJs).join(',')}]`;
    default: return 'null';
  }
}

// ---------------------------------------------------------------------------------
// 3. GERAÇÃO DO CORPUS DETERMINÍSTICO DE 10.000 PROGRAMAS
// ---------------------------------------------------------------------------------
console.log('▶ [FASE 1: GERANDO CORPUS DETERMINÍSTICO COM SEED FIXA]...');

const allPrograms = [];
const allJsOracles = [];
const allArgs = [];

for (let i = 0; i < TOTAL_PROGRAMS; i++) {
  const fnName = `prog_${i + 1}`;
  const vars = ['a', 'b', 'c'];
  const depth = randomInt(2, MAX_DEPTH);
  const ast = generateAst(depth, vars);

  const linCode = `!${fnName}(a,b,c){res=${emitLin(ast)};^res}`;
  const jsCode = `(a, b, c) => { return ${emitJs(ast)}; }`;

  allPrograms.push({ fnName, linCode, ast });
  allJsOracles.push(eval(jsCode));
  allArgs.push([randomInt(-10, 30), randomInt(-10, 30), randomInt(-10, 30)]);
}

console.log(`✔ Corpus 100% reproduzível gerado: ${TOTAL_PROGRAMS} programas.\n`);

// ---------------------------------------------------------------------------------
// 4. DIAGNÓSTICO DETALHADO DE CADA MISMATCH NO BASELINE
// ---------------------------------------------------------------------------------
console.log('▶ [FASE 2: EXECUTANDO BASELINE E CLASSIFICANDO DIVERGÊNCIAS CASO A CASO]...');

const baselineResults = [];
const mismatches = [];
const categories = {
  STRING_NUMBER_COERCION: 0,
  BOOLEAN_SHORT_CIRCUIT_VALUE_PROPAGATION: 0,
  TYPE_MISMATCH_OBJECT_ARRAY: 0,
  OTHER: 0
};

for (let batch = 0; batch < 10; batch++) {
  const startIdx = batch * BATCH_SIZE;
  const endIdx = startIdx + BATCH_SIZE;
  const batchProgs = allPrograms.slice(startIdx, endIdx);
  const batchFile = `/tmp/lin_diag_batch_${batch}.lin`;

  const linContent = `@LIN:L1c:0.2\n^schema_once ^lossy=true ^ops=diag_${batch}\n~G{?=if #=for ^=ret :else}\n\n${batchProgs.map(p => p.linCode).join('\n')}\n\n=ex{${batchProgs.map(p => p.fnName).join(',')}}\n`;
  fs.writeFileSync(batchFile, linContent);

  for (let i = startIdx; i < endIdx; i++) {
    const prog = allPrograms[i];
    const args = allArgs[i];
    const jsFn = allJsOracles[i];

    let jsResult = jsFn(...args);
    let linResult;

    try {
      const stdout = execFileSync(RUST_BIN, ['call', batchFile, prog.fnName, JSON.stringify(args)], {
        encoding: 'utf8',
        stdio: ['pipe', 'pipe', 'pipe']
      });
      linResult = JSON.parse(stdout.trim());
    } catch (e) {
      linResult = '__RUNTIME_ERROR__';
    }

    baselineResults.push(linResult);

    // Verificação de equivalência
    let isMatch = false;
    if (typeof jsResult === 'boolean' || typeof linResult === 'boolean') {
      isMatch = Boolean(linResult) === Boolean(jsResult);
    } else if (typeof jsResult === 'number' && typeof linResult === 'number') {
      isMatch = (linResult === jsResult) || Math.abs(linResult - jsResult) < 1e-4;
    } else {
      isMatch = JSON.stringify(linResult) === JSON.stringify(jsResult);
    }

    if (!isMatch) {
      let category = 'OTHER';
      if (typeof jsResult === 'string' && typeof linResult === 'number' || typeof jsResult === 'number' && typeof linResult === 'string') {
        category = 'STRING_NUMBER_COERCION';
      } else if (typeof jsResult !== typeof linResult) {
        category = 'BOOLEAN_SHORT_CIRCUIT_VALUE_PROPAGATION';
      }
      categories[category] = (categories[category] || 0) + 1;

      if (mismatches.length < 50) {
        mismatches.push({
          case_id: i + 1,
          lin_code: prog.linCode,
          args,
          js_expected: jsResult,
          lin_actual: linResult,
          category
        });
      }
    }
  }

  try { fs.unlinkSync(batchFile); } catch (e) {}
}

const totalMismatches = Object.values(categories).reduce((a, b) => a + b, 0);
const totalMatches = TOTAL_PROGRAMS - totalMismatches;

console.log('================================================================');
console.log('   RESULTADOS DO DIAGNÓSTICO BASELINE (10.000 ASTs REPRODUZÍVEIS)');
console.log('================================================================');
console.log(`  programs_generated:       ${TOTAL_PROGRAMS}`);
console.log(`  matches:                  ${totalMatches}`);
console.log(`  total_mismatches:         ${totalMismatches}`);
console.log(`  behavior_eq:              ${(totalMatches / TOTAL_PROGRAMS).toFixed(4)}`);
console.log('\n  ▶ Distribuição de Categorias das Divergências:');
for (const [k, v] of Object.entries(categories)) {
  console.log(`    - ${k.padEnd(45)}: ${v} casos`);
}

fs.mkdirSync('storage', { recursive: true });
fs.writeFileSync('storage/lin_10k_mismatches.json', JSON.stringify({
  seed: SEED,
  total_programs: TOTAL_PROGRAMS,
  matches: totalMatches,
  categories,
  sample_counterexamples: mismatches
}, null, 2));

console.log('\n✔ Log de diagnóstico detalhado salvo em: storage/lin_10k_mismatches.json\n');

// ---------------------------------------------------------------------------------
// 5. MUTATION TESTING DISCRETO CASO A CASO (baseline[i] !== mutant[i])
// ---------------------------------------------------------------------------------
console.log('▶ [FASE 3: MUTATION TESTING COM COMPARAÇÃO CASO A CASO (baseline[i] != mutant[i])]...\n');

fs.copyFileSync(MAIN_RS, BACKUP_MAIN_RS);

const MUTANTS = [
  {
    id: "M1",
    desc: "Corrupção de Aritmética (+ para -) em js_add",
    from: "        (Some(a), Some(b)) => make_number(a + b),",
    to:   "        (Some(a), Some(b)) => make_number(a - b),"
  },
  {
    id: "M2",
    desc: "Inversão da lógica de curto-circuito em '&&' (!is_truthy para is_truthy)",
    from: "        if !is_truthy(&v1) { return v1; }",
    to:   "        if is_truthy(&v1) { return v1; }"
  },
  {
    id: "M3",
    desc: "Corrupção de Comparação Relacional (< para <=) em js_rel_lt",
    from: "        (Some(na), Some(nb)) => Some(na < nb),",
    to:   "        (Some(na), Some(nb)) => Some(na <= nb),"
  }
];

let validKills = 0;

try {
  for (const mut of MUTANTS) {
    console.log(`▶ Injetando Mutante ${mut.id}: ${mut.desc}...`);

    let src = fs.readFileSync(BACKUP_MAIN_RS, 'utf8');
    assert.ok(src.includes(mut.from), `Snippet not found for ${mut.id}`);
    src = src.replace(mut.from, mut.to);
    fs.writeFileSync(MAIN_RS, src);

    execFileSync('cargo', ['build', '--release', '--manifest-path', path.join(RUST_DIR, 'Cargo.toml')], { stdio: 'pipe' });
    execFileSync('cp', [path.join(RUST_DIR, 'target/release/lin_runtime'), RUST_BIN]);

    let killingCases = 0;

    for (let batch = 0; batch < 10; batch++) {
      const startIdx = batch * BATCH_SIZE;
      const endIdx = startIdx + BATCH_SIZE;
      const batchProgs = allPrograms.slice(startIdx, endIdx);
      const batchFile = `/tmp/lin_mut_batch_${batch}.lin`;

      const linContent = `@LIN:L1c:0.2\n^schema_once ^lossy=true ^ops=mut_${batch}\n~G{?=if #=for ^=ret :else}\n\n${batchProgs.map(p => p.linCode).join('\n')}\n\n=ex{${batchProgs.map(p => p.fnName).join(',')}}\n`;
      fs.writeFileSync(batchFile, linContent);

      for (let i = startIdx; i < endIdx; i++) {
        const prog = allPrograms[i];
        const args = allArgs[i];
        const baseResult = baselineResults[i];

        let mutResult;
        try {
          const stdout = execFileSync(RUST_BIN, ['call', batchFile, prog.fnName, JSON.stringify(args)], {
            encoding: 'utf8',
            stdio: ['pipe', 'pipe', 'pipe']
          });
          mutResult = JSON.parse(stdout.trim());
        } catch (e) {
          mutResult = '__MUTANT_RUNTIME_ERROR__';
        }

        if (JSON.stringify(mutResult) !== JSON.stringify(baseResult)) {
          killingCases++;
        }
      }

      try { fs.unlinkSync(batchFile); } catch (e) {}
    }

    if (killingCases > 0) {
      console.log(`  ✔ MUTANTE ${mut.id} KILLED! (${killingCases}/10.000 casos alteraram a saída em relação ao baseline)\n`);
      validKills++;
    } else {
      console.log(`  ❌ MUTANTE ${mut.id} SURVIVED! (0 casos discriminantes)\n`);
    }
  }
} finally {
  fs.copyFileSync(BACKUP_MAIN_RS, MAIN_RS);
  fs.unlinkSync(BACKUP_MAIN_RS);
  execFileSync('cargo', ['build', '--release', '--manifest-path', path.join(RUST_DIR, 'Cargo.toml')], { stdio: 'pipe' });
  execFileSync('cp', [path.join(RUST_DIR, 'target/release/lin_runtime'), RUST_BIN]);
  console.log('✔ Runtime Rust limpo restaurado.');
}

console.log('================================================================');
console.log(`   MUTATION SCORE CASO A CASO (baseline[i] != mutant[i]):       `);
console.log(`   ${validKills}/${MUTANTS.length} Mutantes Eliminados com Evidência Direta (${((validKills / MUTANTS.length) * 100).toFixed(0)}%)`);
console.log('================================================================\n');
