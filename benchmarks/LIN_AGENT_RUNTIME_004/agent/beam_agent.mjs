// LIN Beam Search Autonomous Debugging Agent with Robust Failover

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { SemanticSubstrate } from '../../LIN_AGENT_RUNTIME_001/runtime/semantic_substrate.mjs';
import { VerifierGate } from '../../LIN_AGENT_RUNTIME_001/runtime/verifier_gate.mjs';
import { HypothesisLedger } from '../runtime/hypothesis_ledger.mjs';
import { SemanticBeamSearch } from '../runtime/semantic_beam_search.mjs';

export class BeamAgent {
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
    this.beamSearch = new SemanticBeamSearch(this.substrate, this.ledger);
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

      // Brief backoff
      await new Promise(resolve => setTimeout(resolve, 800));
    }

    // Failover to local Ollama
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

    throw new Error("All LLM providers unavailable after retries");
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
      // Strip any accidental leading FILE: headers inside code block
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

  async runBlindTask({ task, repoDir, arm = 'LIN_BEAM', maxAttempts = 3 }) {
    this.ledger.clear();
    let historyBuffer = [];
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

    // Initialize Beam Search
    const entrySym = this.beamSearch.identifyEntrySymbol(task.test_assertion_error);
    const candidateBeam = this.beamSearch.generateBeam(entrySym);

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      attemptsCount++;
      let prompt = '';
      let activeCandidate = null;
      let activeHyp = null;

      if (arm === 'RAW') {
        prompt = `You are an expert debugger fixing a bug in an open-source SemVer repository.\n\n[Bug Report]\n${task.issue_description}\n\n[Failing Test Error]\n${task.test_assertion_error}\n\n[Repository Files]\n`;
        for (const f of availableFiles) {
          prompt += `--- ${f} ---\n${fs.readFileSync(path.join(repoDir, f), 'utf8')}\n\n`;
        }
        prompt += `Identify which file contains the bug and provide the complete fixed file code in a single \`\`\`javascript code block with header 'FILE: <filepath>'.`;

      } else if (arm === 'CHAT_HISTORY') {
        const histText = historyBuffer.map(h => `[Attempt ${h.attempt} Failed on ${h.file}]:\n${h.testOutput}`).join('\n\n');
        prompt = `You are an expert debugger fixing a bug in an open-source SemVer repository.\n\n[Bug Report]\n${task.issue_description}\n\n[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        if (histText) prompt += `[Previous Attempt Failure Output]\n${histText}\n\n`;
        prompt += `[Repository Files]\n`;
        for (const f of availableFiles) {
          prompt += `--- ${f} ---\n${fs.readFileSync(path.join(repoDir, f), 'utf8')}\n\n`;
        }
        prompt += `Identify which file contains the bug and provide the complete fixed file code in a single \`\`\`javascript code block with header 'FILE: <filepath>'.`;

      } else if (arm === 'LIN_GREEDY') {
        // Greedy: always picks top candidate without refutation shift
        activeCandidate = candidateBeam[0];
        const focused = this.substrate.generateFocusedContext(activeCandidate.symbol);
        prompt = `[LIN Semantic State]\nTarget: ${activeCandidate.symbol} (${activeCandidate.module})\nEffect: *(${focused.effect})\nDependents: [${focused.dependents.join(', ')}]\n\n[Bug Report]\n${task.issue_description}\n\n[Failing Test Error]\n${task.test_assertion_error}\n\n[Module Code: ${activeCandidate.module}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, activeCandidate.module), 'utf8')}\n\`\`\`\n\nProvide the complete fixed code for ${activeCandidate.module} inside a single \`\`\`javascript code block.`;

      } else if (arm === 'LIN_BEAM') {
        // Beam Search: picks next unrefuted candidate in beam ranking
        activeCandidate = this.beamSearch.selectCandidateForAttempt(candidateBeam, attempt);
        activeHyp = this.ledger.registerHypothesis({
          symbol: activeCandidate.symbol,
          module: activeCandidate.module,
          reason: `Topological candidate with score ${activeCandidate.score}`
        });

        const focused = this.substrate.generateFocusedContext(activeCandidate.symbol);
        const searchMemory = this.ledger.generateSearchMemoryPrompt();

        prompt = `[LIN Semantic Beam State]\n`;
        prompt += `* Active Hypothesis: ${activeHyp.id} -> Investigating '${activeCandidate.symbol}' in '${activeCandidate.module}'\n`;
        prompt += `* Candidate Score: ${activeCandidate.score} (${activeCandidate.role})\n`;
        prompt += `* Ranked Beam: [${candidateBeam.map(c => `${c.symbol} (${c.module}): ${c.score}`).join(', ')}]\n`;
        prompt += `* Declared Effect: *(${focused.effect})\n`;
        prompt += `* Transitive Dependents: [${focused.dependents.join(', ')}]\n`;
        if (searchMemory) {
          prompt += `\n${searchMemory}\n`;
        }

        prompt += `\n[Bug Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        prompt += `[Target Module Code: ${activeCandidate.module}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, activeCandidate.module), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${activeCandidate.module} inside a single \`\`\`javascript code block.`;
      }

      // Query LLM
      const llm = await this.queryLLM(prompt);
      totalPromptTokens += llm.promptTokens;
      totalEvalTokens += llm.evalTokens;
      totalDurationMs += llm.durationMs;

      // Extract patch
      const defaultTargetFile = activeCandidate ? activeCandidate.module : availableFiles[0];
      const { targetFile, code } = this.extractFileAndPatch(llm.response, defaultTargetFile, availableFiles);

      if (!code) continue;

      if (targetFile === task.ground_truth.file) {
        rootCauseFound = true;
      } else {
        wrongFileEdits++;
      }

      // Apply patch to disk
      fs.writeFileSync(path.join(repoDir, targetFile), code, 'utf8');

      // Run tests
      const testRes = this.runTests(repoDir);

      if (testRes.passed) {
        if (attempt === 1) initialSuccess = true;
        else recoveredSuccess = true;
        if (activeHyp) this.ledger.verifyHypothesis(activeHyp.id);
        break;
      } else {
        // Rollback & Record Refutation
        resetFiles();
        historyBuffer.push({ attempt, file: targetFile, testOutput: testRes.output.slice(0, 200) });
        if (activeHyp) {
          this.ledger.refuteHypothesis(activeHyp.id, testRes.output.slice(0, 150));
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
