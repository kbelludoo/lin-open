import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { AdaptiveAgent } from '../agent/adaptive_agent.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const TEMPLATE_DIR = path.resolve(ROOT, '../LIN_REAL_AGENT_002/repo_template');
const WORK_DIR = path.join(ROOT, 'repo_work');
const TASKS_FILE = path.resolve(ROOT, '../LIN_AGENT_RUNTIME_003/dataset/blind_tasks.json');

function setupWorkspace() {
  fs.rmSync(WORK_DIR, { recursive: true, force: true });
  fs.cpSync(TEMPLATE_DIR, WORK_DIR, { recursive: true });
}

function initializeSubstrate(agent) {
  const sub = agent.substrate;

  // 1. Register Symbols & Modules
  sub.registerSymbol({ name: 'parseVersion', module: 'src/parser.js', effect: 'Pure', body: 'regex.match' });
  sub.registerSymbol({ name: 'isValid', module: 'src/parser.js', effect: 'Pure', body: 'parseVersion(str) !== null' });

  sub.registerSymbol({ name: 'compareIdentifiers', module: 'src/comparator.js', effect: 'Pure', body: 'parseInt comparison' });
  sub.registerSymbol({ name: 'comparePrereleases', module: 'src/comparator.js', effect: 'Pure', body: 'compareIdentifiers loop' });
  sub.registerSymbol({ name: 'compareVersions', module: 'src/comparator.js', effect: 'Pure', body: 'comparePrereleases + major/minor/patch' });
  sub.registerSymbol({ name: 'gt', module: 'src/comparator.js', effect: 'Pure', body: 'compareVersions > 0' });
  sub.registerSymbol({ name: 'lt', module: 'src/comparator.js', effect: 'Pure', body: 'compareVersions < 0' });

  sub.registerSymbol({ name: 'parseRange', module: 'src/ranges.js', effect: 'Pure', body: 'caret and tilde parser' });
  sub.registerSymbol({ name: 'satisfiesRange', module: 'src/ranges.js', effect: 'Pure', body: 'evaluates comparators and prerelease isolation' });

  sub.registerSymbol({ name: 'maxSatisfying', module: 'src/satisfier.js', effect: 'Pure', body: 'loop with gt' });
  sub.registerSymbol({ name: 'minSatisfying', module: 'src/satisfier.js', effect: 'Pure', body: 'loop with lt' });

  // 2. Transitive Dependency Graph
  sub.addDependency('compareVersions', 'parseVersion');
  sub.addDependency('comparePrereleases', 'compareIdentifiers');
  sub.addDependency('compareVersions', 'comparePrereleases');
  sub.addDependency('gt', 'compareVersions');
  sub.addDependency('lt', 'compareVersions');

  sub.addDependency('parseRange', 'parseVersion');
  sub.addDependency('satisfiesRange', 'parseRange');
  sub.addDependency('satisfiesRange', 'compareVersions');

  sub.addDependency('maxSatisfying', 'satisfiesRange');
  sub.addDependency('maxSatisfying', 'gt');
  sub.addDependency('minSatisfying', 'satisfiesRange');
  sub.addDependency('minSatisfying', 'lt');
}

export async function runAdaptiveBenchmark() {
  console.log("================================================================================");
  console.log("   LIN-AGENT-RUNTIME-005: ADAPTIVE MULTI-FEATURE BEAM SEARCH (4 ARMS)           ");
  console.log("================================================================================");

  const tasks = JSON.parse(fs.readFileSync(TASKS_FILE, 'utf8'));

  const arms = [
    { id: 'GREEDY', name: 'Arm C1: LIN Greedy (Single-Node)' },
    { id: 'BEAM_3', name: 'Arm C2: LIN Fixed Beam-3' },
    { id: 'BEAM_5', name: 'Arm C3: LIN Fixed Beam-5' },
    { id: 'ADAPTIVE', name: 'Arm C4: LIN Adaptive Multi-Feature Beam' }
  ];

  const agent = new AdaptiveAgent();
  initializeSubstrate(agent);

  const armSummaries = {};

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

    for (const task of tasks) {
      setupWorkspace();

      // Inject bug according to ground truth
      const targetFilePath = path.join(WORK_DIR, task.ground_truth.file);
      let content = fs.readFileSync(targetFilePath, 'utf8');
      content = content.replace(task.ground_truth.bug_find, task.ground_truth.bug_replace);
      fs.writeFileSync(targetFilePath, content, 'utf8');

      // Execute task
      const res = await agent.runTask({
        task,
        repoDir: WORK_DIR,
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

      console.log(`  [${task.task_id}] ${task.title.slice(0, 32)}... -> Success: ${res.success} (Init: ${res.initialSuccess}, Rec: ${res.recoveredSuccess}) | Localized: ${res.rootCauseFound} | Wrong Edits: ${res.wrongFileEdits} | Tokens: ${res.promptTokens} | Time: ${(res.durationMs / 1000).toFixed(1)}s`);
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
    console.log(`\n>>> [${arm.id} Summary] Success: ${(taskSuccessRate * 100).toFixed(1)}% | Localized: ${(localizationRate * 100).toFixed(1)}% | Recovery: ${(recoveryRate * 100).toFixed(1)}% | Wrong Edits: ${totalWrongFileEdits} | Avg Tokens: ${avgTokens.toFixed(0)} | Total Time: ${(totalDurationMs / 1000).toFixed(1)}s`);
  }

  const outPath = path.join(ROOT, 'results/LIN_AGENT_RUNTIME_005_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(armSummaries, null, 2));
  console.log(`\n[+] RUNTIME-005 Benchmark Complete! Final Report saved to: ${outPath}`);
  return armSummaries;
}

runAdaptiveBenchmark();
