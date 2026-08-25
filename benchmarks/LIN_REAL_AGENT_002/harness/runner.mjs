import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const TEMPLATE_DIR = path.join(ROOT, 'repo_template');
const WORK_DIR = path.join(ROOT, 'repo');

async function callOllama(prompt) {
  const t0 = performance.now();
  const res = await fetch("http://localhost:11434/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "qwen2.5-coder:7b",
      prompt,
      temperature: 0.2,
      stream: false
    })
  });
  if (!res.ok) {
    throw new Error(`Ollama call failed: ${res.statusText}`);
  }
  const data = await res.json();
  const durationMs = performance.now() - t0;
  return {
    response: data.response || "",
    promptTokens: data.prompt_eval_count || Math.ceil(prompt.length / 4),
    evalTokens: data.eval_count || 0,
    durationMs
  };
}

function resetRepo() {
  fs.rmSync(WORK_DIR, { recursive: true, force: true });
  fs.cpSync(TEMPLATE_DIR, WORK_DIR, { recursive: true });
}

function runRepoTests() {
  try {
    const out = execSync(`node ${path.join(WORK_DIR, 'tests/test_runner.js')}`, { encoding: 'utf8', timeout: 5000 });
    const passed = out.includes("Overall: PASS");
    return { passed, output: out };
  } catch (err) {
    return { passed: false, output: err.stdout || err.message };
  }
}

function extractCode(llmResponse, originalCode) {
  // Extract markdown code block if present
  const m = llmResponse.match(/```(?:javascript|js)?\s*([\s\S]*?)```/i);
  if (m) {
    return m[1].trim();
  }
  // Fallback: if response looks like JS code, use directly
  if (llmResponse.includes("export function") || llmResponse.includes("function ")) {
    return llmResponse.trim();
  }
  return originalCode;
}

