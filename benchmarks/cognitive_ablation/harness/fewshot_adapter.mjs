/**
 * fewshot_adapter.mjs — Adaptador A/B para testes zero-shot vs few-shot vs constrained
 *
 * Herda a infraestrutura de RealModelAdapter e adiciona:
 *   - Injeção automática de few-shot examples a partir de um arquivo .md
 *   - Modo CONSTRAINED (constraints de gramática no prompt)
 *   - Registro de qual condição (A/B/C) está sendo executada
 *   - Coleta de métricas granulares por condição
 */

import { readFileSync } from 'fs';
import { createHash } from 'crypto';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FEWSHOT_PATH = path.join(__dirname, '..', 'prompts', 'LIN_FEWSHOT_V1.md');

export class FewShotAdapter {
  constructor({
    baseUrl = 'http://localhost:11434',
    provider = 'ollama',
    model = 'qwen2.5-coder:7b',
    temperature = 0.0,
    seed = 42,
    mode = 'ZERO_SHOT',  // 'ZERO_SHOT' | 'FEW_SHOT' | 'CONSTRAINED'
  }) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.provider = provider;
    this.model = model;
    this.temperature = temperature;
    this.seed = seed;
    this.mode = mode;
    this.fewshotContent = null;

    if (mode === 'FEW_SHOT' || mode === 'CONSTRAINED') {
      this.fewshotContent = readFileSync(FEWSHOT_PATH, 'utf-8');
    }
  }

  _buildZeroShotPrompt(task) {
    return `@LIN:1.0
Task: ${task.id} (${task.family})
Spec: ${task.specification}
Forbidden effects: ${task.forbidden_effects && task.forbidden_effects.length ? task.forbidden_effects.join(', ') : 'none'}

Grammar rules:
- Function: !solve(input){ ... }
- Return: ^expression
- Conditionals: ?(cond){ ... } or ?(cond){ ... }:(cond2){ ... }:{ ... }
- Loops: #(i=0; i<len; i++){ ... }
- Pure assignments: a = 1; b = 2;

Output ONLY the raw LIN function !solve(input){ ... } without markdown or explanations.`;
  }

  _buildFewShotPrompt(task) {
    // fewshotContent já contém EXAMPLES + footer "Now solve..."
    // Substituímos a última linha pelo task específico
    const base = this.fewshotContent.replace(
      /END EXAMPLES\. Now solve the following task.*$/m,
      `END EXAMPLES. Now solve the following task using the same LIN syntax. Output ONLY the raw LIN function starting with !solve(input).`
    );
    return base + `\n\nTASK: ${task.specification}\nForbidden: ${(task.forbidden_effects || []).join(', ') || 'none'}`;
  }

  _buildConstrainedPrompt(task) {
    const base = this.fewshotContent.replace(
      /END EXAMPLES\. Now solve the following task.*$/m,
      `END EXAMPLES. Now solve the following task using the same LIN syntax. Output ONLY the raw LIN function starting with !solve(input).`
    );
    return base + `\n\nTASK: ${task.specification}\nForbidden: ${(task.forbidden_effects || []).join(', ') || 'none'}

CONSTRAINTS (your output MUST satisfy ALL):
1. Start with exactly !solve(input){
2. Use ^ for return
3. Use ?(cond){} for if
4. Use :(cond){} for else-if
5. Use :{} for else
6. Use #(init; cond; inc){} for loops
7. End with }
8. Do NOT include markdown, comments, or explanations`;
  }

  buildPrompt(task) {
    switch (this.mode) {
      case 'FEW_SHOT':    return this._buildFewShotPrompt(task);
      case 'CONSTRAINED': return this._buildConstrainedPrompt(task);
      default:            return this._buildZeroShotPrompt(task);
    }
  }

  extractCode(rawText) {
    let text = rawText.trim();
    const codeBlockMatch = text.match(/```(?:lin|lia|js|javascript)?\s*([\s\S]*?)```/);
    if (codeBlockMatch) {
      text = codeBlockMatch[1].trim();
    }
    return text;
  }

  async generateCandidate(task, attempt, traumaHistory = []) {
    const prompt = this.buildPrompt(task);
    const startTime = Date.now();

    let rawText = '';
    let promptTokens = 0;
    let completionTokens = 0;
    let totalTokens = 0;
    let modelError = false;
    let modelTimeout = false;

    try {
      if (this.provider === 'ollama') {
        const res = await fetch(`${this.baseUrl}/api/generate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.model,
            prompt,
            stream: false,
            options: {
              temperature: this.temperature,
              seed: this.seed,
            }
          })
        });

        if (!res.ok) {
          modelError = true;
          rawText = '';
        } else {
          const data = await res.json();
          rawText = data.response || '';
          promptTokens = typeof data.prompt_eval_count === 'number' ? data.prompt_eval_count : 0;
          completionTokens = typeof data.eval_count === 'number' ? data.eval_count : 0;
          totalTokens = promptTokens + completionTokens;
        }
      } else {
        const res = await fetch(`${this.baseUrl}/v1/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.model,
            messages: [{ role: 'user', content: prompt }],
            temperature: this.temperature,
            seed: this.seed
          })
        });

        if (!res.ok) {
          modelError = true;
          rawText = '';
        } else {
          const data = await res.json();
          const choice = data.choices && data.choices[0];
          rawText = choice && choice.message ? choice.message.content : '';
          if (data.usage) {
            promptTokens = data.usage.prompt_tokens || 0;
            completionTokens = data.usage.completion_tokens || 0;
            totalTokens = data.usage.total_tokens || 0;
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError' || err.message?.includes('timeout')) {
        modelTimeout = true;
      } else {
        modelError = true;
      }
    }

    const latency_ms = Date.now() - startTime;
    const candidateCode = this.extractCode(rawText);
    const candidate_hash = createHash('sha256').update(candidateCode).digest('hex').slice(0, 16);

    return {
      candidate_code: candidateCode,
      raw_output: rawText,
      candidate_hash,
      prompt_tokens: promptTokens,
      completion_tokens: completionTokens,
      tokens: totalTokens,
      latency_ms,
      model_error: modelError,
      model_timeout: modelTimeout,
      condition: this.mode,
    };
  }
}
