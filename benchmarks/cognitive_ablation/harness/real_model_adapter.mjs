/**
 * real_model_adapter.mjs — Adaptador universal para inferência com modelos reais locais (Ollama / OpenAI-compat)
 * 
 * Captura tokens exatos do runtime, metadados imutáveis e sanitiza extração de código.
 */

import { createHash } from 'crypto';

export class RealModelAdapter {
  constructor({
    baseUrl = 'http://localhost:11434',
    provider = 'ollama', // 'ollama' ou 'openai'
    model = 'qwen2.5-coder:7b',
    temperature = 0.0,
    seed = 42,
    systemPrompt = '',
    promptMode = 'LIN_TRAUMA' // 'NATURAL_JS', 'LIN_ZERO_SHOT', 'LIN_UNSTRUCTURED', 'LIN_TRAUMA'
  }) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.provider = provider;
    this.model = model;
    this.temperature = temperature;
    this.seed = seed;
    this.systemPrompt = systemPrompt;
    this.promptMode = promptMode;
  }

  async getModelMetadata() {
    if (this.provider === 'ollama') {
      try {
        const res = await fetch(`${this.baseUrl}/api/show`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: this.model })
        });
        if (res.ok) {
          const info = await res.json();
          return {
            provider: 'ollama',
            model: this.model,
            digest: info.digest || 'unknown',
            details: info.details || {},
            parameters: info.parameters || ''
          };
        }
      } catch (e) {
        // Fallback
      }
    }
    return {
      provider: this.provider,
      model: this.model,
      digest: 'unknown',
      details: {}
    };
  }

  buildPrompt(task, attempt, traumaHistory) {
    if (this.promptMode === 'NATURAL_JS') {
      // Sistema B: Baseline JS tradicional
      return `Task ID: ${task.id} (${task.family})
Specification: ${task.specification}
Constraints: Write a pure JavaScript function named "solve" that accepts "input" and returns the result. Do not use external libraries.

Output ONLY valid JavaScript code for function solve(input):`;
    }

    // Sistemas C, D, E, F: Representação LIN
    let prompt = `@LIN:1.0
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

    if (attempt > 1 && traumaHistory.length > 0) {
      if (this.promptMode === 'LIN_UNSTRUCTURED') {
        const lastErr = traumaHistory[traumaHistory.length - 1];
        prompt += `\n\n[RETRY FEEDBACK]: Previous attempt failed. Error: ${lastErr.error_message || 'Verification failed'}. Fix the error and try again.`;
      } else if (this.promptMode === 'LIN_TRAUMA') {
        const lastTrauma = traumaHistory[traumaHistory.length - 1];
        prompt += `\n\n[TRAUMA CONSTRAINTS - DO NOT REPEAT]:
.trauma {
  .stage = "${lastTrauma.stage}"
  .violation = "${lastTrauma.violation_class}"
  .rule = "${lastTrauma.constraint_rule}"
  .invariant = "${lastTrauma.invariant_broken}"
  .hint = "${lastTrauma.remedy_hint}"
}
You MUST obey these constraints on this retry. Output fixed !solve(input){ ... }:`;
      }
    }

    return prompt;
  }

  extractCode(rawText) {
    let text = rawText.trim();

    // Extrai de bloco markdown se o modelo envolver em ```lin ou ```js ou ```
    const codeBlockMatch = text.match(/```(?:lin|lia|js|javascript)?\s*([\s\S]*?)```/);
    if (codeBlockMatch) {
      text = codeBlockMatch[1].trim();
    }

    return text;
  }

  async generateCandidate(task, attempt, traumaHistory = []) {
    const prompt = this.buildPrompt(task, attempt, traumaHistory);
    const startTime = Date.now();

    let rawText = '';
    let promptTokens = 'UNAVAILABLE';
    let completionTokens = 'UNAVAILABLE';
    let totalTokens = 'UNAVAILABLE';

    if (this.provider === 'ollama') {
      const res = await fetch(`${this.baseUrl}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          prompt,
          system: this.systemPrompt || undefined,
          stream: false,
          options: {
            temperature: this.temperature,
            seed: this.seed
          }
        })
      });

      if (!res.ok) {
        throw new Error(`Ollama error (${res.status}): ${await res.text()}`);
      }

      const data = await res.json();
      rawText = data.response || '';
      promptTokens = typeof data.prompt_eval_count === 'number' ? data.prompt_eval_count : 'UNAVAILABLE';
      completionTokens = typeof data.eval_count === 'number' ? data.eval_count : 'UNAVAILABLE';
      totalTokens = typeof promptTokens === 'number' && typeof completionTokens === 'number'
        ? promptTokens + completionTokens
        : 'UNAVAILABLE';
    } else {
      // OpenAI-compatible endpoint
      const res = await fetch(`${this.baseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          messages: [
            ...(this.systemPrompt ? [{ role: 'system', content: this.systemPrompt }] : []),
            { role: 'user', content: prompt }
          ],
          temperature: this.temperature,
          seed: this.seed
        })
      });

      if (!res.ok) {
        throw new Error(`API error (${res.status}): ${await res.text()}`);
      }

      const data = await res.json();
      const choice = data.choices && data.choices[0];
      rawText = choice && choice.message ? choice.message.content : '';
      if (data.usage) {
        promptTokens = data.usage.prompt_tokens ?? 'UNAVAILABLE';
        completionTokens = data.usage.completion_tokens ?? 'UNAVAILABLE';
        totalTokens = data.usage.total_tokens ?? 'UNAVAILABLE';
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
      tokens: typeof totalTokens === 'number' ? totalTokens : 0,
      latency_ms
    };
  }
}
