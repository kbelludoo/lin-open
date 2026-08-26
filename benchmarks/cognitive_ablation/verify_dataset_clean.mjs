/**
 * verify_dataset_clean.mjs — Teste de Execução Comportamental das 30 Tarefas nos seus Oráculos
 */

import fs from 'fs';
import path from 'path';

const BASE_DIR = '/home/k/Downloads/lin-master/benchmarks/cognitive_ablation';
const tasks = JSON.parse(fs.readFileSync(path.join(BASE_DIR, 'MANIFEST.json'), 'utf-8')).tasks;

// Transpiler robusto para executar os candidatos LIN dentro dos oráculos de teste
export function executeLinCandidate(code) {
  let clean = code.replace(/@LIN:[^\n]+\n/g, '').replace(/=ex\{[^\}]+\}/g, '').trim();

  // Substituição de sigilos LIN para JS equivalente
  clean = clean
    .replace(/!([a-zA-Z0-9_]+)\(([^)]*)\)\{/g, 'function $1($2){')
    .replace(/\$([a-zA-Z0-9_]+)\s*=/g, 'let $1 =')
    .replace(/\?\(([^)]+)\)\{/g, 'if ($1) {')
    .replace(/\:\(([^)]+)\)\{/g, '} else if ($1) {')
    .replace(/\:\{/g, '} else {')
    .replace(/\#\(([^;]*);([^;]*);([^)]*)\)\{/g, 'for (let $1; $2; $3) {')
    .replace(/\^([^\n;\}]+)/g, 'return $1');

  const fn = new Function('input', `
    ${clean}
    return solve(input);
  `);

  return fn;
}

const solutions = JSON.parse(fs.readFileSync(path.join(BASE_DIR, 'task_solutions.json'), 'utf-8'));

let allPassed = true;
for (const t of tasks) {
  const task = JSON.parse(fs.readFileSync(path.join(BASE_DIR, 'tasks', t.id + '.json'), 'utf-8'));
  const oracleModule = await import(`file://${path.join(BASE_DIR, t.oracle_entrypoint)}`);
  const res = await oracleModule.oracle(task, { candidate_code: solutions[t.id] });
  if (!res.passed) {
    console.log(`❌ ${t.id} FALHOU no Oráculo:`, res.hint);
    allPassed = false;
  } else {
    console.log(`✅ ${t.id} PASSOU no Oráculo Independente`);
  }
}

if (allPassed) {
  console.log('\n🎯 TODAS AS 30 TAREFAS PASSARAM NOS SEUS RESPECTIVOS ORÁCULOS!');
} else {
  console.log('\n⚠️ Algumas tarefas falharam na execução.');
}
