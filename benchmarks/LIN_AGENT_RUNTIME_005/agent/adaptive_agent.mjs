// LIN Adaptive Multi-Feature Agent

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { SemanticSubstrate } from '../../LIN_AGENT_RUNTIME_001/runtime/semantic_substrate.mjs';
import { VerifierGate } from '../../LIN_AGENT_RUNTIME_001/runtime/verifier_gate.mjs';
import { HypothesisLedger } from '../../LIN_AGENT_RUNTIME_004/runtime/hypothesis_ledger.mjs';
import { AdaptiveBeamSearch } from '../runtime/adaptive_beam_search.mjs';

export class AdaptiveAgent {
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
    this.ledger = new HypothesisLedger();
    this.verifier = new VerifierGate(this.substrate);
    this.search = new AdaptiveBeamSearch(this.substrate, this.ledger);
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

  async queryLLM(prompt, retryCount = 2) {
    const t0 = performance.now();

    for (let r = 0; r <= retryCount; r++) {
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
              max_tokens: 800
            }),
            signal: AbortSignal.timeout(12000)
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
      await new Promise(resolve => setTimeout(resolve, 800));
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
        })
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

  extractFileAndPatch(llmResponse, defaultFile, availableFiles) {
    let targetFile = defaultFile;
    for (const f of availableFiles) {
      if (llmResponse.includes(f) || llmResponse.includes(`FILE: ${f}`)) {
        targetFile = f;
        break;
      }
    }
    const match = llmResponse.match(/```(?:javascript|js)?\s*([\s\S]*?)```/i);
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

  async runTask({ task, repoDir, arm = 'ADAPTIVE', maxAttempts = 3 }) {
    this.ledger.clear();
    let initialSuccess = false;
    let recoveredSuccess = false;
    let rootCauseFound = false;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;
    let attemptsCount = 0;
    let wrongFileEdits = 0;

    const availableFiles = ['src/parser.js', 'src/comparator.js', 'src/ranges.js', 'src/satisfier.js'];
    const originalFiles = {};
    for (const f of availableFiles) {
      originalFiles[f] = fs.readFileSync(path.join(repoDir, f), 'utf8');
    }

    const resetFiles = () => {
      for (const f of availableFiles) {
        fs.writeFileSync(path.join(repoDir, f), originalFiles[f], 'utf8');
      }
    };

    const entrySym = this.search.identifyEntrySymbol(task.test_assertion_error);
    const rankedBeam = this.search.generateRankedBeam(entrySym, task.test_assertion_error);

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      attemptsCount++;
      let prompt = '';
      let activeCandidate = null;
      let activeHyp = null;

      if (arm === 'GREEDY') {
        activeCandidate = rankedBeam[0];
        const focused = this.substrate.generateFocusedContext(activeCandidate.symbol);
        prompt = `[LIN Semantic State]\nTarget: ${activeCandidate.symbol} (${activeCandidate.module})\nEffect: *(${focused.effect})\n\n[Bug Report]\n${task.issue_description}\n\n[Failing Test Error]\n${task.test_assertion_error}\n\n[Module Code: ${activeCandidate.module}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, activeCandidate.module), 'utf8')}\n\`\`\`\n\nProvide the complete fixed code for ${activeCandidate.module} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'BEAM_3' || arm === 'BEAM_5') {
        const k = arm === 'BEAM_3' ? 3 : 5;
        const beamSlice = rankedBeam.slice(0, k);
        activeCandidate = this.search.selectAdaptiveCandidate(beamSlice, attempt);
        activeHyp = this.ledger.registerHypothesis({
          symbol: activeCandidate.symbol,
          module: activeCandidate.module,
          reason: `Beam rank candidate score ${activeCandidate.score}`
        });

        const focused = this.substrate.generateFocusedContext(activeCandidate.symbol);
        const searchMemory = this.ledger.generateSearchMemoryPrompt();

        prompt = `[LIN Fixed Beam State (Top-${k})]\n`;
        prompt += `* Active Hypothesis: ${activeHyp.id} -> Investigating '${activeCandidate.symbol}' in '${activeCandidate.module}'\n`;
        prompt += `* Ranked Beam: [${beamSlice.map(c => `${c.symbol} (${c.score})`).join(', ')}]\n`;
        prompt += `* Declared Effect: *(${focused.effect})\n`;
        if (searchMemory) prompt += `\n${searchMemory}\n`;

        prompt += `\n[Bug Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        prompt += `[Target Module: ${activeCandidate.module}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, activeCandidate.module), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${activeCandidate.module} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'ADAPTIVE') {
        // Adaptive: On-Demand Candidate Injection without prompt bloat
        activeCandidate = this.search.selectAdaptiveCandidate(rankedBeam, attempt);
        activeHyp = this.ledger.registerHypothesis({
          symbol: activeCandidate.symbol,
          module: activeCandidate.module,
          reason: `Multi-feature score ${activeCandidate.score}`
        });

        const focused = this.substrate.generateFocusedContext(activeCandidate.symbol);
        const refutedList = this.ledger.getRefutedHypotheses();

        prompt = `[LIN Adaptive State: Target ${activeCandidate.symbol} (${activeCandidate.module})]\n`;
        prompt += `* Multi-Feature Score: ${activeCandidate.score} | Role: ${activeCandidate.role} | Effect: *(${focused.effect})\n`;
        if (refutedList.length > 0) {
          prompt += `* Refuted Branches: [${refutedList.map(h => `${h.symbol} (${h.module})`).join(', ')}]\n`;
        }

        prompt += `\n[Bug Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        prompt += `[Module Code: ${activeCandidate.module}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, activeCandidate.module), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${activeCandidate.module} inside a single \`\`\`javascript code block.`;
      }

      const llm = await this.queryLLM(prompt);
      totalPromptTokens += llm.promptTokens;
      totalEvalTokens += llm.evalTokens;
      totalDurationMs += llm.durationMs;

      const defaultTargetFile = activeCandidate ? activeCandidate.module : availableFiles[0];
      const { targetFile, code } = this.extractFileAndPatch(llm.response, defaultTargetFile, availableFiles);

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
        if (activeHyp) this.ledger.verifyHypothesis(activeHyp.id);
        break;
      } else {
        resetFiles();
        if (activeHyp) {
          this.ledger.refuteHypothesis(activeHyp.id, testRes.output.slice(0, 120));
        }
      }
    }

    resetFiles();

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
