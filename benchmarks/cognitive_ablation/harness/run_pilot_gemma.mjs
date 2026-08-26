/**
 * run_pilot_gemma.mjs — Execução do Teste Piloto com gemma-4-E2B-it
 */

import fs from 'fs';
import path from 'path';
import assert from 'assert';
import { CognitiveBenchmarkRunner } from './runner.mjs';
import { RealModelAdapter } from './real_model_adapter.mjs';
import { LinVerifierAdapter } from './lin_verifier_adapter.mjs';

const EXPECTED_MANIFEST_SHA256 = 'd3951769e4f9d210657a93659deee8b3ccc611e2f0f309373bc8fa358bec3061';
const BASE_DIR = '/home/k/Downloads/lin-master/benchmarks/cognitive_ablation';
const MODEL_NAME = 'hf.co/lmstudio-community/gemma-4-E2B-it-GGUF:Q4_K_M';
const RUNS_DIR = path.join(BASE_DIR, 'runs', 'COGNITIVE_ABLATION_PILOT_GEMMA4');

async function main() {
  console.log(`🚀 Iniciando Teste Piloto com Modelo Gemma4 (${MODEL_NAME})...`);

  const manifestPath = path.join(BASE_DIR, 'MANIFEST.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  assert.strictEqual(
    manifest.global_sha256,
    EXPECTED_MANIFEST_SHA256,
    'VIOLAÇÃO DE INTEGRIDADE: O SHA-256 do manifesto não coincide com a versão congelada!'
  );
  console.log(`🔒 Manifesto verificado com sucesso: ${manifest.global_sha256.slice(0, 16)}...`);

  const pilotTaskIds = ['T001', 'T007', 'T013', 'T019', 'T025'];
  const tasks = [];
  const oracles = {};

  for (const id of pilotTaskIds) {
    const task = JSON.parse(fs.readFileSync(path.join(BASE_DIR, 'tasks', `${id}.json`), 'utf-8'));
    tasks.push(task);
    const mod = await import(`file://${path.join(BASE_DIR, 'oracles', `oracle_${id}.mjs`)}`);
    oracles[id] = mod.oracle;
  }
  console.log(`📋 5 Tarefas do Piloto carregadas: ${pilotTaskIds.join(', ')}`);

  const verifierAdapter = new LinVerifierAdapter();

  const systems = [
    {
      id: 'B',
      name: 'Gemma4 JS Baseline (Zero-Shot)',
      promptMode: 'NATURAL_JS',
      feedbackMode: 'NONE',
      maxAttempts: 1
    },
    {
      id: 'C',
      name: 'Gemma4 LIN Representation (Zero-Shot)',
      promptMode: 'LIN_ZERO_SHOT',
      feedbackMode: 'NONE',
      maxAttempts: 1
    },
    {
      id: 'D',
      name: 'Gemma4 LIN Unstructured Loop (Retry k=3)',
      promptMode: 'LIN_UNSTRUCTURED',
      feedbackMode: 'UNSTRUCTURED',
      maxAttempts: 3
    },
    {
      id: 'E',
      name: 'Gemma4 LIN Full Cognitive + TRAUMA (k=3)',
      promptMode: 'LIN_TRAUMA',
      feedbackMode: 'TRAUMA',
      maxAttempts: 3
    }
  ];

  const pilotSummary = {};

  for (const sys of systems) {
    console.log(`\n======================================================`);
    console.log(`▶ Executando Sistema ${sys.id}: ${sys.name}`);
    console.log(`======================================================`);

    const modelAdapter = new RealModelAdapter({
      baseUrl: 'http://localhost:11434',
      provider: 'ollama',
      model: MODEL_NAME,
      temperature: 0.0,
      seed: 42,
      promptMode: sys.promptMode
    });

    const meta = await modelAdapter.getModelMetadata();

    const runner = new CognitiveBenchmarkRunner({
      modelAdapter,
      verifierAdapter,
      options: {
        maxAttempts: sys.maxAttempts,
        feedbackMode: sys.feedbackMode
      }
    });

    const runResult = await runner.runBenchmark({
      tasks,
      oracles,
      manifestSha256: manifest.global_sha256,
      systemId: sys.id,
      modelId: MODEL_NAME
    });

    runResult.model_metadata = meta;

    const sysRunDir = path.join(RUNS_DIR, sys.id);
    fs.mkdirSync(sysRunDir, { recursive: true });

    fs.writeFileSync(
      path.join(sysRunDir, 'config.json'),
      JSON.stringify({
        system_id: sys.id,
        system_name: sys.name,
        prompt_mode: sys.promptMode,
        feedback_mode: sys.feedbackMode,
        max_attempts: sys.maxAttempts,
        model_metadata: meta,
        manifest_sha256: manifest.global_sha256
      }, null, 2)
    );

    fs.writeFileSync(
      path.join(sysRunDir, 'task_results.json'),
      JSON.stringify(runResult.task_results, null, 2)
    );

    fs.writeFileSync(
      path.join(sysRunDir, 'metrics.json'),
      JSON.stringify(runResult.summary, null, 2)
    );

    pilotSummary[sys.id] = runResult.summary;

    console.log(`  Resultado Sistema ${sys.id}:`);
    console.log(`    pass@1: ${runResult.summary.pass_at_1}`);
    console.log(`    pass@k: ${runResult.summary.pass_at_k}`);
    console.log(`    RSR: ${runResult.summary.recovery_success_rate}`);
    console.log(`    Tokens Médios por Sucesso: ${runResult.summary.avg_tokens_per_pass}`);
  }

  console.log('\n📊 ======================================================');
  console.log('📊 RESUMO COMPARATIVO DO TESTE PILOTO GEMMA4 (5 TAREFAS)');
  console.log('📊 ======================================================');
  console.table(
    Object.entries(pilotSummary).map(([sysId, s]) => ({
      'Sistema': sysId,
      'pass@1': s.pass_at_1,
      'pass@k': s.pass_at_k,
      'P1': s.initial_pass_p1,
      'PR': s.recovered_pass_pr,
      'FF': s.final_fail_ff,
      'RSR': s.recovery_success_rate ?? 'N/A',
      'Avg Tokens': s.avg_tokens_per_pass
    }))
  );

  console.log(`\n💾 Todos os artefatos do piloto Gemma4 foram gravados em: ${RUNS_DIR}`);
}

main().catch(err => {
  console.error('❌ ERRO NO PILOTO GEMMA4:', err);
  process.exit(1);
});
