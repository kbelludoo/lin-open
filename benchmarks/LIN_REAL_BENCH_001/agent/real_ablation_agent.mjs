// LIN Real-World 7-Stage Component Ablation Agent

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { RealBlindSubstrate } from '../runtime/real_blind_substrate.mjs';

export class RealAblationAgent {
  constructor({
    routerUrl = 'http://localhost:20128/v1',
    apiKey = 'sk-4f1d4e3f72aabeb4-eayna4-68bb3e83',
    primaryModel = 'ag/gemini-3.7-flash-low',
    secondaryModel = 'ag/gemini-3.5-flash-low',
    ollamaUrl = 'http://localhost:11434',
    ollamaModel = 'qwen2.5-coder:7b'
  } = {}) {
    this.routerUrl = routerUrl;
    this.apiKey = apiKey;
    this.primaryModel = primaryModel;
    this.secondaryModel = secondaryModel;
    this.ollamaUrl = ollamaUrl;
    this.ollamaModel = ollamaModel;
    this.substrate = new RealBlindSubstrate();
  }

  async queryLLM(prompt) {
    const t0 = performance.now();

    for (const model of [this.primaryModel, this.secondaryModel]) {
      try {
        const res = await fetch(`${this.routerUrl}/chat/completions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${this.apiKey}`
          },
          body: JSON.stringify({
            model,
            messages: [{ role: 'user', content: prompt }],
            temperature: 0.1,
            max_tokens: 800,
            stream: false
          }),
          signal: AbortSignal.timeout(6000)
        });

        if (res.ok) {
          const data = await res.json();
          if (data.choices && data.choices[0] && data.choices[0].message) {
            const text = data.choices[0].message.content.trim();
            const durationMs = performance.now() - t0;
            const promptTokens = Math.ceil(prompt.length / 4);
            const evalTokens = Math.ceil(text.length / 4);
            return { response: text, promptTokens, evalTokens, durationMs, modelUsed: model };
          }
        }
      } catch(e) {}
    }

    try {
      const res = await fetch(`${this.ollamaUrl}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.ollamaModel,
          prompt,
          temperature: 0.1,
          stream: false,
          options: { num_predict: 350, num_thread: 8 }
        }),
        signal: AbortSignal.timeout(10000)
      });
      if (res.ok) {
        const data = await res.json();
        const durationMs = performance.now() - t0;
        return {
          response: data.response || '',
          promptTokens: data.prompt_eval_count || Math.ceil(prompt.length / 4),
          evalTokens: data.eval_count || 0,
          durationMs,
          modelUsed: this.ollamaModel
        };
      }
    } catch(e) {}

    throw new Error("All LLM providers unavailable");
  }

  extractFileAndPatch(llmResponse, defaultFile, availableFiles = []) {
    let targetFile = defaultFile;
    for (const f of availableFiles) {
      if (llmResponse.includes(f) || llmResponse.includes(`FILE: ${f}`)) {
        targetFile = f;
        break;
      }
    }
    const match = llmResponse.match(/```(?:javascript|js|lin)?\s*([\s\S]*?)```/i);
    let code = match ? match[1].trim() : null;
    if (code) {
      code = code.replace(/^FILE:[^\n]*\n+/i, '').trim();
    }
    return { targetFile, code };
  }

  runTests(repoDir) {
    try {
      const runnerPath = fs.existsSync(path.join(repoDir, 'test/test_runner.js')) 
        ? path.join(repoDir, 'test/test_runner.js')
        : path.join(repoDir, 'tests/test_runner.js');
      const out = execSync(`node ${runnerPath}`, { encoding: 'utf8', timeout: 5000 });
      return { passed: out.includes('Overall: PASS'), output: out };
    } catch (err) {
      return { passed: false, output: err.stdout || err.message };
    }
  }

  findMatchingSymbolFromError(testErrorOutput) {
    for (const [sym, node] of this.substrate.symbolIndex.entries()) {
      if (testErrorOutput.includes(sym)) return { symbol: sym, file: node.file };
    }
    // Return first symbol in substrate if not directly matching
    const firstKey = this.substrate.symbolIndex.keys().next().value;
    if (firstKey) {
      const node = this.substrate.symbolIndex.get(firstKey);
      return { symbol: firstKey, file: node.file };
    }
    return { symbol: 'unknown', file: 'lib/index.js' };
  }

  async runAblationTask({ task, repoDir, arm = 'ARM_G_FULL_LIN', maxAttempts = 3 }) {
    // 1. Blindly index repository from disk
    this.substrate.indexRepository(repoDir);

    let historyBuffer = [];
    let refutedSet = new Set();
    let initialSuccess = false;
    let recoveredSuccess = false;
    let rootCauseFound = false;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;
    let attemptsCount = 0;
    let wrongFileEdits = 0;

    const sourceFiles = [];
    function scanFiles(dir) {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (e.name === 'node_modules' || e.name === 'test' || e.name === 'tests') continue;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) scanFiles(full);
        else if (e.name.endsWith('.js')) sourceFiles.push(path.relative(repoDir, full));
      }
    }
    scanFiles(repoDir);

    const originalContents = {};
    for (const f of sourceFiles) {
      originalContents[f] = fs.readFileSync(path.join(repoDir, f), 'utf8');
    }

    const resetFiles = () => {
      for (const f of sourceFiles) {
        fs.writeFileSync(path.join(repoDir, f), originalContents[f], 'utf8');
      }
    };

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      attemptsCount++;
      let prompt = '';
      const matched = this.findMatchingSymbolFromError(task.test_assertion_error);
      const defaultTargetFile = matched.file || sourceFiles[0];

      if (arm === 'ARM_A_RAW') {
        // Arm A: Pure LLM prompt with file code
        prompt = `You are an expert open-source maintainer fixing a real historical bug in \`${task.repo}\`.\n\n`;
        prompt += `[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        prompt += `[Repository Files]\n`;
        for (const f of sourceFiles) {
          prompt += `--- ${f} ---\n${fs.readFileSync(path.join(repoDir, f), 'utf8')}\n\n`;
        }
        prompt += `Provide the complete fixed code for the target file inside a single \`\`\`javascript code block with header 'FILE: <filepath>'.`;

      } else if (arm === 'ARM_B_CHAT') {
        const histText = historyBuffer.map(h => `[Attempt ${h.attempt} Failed on ${h.file}]:\n${h.testOutput}`).join('\n\n');
        prompt = `You are an expert open-source maintainer fixing a real historical bug in \`${task.repo}\`.\n\n`;
        prompt += `[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        if (histText) prompt += `[Previous Attempt History]\n${histText}\n\n`;
        prompt += `[Repository Files]\n`;
        for (const f of sourceFiles) {
          prompt += `--- ${f} ---\n${fs.readFileSync(path.join(repoDir, f), 'utf8')}\n\n`;
        }
        prompt += `Provide the complete fixed code for the target file inside a single \`\`\`javascript code block with header 'FILE: <filepath>'.`;

      } else if (arm === 'ARM_C_HASHCONS') {
        // Arm C: HashCons Canonical Identity Indexing
        prompt = `[LIN HashCons Index]\nTarget File: ${defaultTargetFile}\nCanonical Node: ${matched.symbol}\n\n`;
        prompt += `[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        prompt += `[Source Code: ${defaultTargetFile}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, defaultTargetFile), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${defaultTargetFile} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'ARM_D_DAG') {
        // Arm D: HashCons + Transitive Dependency DAG
        const focused = this.substrate.generateFocusedContext(matched.symbol);
        prompt = `[LIN Dependency DAG]\n`;
        prompt += `* Target Symbol: ${matched.symbol} in '${defaultTargetFile}'\n`;
        prompt += `* Callee Dependencies: [${focused ? focused.dependencies.join(', ') : 'None'}]\n`;
        prompt += `* Upstream Callers: [${focused ? focused.dependents.join(', ') : 'None'}]\n\n`;
        prompt += `[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        prompt += `[Source Code: ${defaultTargetFile}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, defaultTargetFile), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${defaultTargetFile} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'ARM_E_CONTRACTS_EFFECTS') {
        // Arm E: DAG + Invariants (%) + Effect Safety (*)
        const focused = this.substrate.generateFocusedContext(matched.symbol);
        prompt = `[LIN Contracts % & Effects *]\n`;
        prompt += `* Target Symbol: ${matched.symbol} in '${defaultTargetFile}'\n`;
        prompt += `* Declared Effect: *(${focused ? focused.effect : 'Pure'})\n`;
        prompt += `* Active Invariants: [${focused ? focused.invariants.join('; ') : 'ret !== undefined'}]\n\n`;
        prompt += `[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        prompt += `[Source Code: ${defaultTargetFile}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, defaultTargetFile), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${defaultTargetFile} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'ARM_F_TRAUMA') {
        // Arm F: Contracts + Effects + Trauma Memory
        const focused = this.substrate.generateFocusedContext(matched.symbol);
        const traumaText = Array.from(refutedSet).map(s => `* Refuted Hypothesis: '${s}' failed test`).join('\n');
        prompt = `[LIN Trauma Ledger (Attempt ${attempt})]\n`;
        prompt += `* Target Symbol: ${matched.symbol} in '${defaultTargetFile}'\n`;
        prompt += `* Effect: *(${focused ? focused.effect : 'Pure'})\n`;
        if (traumaText) prompt += `\n[Trauma Memory]\n${traumaText}\n`;
        prompt += `\n[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        prompt += `[Source Code: ${defaultTargetFile}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, defaultTargetFile), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${defaultTargetFile} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'ARM_G_FULL_LIN') {
        // Arm G: Full LIN Frontier (DAG + Contracts + Effects + Trauma + Causal Navigation)
        const focused = this.substrate.generateFocusedContext(matched.symbol);
        prompt = `[Full LIN Causal Frontier Navigation (Attempt ${attempt})]\n`;
        prompt += `* Canonical Symbol: ${matched.symbol} in '${defaultTargetFile}'\n`;
        prompt += `* Declared Effect: *(${focused ? focused.effect : 'Pure'})\n`;
        prompt += `* Invariant Contracts: [${focused ? focused.invariants.join('; ') : 'ret !== undefined'}]\n`;
        prompt += `* Transitive Dependents: [${focused ? focused.dependents.join(', ') : 'None'}]\n`;
        if (refutedSet.size > 0) {
          prompt += `* Causal Frontier Note: Upstream wrapper '${Array.from(refutedSet).join(', ')}' was refuted. Focusing on leaf symbol logic.\n`;
        }
        prompt += `\n[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Assertion]\n${task.test_assertion_error}\n\n`;
        prompt += `[Source Code: ${defaultTargetFile}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, defaultTargetFile), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${defaultTargetFile} inside a single \`\`\`javascript code block.`;
      }

      const llm = await this.queryLLM(prompt);
      totalPromptTokens += llm.promptTokens;
      totalEvalTokens += llm.evalTokens;
      totalDurationMs += llm.durationMs;

      const { targetFile, code } = this.extractFileAndPatch(llm.response, defaultTargetFile, sourceFiles);

      if (!code) continue;

      if (targetFile === task.ground_truth.file) {
        rootCauseFound = true;
      } else {
        wrongFileEdits++;
      }

      fs.writeFileSync(path.join(repoDir, targetFile), code, 'utf8');
      const testRes = this.runTests(repoDir);

      if (testRes.passed) {
        if (attempt === 1) initialSuccess = true;
        else recoveredSuccess = true;
        break;
      } else {
        resetFiles();
        historyBuffer.push({ attempt, file: targetFile, testOutput: testRes.output.slice(0, 150) });
        refutedSet.add(matched.symbol);
      }
    }

    resetFiles();

    return {
      task_id: task.task_id,
      repo: task.repo,
      arm,
      success: initialSuccess || recoveredSuccess,
      initialSuccess,
      recoveredSuccess,
      rootCauseFound,
      attempts: attemptsCount,
      wrongFileEdits,
      promptTokens: totalPromptTokens,
      evalTokens: totalEvalTokens,
      durationMs: totalDurationMs
    };
  }
}
