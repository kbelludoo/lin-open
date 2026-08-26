/**
 * full_30_tasks_audit_test.mjs — Teste de Auditoria de Ponta a Ponta com as 30 Tarefas Reais
 * 
 * Carrega os 30 arquivos JSON e os 30 oráculos dinamicamente,
 * executa o runner sobre uma matriz de trajetórias conhecidas (12 P1, 10 PR, 8 FF)
 * e valida a convergência exata das métricas do dataset congelado.
 */

import fs from 'fs';
import path from 'path';
import assert from 'assert';
import { CognitiveBenchmarkRunner } from './runner.mjs';
import { LinVerifierAdapter } from './lin_verifier_adapter.mjs';
import { MockModelAdapter } from './mock_model_adapter.mjs';

const BASE_DIR = '/home/k/Downloads/lin-master/benchmarks/cognitive_ablation';
const MANIFEST_PATH = path.join(BASE_DIR, 'MANIFEST.json');

async function runFull30Audit() {
  console.log('🔬 Iniciando Auditoria Completa das 30 Tarefas do Dataset V1...');

  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf-8'));
  assert.strictEqual(manifest.total_tasks, 30, 'O manifesto deve conter exatamente 30 tarefas');

  // Carregar todas as tarefas e oráculos
  const tasks = [];
  const oracles = {};

  for (const entry of manifest.tasks) {
    const taskPath = path.join(BASE_DIR, 'tasks', `${entry.id}.json`);
    const task = JSON.parse(fs.readFileSync(taskPath, 'utf-8'));
    tasks.push(task);

    const oracleModulePath = path.join(BASE_DIR, entry.oracle_entrypoint);
    const mod = await import(`file://${oracleModulePath}`);
    oracles[entry.id] = mod.oracle;
  }

  console.log('  ✅ 30 tarefas e 30 oráculos independentes carregados com sucesso.');

  const solutions = JSON.parse(fs.readFileSync(path.join(BASE_DIR, 'task_solutions.json'), 'utf-8'));

  // Configuração da matriz de teste controlado:
  // - T001..T012 (12 tarefas) -> M01 (P1)
  // - T013..T020 (8 tarefas)  -> M02 (PR na tentativa 2)
  // - T021..T022 (2 tarefas)  -> M03 (PR na tentativa 3)
  // - T023..T030 (8 tarefas)  -> M04 (FF em todas as 3)
  const trajectoryMap = {};
  for (let i = 1; i <= 12; i++) {
    const id = `T${String(i).padStart(3, '0')}`;
    trajectoryMap[id] = 'M01';
  }
  for (let i = 13; i <= 20; i++) {
    const id = `T${String(i).padStart(3, '0')}`;
    trajectoryMap[id] = 'M02';
  }
  for (let i = 21; i <= 22; i++) {
    const id = `T${String(i).padStart(3, '0')}`;
    trajectoryMap[id] = 'M03';
  }
  for (let i = 23; i <= 30; i++) {
    const id = `T${String(i).padStart(3, '0')}`;
    trajectoryMap[id] = 'M04';
  }

  const mockAdapter = new MockModelAdapter(trajectoryMap, solutions);
  const verifierAdapter = new LinVerifierAdapter();

  const runner = new CognitiveBenchmarkRunner({
    modelAdapter: mockAdapter,
    verifierAdapter,
    feedbackMode: 'TRAUMA'
  });

  console.log('  🚀 Executando Benchmark Runner sobre as 30 tarefas...');
  const runResult = await runner.runBenchmark({
    tasks,
    oracles,
    manifestSha256: manifest.global_sha256,
    systemId: 'E',
    modelId: 'mock-audit-v1'
  });

  const s = runResult.summary;
  console.log('\n📊 Resumo das Métricas Obtidas:');
  console.log(`  Total Tasks (N): ${s.total_tasks}`);
  console.log(`  P1 (Initial Pass): ${s.initial_pass_p1}`);
  console.log(`  F1 (Initial Fail): ${s.initial_fail_f1}`);
  console.log(`  PR (Recovered Pass): ${s.recovered_pass_pr}`);
  console.log(`  FF (Final Fail): ${s.final_fail_ff}`);
  console.log(`  pass@1: ${s.pass_at_1}`);
  console.log(`  pass@3: ${s.pass_at_k}`);
  console.log(`  RSR (Recovery Success Rate): ${s.recovery_success_rate}`);
  console.log(`  Média de tentativas em sucesso: ${s.avg_attempts_per_pass}`);

  // Asserções matemáticas exatas
  assert.strictEqual(s.total_tasks, 30, 'N deve ser 30');
  assert.strictEqual(s.initial_pass_p1, 12, 'P1 deve ser 12');
  assert.strictEqual(s.initial_fail_f1, 18, 'F1 deve ser 18');
  assert.strictEqual(s.recovered_pass_pr, 10, 'PR deve ser 10');
  assert.strictEqual(s.final_fail_ff, 8, 'FF deve ser 8');
  assert.strictEqual(s.pass_at_1, 0.40, 'pass@1 deve ser 0.40');
  assert.strictEqual(s.pass_at_k, Number((22 / 30).toFixed(6)), 'pass@3 deve ser 22/30 (~0.733333)');
  assert.strictEqual(s.recovery_success_rate, Number((10 / 18).toFixed(6)), 'RSR deve ser 10/18 (~0.555556)');

  console.log('\n🔒 AUDITORIA DAS 30 TAREFAS PASSOU COM SUCESSO ABSOLUTO!');
  console.log(`🔒 Dataset Congelado: ${manifest.dataset_id} | SHA-256: ${manifest.global_sha256}`);
}

runFull30Audit().catch(err => {
  console.error('❌ ERRO NA AUDITORIA COMPLETA:', err);
  process.exit(1);
});
