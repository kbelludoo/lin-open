// LIN Autonomous Agent with High-Speed 9router LLM Engine & Full Closed Loop

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { SemanticSubstrate } from '../runtime/semantic_substrate.mjs';
import { TraumaLedger } from '../runtime/trauma_ledger.mjs';
import { VerifierGate } from '../runtime/verifier_gate.mjs';

export class LinAgent {
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
    this.substrate = new SemanticSubstrate();
    this.trauma = new TraumaLedger();
    this.verifier = new VerifierGate(this.substrate);
  }

  async parseSSE(response) {
    const raw = await response.text();
    let text = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("data: ")) {
        const chunk = line.slice(6).trim();
        if (chunk === "[DONE]") continue;
        try {
          const p = JSON.parse(chunk);
          if (p.choices && p.choices[0]) {
            if (p.choices[0].delta && p.choices[0].delta.content) {
              text += p.choices[0].delta.content;
            } else if (p.choices[0].text) {
              text += p.choices[0].text;
            }
          }
        } catch(e) {}
      }
    }
    if (!text) {
      try {
        const p = JSON.parse(raw);
        if (p.choices && p.choices[0]) {
          text = p.choices[0].message ? p.choices[0].message.content : p.choices[0].text;
        }
      } catch(e) {}
    }
    return text.trim();
  }

  async queryLLM(prompt) {
    const t0 = performance.now();

    // 1. Try 9router Primary Model
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
            max_tokens: 600
          }),
          signal: AbortSignal.timeout(8000)
        });
        if (res.ok) {
          const text = await this.parseSSE(res);
          if (text) {
            const durationMs = performance.now() - t0;
            const promptTokens = Math.ceil(prompt.length / 4);
            const evalTokens = Math.ceil(text.length / 4);
            return { response: text, promptTokens, evalTokens, durationMs, modelUsed: model };
          }
        }
      } catch(e) {}
    }

    // 2. Failover to Local Ollama
    const res = await fetch(`${this.ollamaUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.ollamaModel,
        prompt,
        temperature: 0.1,
        stream: false,
        options: { num_predict: 250, num_thread: 8 }
      })
    });
    if (!res.ok) throw new Error(`LLM Error: ${res.statusText}`);
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

  extractCode(llmResponse, originalCode) {
    const match = llmResponse.match(/```(?:javascript|js)?\s*([\s\S]*?)```/i);
    if (match) return match[1].trim();
    if (llmResponse.includes('export function') || llmResponse.includes('function ') || llmResponse.includes('const regex =')) {
      return llmResponse.trim();
    }
    return originalCode;
  }

  runTests(repoDir) {
    try {
      const out = execSync(`node ${path.join(repoDir, 'tests/test_runner.js')}`, { encoding: 'utf8', timeout: 5000 });
      return { passed: out.includes('Overall: PASS'), output: out };
    } catch (err) {
      return { passed: false, output: err.stdout || err.message };
    }
  }

  async runTask({ task, repoDir, group = 'LIN', maxAttempts = 3 }) {
    this.trauma.clear();
    let historyBuffer = [];
    let initialSuccess = false;
    let recoveredSuccess = false;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;
    let verificationRejections = 0;
    let attemptsCount = 0;

    const targetFilePath = path.join(repoDir, task.file);
    const backupCode = fs.readFileSync(targetFilePath, 'utf8');

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      attemptsCount++;
      const currentCode = fs.readFileSync(targetFilePath, 'utf8');

      // 1. Build Prompt conditioned on Group Architecture
      let prompt = '';
      if (group === 'RAW') {
        prompt = `You are an expert JS developer fixing a bug.\nTask: ${task.instruction}\n\nFile (${task.file}):\n\`\`\`javascript\n${currentCode}\n\`\`\`\n\nProvide the complete, corrected code for ${task.file} inside a single \`\`\`javascript code block.`;
      } else if (group === 'CHAT_HISTORY') {
        const histText = historyBuffer.map(h => `[Attempt ${h.attempt} Test Failure Error]:\n${h.testOutput}`).join('\n\n');
        prompt = `You are an expert JS developer fixing a bug.\nTask: ${task.instruction}\n\nFile (${task.file}):\n\`\`\`javascript\n${currentCode}\n\`\`\`\n${histText ? `\nPrevious Attempt Failures:\n${histText}\n` : ''}\nProvide the complete, corrected code for ${task.file} inside a single \`\`\`javascript code block.`;
      } else if (group === 'LIN') {
        const focused = this.substrate.generateFocusedContext(task.symbol);
        const traumaText = this.trauma.generateTraumaPrompt();
        prompt = `[LIN Semantic State]\nTarget Symbol: ${focused.symbol} in '${task.file}'\nDeclared Effect: *(${focused.effect})\nDownstream Transitive Dependents: [${focused.dependents.join(', ')}]\n${traumaText ? `${traumaText}\n` : ''}\nTask: ${task.instruction}\n\nCurrent Code:\n\`\`\`javascript\n${currentCode}\n\`\`\`\n\nProvide the complete, corrected code for ${task.file} inside a single \`\`\`javascript code block.`;
      }

      // 2. Query LLM
      const llm = await this.queryLLM(prompt);
      totalPromptTokens += llm.promptTokens;
      totalEvalTokens += llm.evalTokens;
      totalDurationMs += llm.durationMs;

      // 3. Extract & verify patch
      const newCode = this.extractCode(llm.response, currentCode);

      if (group === 'LIN') {
        const effCheck = this.verifier.verifyEffectIsolation(newCode, 'Pure');
        if (!effCheck.valid) {
          verificationRejections++;
          this.trauma.recordFailure({
            attempt,
            targetSymbol: task.symbol,
            brokenInvariant: 'EFFECT_LEAK',
            errorDiagnostic: effCheck.reason,
            refutedHypothesis: 'Attempted to perform IO in a pure semantic module'
          });
          continue;
        }
      }

      // 4. Apply patch to disk
      fs.writeFileSync(targetFilePath, newCode, 'utf8');

      // 5. Execute tests
      const testRes = this.runTests(repoDir);

      if (testRes.passed) {
        if (attempt === 1) initialSuccess = true;
        else recoveredSuccess = true;
        break;
      } else {
        // Rollback and record trauma
        fs.writeFileSync(targetFilePath, backupCode, 'utf8');
        historyBuffer.push({ attempt, testOutput: testRes.output.slice(0, 250) });
        this.trauma.recordFailure({
          attempt,
          targetSymbol: task.symbol,
          brokenInvariant: 'TEST_ASSERTION_FAILED',
          errorDiagnostic: testRes.output.slice(0, 150),
          refutedHypothesis: `Patch in attempt ${attempt} failed test assertions`
        });
      }
    }

    // Ensure clean state
    fs.writeFileSync(targetFilePath, backupCode, 'utf8');

    return {
      task_id: task.task_id,
      group,
      success: initialSuccess || recoveredSuccess,
      initialSuccess,
      recoveredSuccess,
      attempts: attemptsCount,
      promptTokens: totalPromptTokens,
      evalTokens: totalEvalTokens,
      durationMs: totalDurationMs,
      verificationRejections
    };
  }
}
