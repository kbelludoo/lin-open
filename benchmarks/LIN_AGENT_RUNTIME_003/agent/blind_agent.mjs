// LIN Blind Debugging Autonomous Agent

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { SemanticSubstrate } from '../../LIN_AGENT_RUNTIME_001/runtime/semantic_substrate.mjs';
import { TraumaLedger } from '../../LIN_AGENT_RUNTIME_001/runtime/trauma_ledger.mjs';
import { VerifierGate } from '../../LIN_AGENT_RUNTIME_001/runtime/verifier_gate.mjs';
import { SemanticLocalizer } from '../runtime/semantic_localizer.mjs';

export class BlindAgent {
  constructor({
    routerUrl = 'http://localhost:20128/v1',
    apiKey = 'sk-4f1d4e3f72aabeb4-eayna4-68bb3e83',
    primaryModel = 'ag/gemini-3.7-flash-low',
    secondaryModel = 'ag/gemini-3.5-flash-low'
  } = {}) {
    this.routerUrl = routerUrl;
    this.apiKey = apiKey;
    this.primaryModel = primaryModel;
    this.secondaryModel = secondaryModel;
    this.substrate = new SemanticSubstrate();
    this.trauma = new TraumaLedger();
    this.verifier = new VerifierGate(this.substrate);
    this.localizer = new SemanticLocalizer(this.substrate, this.trauma);
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
          signal: AbortSignal.timeout(10000)
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
    throw new Error("All LLM providers unavailable");
  }