export async function runRealAgentSuite() {
  console.log("================================================================================");
  console.log("   LIN-REAL-AGENT-002: REAL LLM (QWEN2.5-CODER:7B) ON REAL CODE REPO            ");
  console.log("================================================================================");

  const tasks = JSON.parse(fs.readFileSync(path.join(ROOT, 'tasks/tasks.json'), 'utf8'));
  const groups = [
    { id: "A", name: "Group A (Raw LLM / Zero-State)" },
    { id: "B", name: "Group B (LLM + Chat History)" },
    { id: "C", name: "Group C (LLM + LIN Semantic Memory)" },
    { id: "D", name: "Group D (LLM + LIN Memory + Verifier)" }
  ];

  const results = {};

  for (const grp of groups) {
    console.log(`\n>>> EXECUTING GROUP ${grp.id}: ${grp.name}...`);
    let initialSuccess = 0;
    let recoveredSuccess = 0;
    let persistentFailure = 0;
    let totalAttempts = 0;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;

    const taskSummaries = [];

    for (const task of tasks) {
      console.log(`  [Task ${task.task_id}] ${task.title}...`);
      resetRepo();

      // Inject bug
      const targetFilePath = path.join(WORK_DIR, task.file);
      let fileContent = fs.readFileSync(targetFilePath, 'utf8');
      fileContent = fileContent.replace(task.bug_find, task.bug_replace);
      fs.writeFileSync(targetFilePath, fileContent, 'utf8');

      // Verify tests fail
      const initialTest = runRepoTests();
      if (initialTest.passed) {
        console.warn(`    WARNING: Bug injection did not fail tests on ${task.task_id}`);
      }

      let resolved = false;
      let historyBuffer = [];
      let traumaMemory = [];

      for (let attempt = 1; attempt <= 3; attempt++) {
        totalAttempts++;
        const currentCode = fs.readFileSync(targetFilePath, 'utf8');

        // Build prompt based on Group architecture
        let prompt = "";
        if (grp.id === "A") {
          prompt = `You are a software engineer repairing a bug in JavaScript.\n\nTask: ${task.instruction}\n\nFile (${task.file}):\n\`\`\`javascript\n${currentCode}\n\`\`\`\n\nProvide the complete, corrected code for ${task.file} inside a \`\`\`javascript code block.`;
        } else if (grp.id === "B") {
          let histText = historyBuffer.map(h => `Attempt ${h.attempt} Output:\n${h.testOutput}`).join("\n\n");
          prompt = `You are a software engineer repairing a bug in JavaScript.\n\nTask: ${task.instruction}\n\nFile (${task.file}):\n\`\`\`javascript\n${currentCode}\n\`\`\`\n${histText ? `\nPrevious Attempt Test Failures:\n${histText}\n` : ""}\nProvide the complete, corrected code for ${task.file} inside a \`\`\`javascript code block.`;
        } else if (grp.id === "C" || grp.id === "D") {
          let traumaText = traumaMemory.map(t => `[Trauma Memory] Attempt ${t.attempt} violated: ${t.violation}`).join("\n");
          prompt = `[LIN Semantic State Context]\nTarget Module: ${task.file}\nSymbol Focus: ${task.symbol}\nDependency Graph: [parser -> comparator -> ranges -> satisfier -> invariants]\n${traumaText ? `${traumaText}\n` : ""}\nTask: ${task.instruction}\n\nCurrent Code:\n\`\`\`javascript\n${currentCode}\n\`\`\`\n\nProvide the complete, corrected code for ${task.file} inside a \`\`\`javascript code block.`;
        }

        // Call real LLM
        const llm = await callOllama(prompt);
        totalPromptTokens += llm.promptTokens;
        totalEvalTokens += llm.evalTokens;
        totalDurationMs += llm.durationMs;

        // Apply generated patch to disk
        const newCode = extractCode(llm.response, currentCode);
        fs.writeFileSync(targetFilePath, newCode, 'utf8');

        // If Group D, run static invariant pre-check
        if (grp.id === "D") {
          try {
            const invCheck = execSync(`node -e "import('./src/invariants.js').then(m => { const r = m.checkSemverInvariants(); if (!r.valid) process.exit(1); })"`, { cwd: WORK_DIR, timeout: 2000 });
          } catch (e) {
            // Verifier detected broken invariant before full suite run
            traumaMemory.push({ attempt, violation: "SemVer Invariant violation detected by static verifier" });
          }
        }

        // Run full test suite on disk
        const testRes = runRepoTests();
        if (testRes.passed) {
          resolved = true;
          if (attempt === 1) {
            initialSuccess++;
            console.log(`    -> PASSED on Attempt 1 (${(llm.durationMs/1000).toFixed(1)}s)`);
          } else {
            recoveredSuccess++;
            console.log(`    -> RECOVERED on Attempt ${attempt} (${(llm.durationMs/1000).toFixed(1)}s)`);
          }
          break;
        } else {
          console.log(`    -> Attempt ${attempt} Failed. Test failures: ${testRes.output.slice(0, 120).trim()}...`);
          historyBuffer.push({ attempt, testOutput: testRes.output.slice(0, 300) });
          traumaMemory.push({ attempt, violation: `Test suite failed on: ${testRes.output.slice(0, 150)}` });
        }
      }

      if (!resolved) {
        persistentFailure++;
        console.log(`    -> FAILED all 3 attempts.`);
      }

      taskSummaries.push({ task_id: task.task_id, type: task.type, resolved });
    }

    const failedInitial = tasks.length - initialSuccess;
    const recoveryRate = failedInitial > 0 ? (recoveredSuccess / failedInitial) : 0;
    const taskSuccessRate = (initialSuccess + recoveredSuccess) / tasks.length;

    const summary = {
      group_id: grp.id,
      group_name: grp.name,
      model: "qwen2.5-coder:7b",
      total_tasks: tasks.length,
      initial_success: initialSuccess,
      recovered_success: recoveredSuccess,
      persistent_failure: persistentFailure,
      task_success_rate: taskSuccessRate,
      recovery_rate: recoveryRate,
      avg_attempts: totalAttempts / tasks.length,
      total_prompt_tokens: totalPromptTokens,
      total_eval_tokens: totalEvalTokens,
      avg_prompt_tokens_per_task: totalPromptTokens / tasks.length,
      total_duration_s: totalDurationMs / 1000,
      tasks: taskSummaries
    };

    results[grp.id] = summary;
    console.log(`\n[Group ${grp.id} Result] Success: ${(taskSuccessRate*100).toFixed(1)}% | Recovery: ${(recoveryRate*100).toFixed(1)}% | Avg Tokens: ${(totalPromptTokens/tasks.length).toFixed(0)}`);
  }

  const outPath = path.join(ROOT, 'results/LIN_REAL_AGENT_002_REPORT.json');
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
  console.log(`\n[+] LIN-REAL-AGENT-002 Complete! Saved to ${outPath}`);
  return results;
}

runRealAgentSuite();
