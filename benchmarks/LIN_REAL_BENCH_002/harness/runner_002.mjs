import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { RealAgent002 } from '../agent/real_agent_002.mjs';
import { StatisticalEngine } from '../runtime/statistical_engine.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const TASKS_FILE = path.join(ROOT, 'dataset/frozen_historical_corpus.json');

export async function runRealBench002() {
  console.log("================================================================================");
  console.log("   LIN-REAL-BENCH-002: LARGE-SCALE REAL REPOSITORIES & STATISTICAL SIGNIFICANCE ");
  console.log("================================================================================");

  const tasks = JSON.parse(fs.readFileSync(TASKS_FILE, 'utf8'));
  console.log(`[+] Loaded Pre-Frozen Historical Corpus: ${tasks.length} Tasks across 4 Open-Source Repositories.`);

  const arms = [
    { id: 'RAW', name: 'Arm A: Raw LLM Multi-File Baseline' },
    { id: 'CHAT_HISTORY', name: 'Arm B: Chat History Buffer' },
    { id: 'FULL_LIN', name: 'Arm C: Full LIN Canonical Substrate' }
  ];

  const agent = new RealAgent002();
  const armSummaries = {};
  const localizationOutcomes = {};
  const successOutcomes = {};

  for (const arm of arms) {
    console.log(`\n================================================================================`);
    console.log(`>>> Executing ${arm.name}...`);
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
    const locFlags = [];
    const succFlags = [];

    for (const task of tasks) {
      const repoDir = path.join(ROOT, task.repo_dir);

      // Inject frozen bug
      const targetFilePath = path.join(repoDir, task.ground_truth.file);
      let content = fs.readFileSync(targetFilePath, 'utf8');
      content = content.replace(task.ground_truth.bug_find, task.ground_truth.bug_replace);
      fs.writeFileSync(targetFilePath, content, 'utf8');

      const res = await agent.runTask({
        task,
        repoDir,
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

      locFlags.push(res.rootCauseFound);
      succFlags.push(res.success);

      console.log(`  [${task.task_id}] (${task.repo}) ${task.title.slice(0, 36)}... -> Success: ${res.success} (Init: ${res.initialSuccess}, Rec: ${res.recoveredSuccess}) | Localized: ${res.rootCauseFound} | Tokens: ${res.promptTokens} | Time: ${(res.durationMs / 1000).toFixed(1)}s`);
      taskLogs.push(res);
    }

    localizationOutcomes[arm.id] = locFlags;
    successOutcomes[arm.id] = succFlags;

    const failedInitial = totalTasks - initialSuccessCount;
    const recoveryRate = failedInitial > 0 ? (recoveredSuccessCount / failedInitial) : 0;
    const taskSuccessRate = (initialSuccessCount + recoveredSuccessCount) / totalTasks;
    const localizationRate = rootCauseFoundCount / totalTasks;
    const avgAttempts = totalAttempts / totalTasks;
    const avgTokens = totalPromptTokens / totalTasks;

    const wilsonLocalization = StatisticalEngine.computeWilsonCI(rootCauseFoundCount, totalTasks);
    const wilsonSuccess = StatisticalEngine.computeWilsonCI(initialSuccessCount + recoveredSuccessCount, totalTasks);

    const summary = {
      arm_id: arm.id,
      arm_name: arm.name,
      total_tasks: totalTasks,
      root_cause_localization_rate: localizationRate,
      localization_ci_95: wilsonLocalization,
      initial_success: initialSuccessCount,
      recovered_success: recoveredSuccessCount,
      persistent_failures: totalTasks - (initialSuccessCount + recoveredSuccessCount),
      task_success_rate: taskSuccessRate,
      success_ci_95: wilsonSuccess,
      hypothesis_recovery_rate: recoveryRate,
      total_wrong_file_edits: totalWrongFileEdits,
      avg_attempts_per_task: avgAttempts,
      avg_prompt_tokens_per_task: avgTokens,
      total_duration_s: totalDurationMs / 1000,
      tasks: taskLogs
    };

    armSummaries[arm.id] = summary;
    console.log(`\n>>> [${arm.id} Summary] Success: ${wilsonSuccess.formatted} | Localized: ${wilsonLocalization.formatted} | Recovery: ${(recoveryRate * 100).toFixed(1)}% | Avg Tokens: ${avgTokens.toFixed(0)} | Total Time: ${(totalDurationMs / 1000).toFixed(1)}s`);
  }

  // Statistical Significance McNemar Tests
  const mcNemarLocalization = StatisticalEngine.computeMcNemarTest(localizationOutcomes['FULL_LIN'], localizationOutcomes['RAW']);
  const mcNemarSuccess = StatisticalEngine.computeMcNemarTest(successOutcomes['FULL_LIN'], successOutcomes['RAW']);

  const finalReport = {
    benchmark: "LIN-REAL-BENCH-002",
    total_frozen_tasks: tasks.length,
    statistical_tests: {
      mcnemar_localization_LIN_vs_RAW: mcNemarLocalization,
      mcnemar_success_LIN_vs_RAW: mcNemarSuccess
    },
    arms: armSummaries
  };

  const outPath = path.join(ROOT, 'results/LIN_REAL_BENCH_002_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(finalReport, null, 2));
  console.log(`\n================================================================================`);
  console.log(`>>> Statistical Significance (LIN vs RAW):`);
  console.log(`    - Localization McNemar p-value: ${mcNemarLocalization.p_value} (Significant: ${mcNemarLocalization.is_statistically_significant})`);
  console.log(`    - Success McNemar p-value: ${mcNemarSuccess.p_value} (Significant: ${mcNemarSuccess.is_statistically_significant})`);
  console.log(`[+] LIN-REAL-BENCH-002 Complete! Final Report saved to: ${outPath}`);
  console.log(`================================================================================`);
  return finalReport;
}

runRealBench002();
