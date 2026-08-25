import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { Scale50kAgent } from '../agent/scale_50k_agent.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const JS_DIR = path.join(ROOT, 'repo_js');
const TASKS_FILE = path.join(ROOT, 'dataset/blind_50k_tasks.json');
const MANIFEST_FILE = path.join(ROOT, 'dataset/50k_manifest.json');

export async function run50kScaleBenchmark() {
  console.log("================================================================================");
  console.log("   LIN-50K-SCALE: 50,000 LOC BENCHMARK (JS vs NATIVE LIN)                       ");
  console.log("================================================================================");

  const manifest = JSON.parse(fs.readFileSync(MANIFEST_FILE, 'utf8'));
  const tasks = JSON.parse(fs.readFileSync(TASKS_FILE, 'utf8'));

  console.log(`[+] Target Codebase Metrics:`);
  console.log(`    - Executable JS Codebase: ${manifest.total_js_lines.toLocaleString()} lines across ${manifest.num_modules} modules`);
  console.log(`    - Native LIN (.lin) Codebase: ${manifest.total_lin_lines.toLocaleString()} lines`);
  console.log(`    - Structural Compression Ratio: ${manifest.compression_ratio}x`);
  console.log(`    - Total Functions / DAG Nodes: ${manifest.total_functions.toLocaleString()}`);

  const arms = [
    { id: 'RAW', name: 'Arm A: Raw JS Multi-Module Baseline' },
    { id: 'CHAT_HISTORY', name: 'Arm B: Chat History Buffer' },
    { id: 'LIN_NATIVE', name: 'Arm C: LIN Native Substrate (.lin + HashCons)' }
  ];

  const agent = new Scale50kAgent();
  agent.substrate.index50kManifest(MANIFEST_FILE);

  const armSummaries = {};

  for (const arm of arms) {
    console.log(`\n================================================================================`);
    console.log(`>>> Executing ${arm.name} on 50k LOC Codebase...`);
    console.log(`================================================================================`);

    let totalTasks = tasks.length;
    let initialSuccessCount = 0;
    let recoveredSuccessCount = 0;
    let rootCauseFoundCount = 0;
    let totalAttempts = 0;
    let totalWrongFileEdits = 0;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;

    const taskLogs = [];

    for (const task of tasks) {
      // Inject bug into target module in 50k repo
      const targetFilePath = path.join(JS_DIR, task.ground_truth.file);
      let content = fs.readFileSync(targetFilePath, 'utf8');
      content = content.replace(task.ground_truth.bug_find, task.ground_truth.bug_replace);
      fs.writeFileSync(targetFilePath, content, 'utf8');

      const res = await agent.runTask({
        task,
        repoDir: JS_DIR,
        arm: arm.id,
        maxAttempts: 3
      });

      if (res.initialSuccess) initialSuccessCount++;
      if (res.recoveredSuccess) recoveredSuccessCount++;
      if (res.rootCauseFound) rootCauseFoundCount++;
      totalAttempts += res.attempts;
      totalWrongFileEdits += res.wrongFileEdits;
      totalPromptTokens += res.promptTokens;
      totalEvalTokens += res.evalTokens;
      totalDurationMs += res.durationMs;

      console.log(`  [${task.task_id}] ${task.title.slice(0, 38)}... -> Success: ${res.success} (Init: ${res.initialSuccess}, Rec: ${res.recoveredSuccess}) | Localized: ${res.rootCauseFound} | Tokens: ${res.promptTokens} | Time: ${(res.durationMs / 1000).toFixed(1)}s`);
      taskLogs.push(res);
    }

    const failedInitial = totalTasks - initialSuccessCount;
    const recoveryRate = failedInitial > 0 ? (recoveredSuccessCount / failedInitial) : 0;
    const taskSuccessRate = (initialSuccessCount + recoveredSuccessCount) / totalTasks;
    const localizationRate = rootCauseFoundCount / totalTasks;
    const avgAttempts = totalAttempts / totalTasks;
    const avgTokens = totalPromptTokens / totalTasks;

    const summary = {
      arm_id: arm.id,
      arm_name: arm.name,
      total_tasks: totalTasks,
      codebase_lines: manifest.total_js_lines,
      lin_lines: manifest.total_lin_lines,
      compression_ratio: manifest.compression_ratio,
      root_cause_localization_rate: localizationRate,
      initial_success: initialSuccessCount,
      recovered_success: recoveredSuccessCount,
      persistent_failures: totalTasks - (initialSuccessCount + recoveredSuccessCount),
      task_success_rate: taskSuccessRate,
      hypothesis_recovery_rate: recoveryRate,
      total_wrong_file_edits: totalWrongFileEdits,
      avg_attempts_per_task: avgAttempts,
      avg_prompt_tokens_per_task: avgTokens,
      total_duration_s: totalDurationMs / 1000,
      tasks: taskLogs
    };

    armSummaries[arm.id] = summary;
    console.log(`\n>>> [${arm.id} 50k Summary] Success: ${(taskSuccessRate * 100).toFixed(1)}% | Localized: ${(localizationRate * 100).toFixed(1)}% | Recovery: ${(recoveryRate * 100).toFixed(1)}% | Avg Tokens: ${avgTokens.toFixed(0)} | Total Time: ${(totalDurationMs / 1000).toFixed(1)}s`);
  }

  const outPath = path.join(ROOT, 'results/LIN_50K_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(armSummaries, null, 2));
  console.log(`\n[+] 50K LOC Scale Benchmark Complete! Final Report saved to: ${outPath}`);
  return armSummaries;
}

run50kScaleBenchmark();
