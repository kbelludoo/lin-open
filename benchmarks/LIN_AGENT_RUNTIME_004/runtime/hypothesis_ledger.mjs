// LIN Structured Hypothesis Ledger: Search Memory with Refutation & Confidence

export class HypothesisLedger {
  constructor() {
    this.hypotheses = new Map(); // id -> hypothesis object
    this.hypCounter = 0;
  }

  registerHypothesis({ symbol, module, reason, initialConfidence = 0.85 }) {
    this.hypCounter++;
    const id = `H${this.hypCounter}`;
    const hyp = {
      id,
      symbol,
      module,
      reason,
      status: 'ACTIVE', // 'ACTIVE', 'REFUTED', 'VERIFIED'
      confidence: initialConfidence,
      refutationEvidence: null
    };
    this.hypotheses.set(id, hyp);
    return hyp;
  }

  refuteHypothesis(hypId, evidence) {
    const hyp = this.hypotheses.get(hypId);
    if (hyp) {
      hyp.status = 'REFUTED';
      hyp.confidence = 0.0;
      hyp.refutationEvidence = String(evidence).slice(0, 200);
    }
  }

  verifyHypothesis(hypId) {
    const hyp = this.hypotheses.get(hypId);
    if (hyp) {
      hyp.status = 'VERIFIED';
      hyp.confidence = 1.0;
    }
  }

  getActiveHypotheses() {
    return Array.from(this.hypotheses.values()).filter(h => h.status === 'ACTIVE');
  }

  getRefutedHypotheses() {
    return Array.from(this.hypotheses.values()).filter(h => h.status === 'REFUTED');
  }

  generateSearchMemoryPrompt() {
    const refuted = this.getRefutedHypotheses();
    if (refuted.length === 0) return '';

    let prompt = `[LIN Hypothesis Search Memory - Pruned Search Branches]\n`;
    for (const h of refuted) {
      prompt += `* ${h.id} [REFUTED] Module: '${h.module}' (${h.symbol})\n`;
      prompt += `  - Reason Refuted: ${h.refutationEvidence}\n`;
      prompt += `  - Action: Do NOT edit '${h.module}'. Search downstream/upstream dependencies.\n`;
    }
    return prompt;
  }

  clear() {
    this.hypotheses.clear();
    this.hypCounter = 0;
  }
}
