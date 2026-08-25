// Scale 50k Agent: Comparing RAW/CHAT Multi-File JS vs LIN Native Substrate

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { LIN50kSubstrate } from '../runtime/lin_50k_substrate.mjs';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

export class Scale50kAgent {
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
    this.substrate = new LIN50kSubstrate();
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

    // Failover to Ollama
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

  extractFileAndPatch(llmResponse, defaultFile) {
    let targetFile = defaultFile;
    const match = llmResponse.match(/```(?:javascript|js|lin)?\s*([\s\S]*?)```/i);
    let code = match ? match[1].trim() : null;
    if (code) {
      code = code.replace(/^FILE:[^\n]*\n+/i, '').trim();
    }
    return { targetFile, code };
  }

  runTests(repoDir) {
    try {
      const out = execSync(`node ${path.join(repoDir, 'tests/test_runner.js')}`, { encoding: 'utf8', timeout: 5000 });
      return { passed: out.includes('Overall: PASS'), output: out };
    } catch (err) {
      return { passed: false, output: err.stdout || err.message };
    }
  }

  findTargetFromError(testErrorOutput) {
    for (const [sym, node] of this.substrate.symbolIndex.entries()) {
      if (testErrorOutput.includes(sym)) {
        return { symbol: sym, module: node.module };
      }
    }
    return { symbol: 'm000_math_algebra_fn_0', module: 'src/mod_000_math_algebra.js' };
  }

  async runTask({ task, repoDir, arm = 'LIN_NATIVE', maxAttempts = 3 }) {
    let historyBuffer = [];
    let initialSuccess = false;
    let recoveredSuccess = false;
    let rootCauseFound = false;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;
    let attemptsCount = 0;
    let wrongFileEdits = 0;

    const target = this.findTargetFromError(task.test_assertion_error);
    const targetFile = target.module;
    const fullTargetFilePath = path.join(repoDir, targetFile);
    const originalContent = fs.existsSync(fullTargetFilePath) ? fs.readFileSync(fullTargetFilePath, 'utf8') : '';

    const resetFile = () => {
      if (originalContent) fs.writeFileSync(fullTargetFilePath, originalContent, 'utf8');
    };

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      attemptsCount++;
      let prompt = '';

      if (arm === 'RAW') {
        const fileContent = fs.readFileSync(fullTargetFilePath, 'utf8');
        prompt = `You are debugging an enterprise codebase with 50,000 lines of code across 130 modules.\n\n[Issue Report]\n${task.issue_description}\n\n[Failing Test Trace]\n${task.test_assertion_error}\n\n[Module Code: ${targetFile}]\n\`\`\`javascript\n${fileContent}\n\`\`\`\n\nProvide the complete fixed code for ${targetFile} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'CHAT_HISTORY') {
        const fileContent = fs.readFileSync(fullTargetFilePath, 'utf8');
        const histText = historyBuffer.map(h => `[Attempt ${h.attempt} Failed]:\n${h.testOutput}`).join('\n\n');
        prompt = `You are debugging an enterprise codebase with 50,000 lines of code across 130 modules.\n\n[Issue Report]\n${task.issue_description}\n\n[Failing Test Trace]\n${task.test_assertion_error}\n\n`;
        if (histText) prompt += `[Previous Attempt History]\n${histText}\n\n`;
        prompt += `[Module Code: ${targetFile}]\n\`\`\`javascript\n${fileContent}\n\`\`\`\n\nProvide the complete fixed code for ${targetFile} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'LIN_NATIVE') {
        // Native LIN Representation & Semantic Substrate Memory Slice
        const focused = this.substrate.generateFocusedContext(target.symbol);
        const linFileName = targetFile.replace('src/', '').replace('.js', '.lin');
        const linFilePath = path.join(ROOT, 'repo_lin', 'src', linFileName);
        const linContent = fs.existsSync(linFilePath) ? fs.readFileSync(linFilePath, 'utf8') : '';

        prompt = `[LIN 50K Semantic Substrate Slice]\n`;
        prompt += `* Target Canonical Symbol: ${target.symbol}\n`;
        prompt += `* Declared Effect: *(${focused ? focused.effect : 'Pure'})\n`;
        prompt += `* Invariants: [${focused ? focused.invariants.join(', ') : 'ret !== undefined'}]\n`;
        prompt += `* Transitive Dependents in 50k Graph: [${focused ? focused.dependents.slice(0, 3).join(', ') : 'None'}]\n\n`;
        prompt += `[Native LIN Representation (.lin)]\n\`\`\`lin\n${linContent.slice(0, 500)}\n\`\`\`\n\n`;
        prompt += `[Issue Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Trace]\n${task.test_assertion_error}\n\n`;
        prompt += `[Target Module JS: ${targetFile}]\n\`\`\`javascript\n${fs.readFileSync(fullTargetFilePath, 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed JavaScript code for ${targetFile} inside a single \`\`\`javascript code block.`;
      }

      const llm = await this.queryLLM(prompt);
      totalPromptTokens += llm.promptTokens;
      totalEvalTokens += llm.evalTokens;
      totalDurationMs += llm.durationMs;

      const { code } = this.extractFileAndPatch(llm.response, targetFile);

      if (!code) continue;

      if (targetFile === task.ground_truth.file) {
        rootCauseFound = true;
      } else {
        wrongFileEdits++;
      }

      fs.writeFileSync(fullTargetFilePath, code, 'utf8');
      const testRes = this.runTests(repoDir);

      if (testRes.passed) {
        if (attempt === 1) initialSuccess = true;
        else recoveredSuccess = true;
        break;
      } else {
        resetFile();
        historyBuffer.push({ attempt, file: targetFile, testOutput: testRes.output.slice(0, 150) });
      }
    }

    resetFile();

    return {
      task_id: task.task_id,
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
