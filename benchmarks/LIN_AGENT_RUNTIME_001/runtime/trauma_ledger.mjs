// LIN Trauma Ledger: Structured Failure Memory & Hypothesis Refutation

export class TraumaLedger {
  constructor() {
    this.records = [];
  }

  recordFailure({ attempt, targetSymbol, brokenInvariant, errorDiagnostic, refutedHypothesis }) {
    this.records.push({
      attempt,
      targetSymbol,
      brokenInvariant: brokenInvariant || 'TEST_SUITE_ASSERTION_FAILED',
      errorDiagnostic: String(errorDiagnostic || '').slice(0, 200),
      refutedHypothesis: refutedHypothesis || `Patch in attempt ${attempt} failed contract satisfaction`
    });
  }

  generateTraumaPrompt() {
    if (this.records.length === 0) return '';

    let text = `[LIN Trauma Ledger - Avoid Refuted Hypotheses]\n`;
    for (const r of this.records) {
      text += `* Attempt ${r.attempt} Failed on '${r.targetSymbol}':\n`;
      text += `  - Broken Invariant: ${r.brokenInvariant}\n`;
      text += `  - Refuted Hypothesis: ${r.refutedHypothesis}\n`;
    }
    return text;
  }

  clear() {
    this.records = [];
  }
}