  extractFileAndPatch(llmResponse, availableFiles) {
    // Parse target file path and code block
    let targetFile = null;
    for (const f of availableFiles) {
      if (llmResponse.includes(f) || llmResponse.includes(path.basename(f))) {
        targetFile = f;
        break;
      }
    }
    if (!targetFile) targetFile = availableFiles[0];

    const match = llmResponse.match(/```(?:javascript|js)?\s*([\s\S]*?)```/i);
    const code = match ? match[1].trim() : null;

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

  async runBlindTask({ task, repoDir, group = 'LIN', maxAttempts = 3 }) {
    this.trauma.clear();
    let historyBuffer = [];
    let initialSuccess = false;
    let recoveredSuccess = false;
    let totalPromptTokens = 0;
    let totalEvalTokens = 0;
    let totalDurationMs = 0;
    let attemptsCount = 0;
    let wrongFileEdits = 0;
    let rootCauseFound = false;

    const availableFiles = [
      'src/parser.js',
      'src/comparator.js',
      'src/ranges.js',
      'src/satisfier.js'
    ];

    // Backup all files for rollback
    const originalFiles = {};
    for (const f of availableFiles) {
      originalFiles[f] = fs.readFileSync(path.join(repoDir, f), 'utf8');
    }

    const resetFiles = () => {
      for (const f of availableFiles) {
        fs.writeFileSync(path.join(repoDir, f), originalFiles[f], 'utf8');
      }
    };

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      attemptsCount++;

      // 1. Build Blind Prompt conditioned on Group
      let prompt = '';

      if (group === 'RAW') {
        prompt = `You are an expert debugger fixing a bug in an open-source SemVer repository.\n\n`;
        prompt += `[Bug Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        prompt += `[Repository Files]\n`;
        for (const f of availableFiles) {
          prompt += `--- ${f} ---\n${fs.readFileSync(path.join(repoDir, f), 'utf8')}\n\n`;
        }
        prompt += `Identify which file contains the root cause bug and provide the complete fixed file code.\n`;
        prompt += `Format response:\nFILE: <filepath>\n\`\`\`javascript\n<complete fixed code>\n\`\`\``;

      } else if (group === 'CHAT_HISTORY') {
        const histText = historyBuffer.map(h => `[Attempt ${h.attempt} Failed Patch on ${h.file}]:\n${h.testOutput}`).join('\n\n');
        prompt = `You are an expert debugger fixing a bug in an open-source SemVer repository.\n\n`;
        prompt += `[Bug Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        if (histText) {
          prompt += `[Previous Attempt Failures & Terminal Errors]\n${histText}\n\n`;
        }
        prompt += `[Repository Files]\n`;
        for (const f of availableFiles) {
          prompt += `--- ${f} ---\n${fs.readFileSync(path.join(repoDir, f), 'utf8')}\n\n`;
        }
        prompt += `Identify which file contains the root cause bug and provide the complete fixed file code.\n`;
        prompt += `Format response:\nFILE: <filepath>\n\`\`\`javascript\n<complete fixed code>\n\`\`\``;

      } else if (group === 'LIN') {
        // LIN Semantic Localizer: navigates DAG from failing test assertion
        const entrySym = this.localizer.identifyEntrySymbol(task.test_assertion_error);
        const candidates = this.localizer.localizeCandidates(entrySym);
        const traumaPrompt = this.trauma.generateTraumaPrompt();

        const topCandidate = candidates.find(c => !c.isRefuted) || candidates[0];
        const focusedContext = this.substrate.generateFocusedContext(topCandidate.symbol);

        prompt = `[LIN Semantic State Context]\n`;
        prompt += `* Entry Failure Symbol: ${entrySym}\n`;
        prompt += `* Active Call-DAG Search Candidates: [${candidates.map(c => `${c.symbol} (${c.module})${c.isRefuted ? ' [REFUTED]' : ''}`).join(', ')}]\n`;
        prompt += `* Primary Candidate: ${topCandidate.symbol} in '${topCandidate.module}'\n`;
        prompt += `* Declared Effect: *(${focusedContext.effect})\n`;
        prompt += `* Downstream Transitive Dependents: [${focusedContext.dependents.join(', ')}]\n`;
        if (traumaPrompt) {
          prompt += `\n${traumaPrompt}\n`;
        }

        prompt += `\n[Bug Report]\n${task.issue_description}\n\n`;
        prompt += `[Failing Test Error]\n${task.test_assertion_error}\n\n`;
        prompt += `[Candidate Module Code: ${topCandidate.module}]\n\`\`\`javascript\n${fs.readFileSync(path.join(repoDir, topCandidate.module), 'utf8')}\n\`\`\`\n\n`;
        prompt += `Provide the complete fixed code for ${topCandidate.module} inside a single \`\`\`javascript code block.`;
      }

      // 2. Query LLM
      const llm = await this.queryLLM(prompt);
      totalPromptTokens += llm.promptTokens;
      totalEvalTokens += llm.evalTokens;
      totalDurationMs += llm.durationMs;

      // 3. Extract target file and patch
      const { targetFile, code } = this.extractFileAndPatch(llm.response, availableFiles);

      if (!code) {
        continue;
      }

      // Check localization accuracy against ground truth
      if (targetFile === task.ground_truth.file) {
        rootCauseFound = true;
      } else {
        wrongFileEdits++;
      }

      // 4. Apply patch
      fs.writeFileSync(path.join(repoDir, targetFile), code, 'utf8');

      // 5. Run tests
      const testRes = this.runTests(repoDir);

      if (testRes.passed) {
        if (attempt === 1) initialSuccess = true;
        else recoveredSuccess = true;
        break;
      } else {
        // Rollback and record trauma
        resetFiles();
        historyBuffer.push({ attempt, file: targetFile, testOutput: testRes.output.slice(0, 250) });
        this.trauma.recordFailure({
          attempt,
          targetSymbol: targetFile,
          brokenInvariant: 'TEST_ASSERTION_FAILED',
          errorDiagnostic: testRes.output.slice(0, 180),
          refutedHypothesis: `Attempt ${attempt} edited '${targetFile}' but failed to satisfy test suite`
        });
      }
    }

    resetFiles();

    return {
      task_id: task.task_id,
      group,
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
