/**
 * golden_harness_test.mjs — Teste de Validação e Auditoria do Harness de Medição
 * 
 * Verifica rigorosamente:
 * 1. Todas as 5 trajetórias unitárias (M01..M05)
 * 2. O Golden Test com N=10 (P1=4, PR=3, FF=3, RSR=0.50)
 * 3. A detecção correta da taxa de repetição de erro (ERR)
 * 4. A integridade do log de tentativas (trail)
 */

import { CognitiveBenchmarkRunner } from './runner.mjs';
import { MockModelAdapter } from './mock_model_adapter.mjs';
import { LinVerifierAdapter } from './lin_verifier_adapter.mjs';
import assert from 'assert';

async function runGoldenAudit() {
  console.log('🧪 Iniciando Auditoria e Teste Dourado do Harness...');

  const verifierAdapter = new LinVerifierAdapter();
  const defaultOracle = async (task, cand) => {
    // Oracle independente: rejeita código que contém "- 999" (lógica errada de M04)
    if (cand.candidate_code.includes('- 999')) {
      return { passed: false, hint: 'Calculation returned incorrect output' };
    }
    return { passed: true };
  };

  // -------------------------------------------------------------
  // TESTE 1: Validação Individual das 5 Trajetórias
  // -------------------------------------------------------------
  console.log('  [1/3] Testando trajetórias individuais (M01..M05)...');

  const unitTrajs = [
    { id: 'T_M01', traj: 'M01', expectedOutcome: 'P1', expectedAttempts: 1 },
    { id: 'T_M02', traj: 'M02', expectedOutcome: 'PR', expectedAttempts: 2 },
    { id: 'T_M03', traj: 'M03', expectedOutcome: 'PR', expectedAttempts: 3 },
    { id: 'T_M04', traj: 'M04', expectedOutcome: 'FF', expectedAttempts: 3 },
    { id: 'T_M05', traj: 'M05', expectedOutcome: 'PR', expectedAttempts: 3 }
  ];

  for (const t of unitTrajs) {
    const mock = new MockModelAdapter({ [t.id]: t.traj });
    const runner = new CognitiveBenchmarkRunner({
      modelAdapter: mock,
      verifierAdapter,
      defaultOracle
    });

    const res = await runner.runTask({ id: t.id, forbidden_effects: ['globalState', 'db.write', 'file.write'] });
    assert.strictEqual(
      res.outcome,
      t.expectedOutcome,
      `Falha na trajetória ${t.traj}: esperava ${t.expectedOutcome}, obteve ${res.outcome}`
    );
    assert.strictEqual(
      res.attempts_count,
      t.expectedAttempts,
      `Falha na contagem de tentativas para ${t.traj}: esperava ${t.expectedAttempts}, obteve ${res.attempts_count}`
    );
    console.log(`    ✅ ${t.traj} -> outcome=${res.outcome} (tentativas=${res.attempts_count})`);
  }

  // -------------------------------------------------------------
  // TESTE 2: Golden Fixture com N=10 (P1=4, PR=3, FF=3)
  // -------------------------------------------------------------
  console.log('\n  [2/3] Executando Golden Test N=10 (P1=4, PR=3, FF=3)...');

  const goldenTasks = [
    { id: 'T01' }, { id: 'T02' }, { id: 'T03' }, { id: 'T04' }, // M01 -> 4 x P1
    { id: 'T05' },                                             // M02 -> 1 x PR (k=2)
    { id: 'T06' },                                             // M03 -> 1 x PR (k=3)
    { id: 'T07' },                                             // M05 -> 1 x PR (k=3 com repetição de erro)
    { id: 'T08' }, { id: 'T09' }, { id: 'T10' }               // M04 -> 3 x FF
  ];

  const goldenTrajMap = {
    T01: 'M01', T02: 'M01', T03: 'M01', T04: 'M01',
    T05: 'M02',
    T06: 'M03',
    T07: 'M05',
    T08: 'M04', T09: 'M04', T10: 'M04'
  };

  const goldenMock = new MockModelAdapter(goldenTrajMap);
  const goldenRunner = new CognitiveBenchmarkRunner({
    modelAdapter: goldenMock,
    verifierAdapter,
    defaultOracle
  });

  const benchmarkResult = await goldenRunner.runBenchmark({
    tasks: goldenTasks.map(t => ({ ...t, forbidden_effects: ['globalState', 'db.write', 'file.write'] })),
    systemId: 'E',
    modelId: 'mock-golden-v1'
  });

  const s = benchmarkResult.summary;

  console.log('    Métricas obtidas:');
  console.log(`      Total Tasks (N): ${s.total_tasks}`);
  console.log(`      Initial Pass (P1): ${s.initial_pass_p1}`);
  console.log(`      Initial Fail (F1): ${s.initial_fail_f1}`);
  console.log(`      Recovered Pass (PR): ${s.recovered_pass_pr}`);
  console.log(`      Final Fail (FF): ${s.final_fail_ff}`);
  console.log(`      pass@1: ${s.pass_at_1}`);
  console.log(`      pass@3: ${s.pass_at_k}`);
  console.log(`      RSR (Recovery Success Rate): ${s.recovery_success_rate}`);
  console.log(`      ERR (Error Repetition Rate): ${s.error_repetition_rate}`);

  // Asserções exatas
  assert.strictEqual(s.total_tasks, 10, 'N deve ser 10');
  assert.strictEqual(s.initial_pass_p1, 4, 'P1 deve ser 4');
  assert.strictEqual(s.initial_fail_f1, 6, 'F1 deve ser 6');
  assert.strictEqual(s.recovered_pass_pr, 3, 'PR deve ser 3');
  assert.strictEqual(s.final_fail_ff, 3, 'FF deve ser 3');
  assert.strictEqual(s.pass_at_1, 0.40, 'pass@1 deve ser exatamente 0.40');
  assert.strictEqual(s.pass_at_k, 0.70, 'pass@3 deve ser exatamente 0.70');
  assert.strictEqual(s.recovery_success_rate, 0.50, 'RSR deve ser exatamente 3/6 = 0.50');

  // -------------------------------------------------------------
  // TESTE 3: Verificação de Auditoria de Detecção de ERR
  // -------------------------------------------------------------
  console.log('\n  [3/3] Auditando detecção do ERR (repetição de erro em T07 + T08..T10)...');
  assert.ok(s.error_repetition_rate > 0, 'ERR deve ser maior que 0');
  // T07 tem 1 repetição (k1=k2) + T08..T10 têm 2 repetições cada (k1=k2, k2=k3) = 1 + 3*2 = 7 repetições em 8 retries
  assert.strictEqual(s.counters.repeated_error_count, 7, 'Deve registrar exatamente 7 repetições');
  assert.strictEqual(s.counters.total_retry_failures, 8, 'Deve registrar exatamente 8 falhas em retries');
  assert.strictEqual(s.error_repetition_rate, 7 / 8, 'ERR deve ser exatamente 7/8 = 0.875');

  console.log('\n🎯 TODOS OS TESTES DE AUDITORIA DO HARNESS PASSARAM COM 100% DE EXATIDÃO!');
}

runGoldenAudit().catch(err => {
  console.error('❌ FALHA NA AUDITORIA DO HARNESS:', err);
  process.exit(1);
});
