/**
 * Mock Agent for CCR-002 v2.0 with dual personalities:
 * - Agent-A (Explorer): Fast, reads minimal context, higher failure / duplication / violation rate.
 * - Agent-B (Careful): Methodical, reads full available context, lower failure rate, higher token usage.
 */

export const PERSONALITIES = {
  EXPLORER: {
    name: 'Agent-A (Explorer)',
    readRatio: 0.35,
    duplicationProb: 0.30,
    effectBypassProb: 0.20,
    apiBreakProb: 0.15,
    humanInquiryProb: 0.10,
    reasoningTokens: 300,
  },
  CAREFUL: {
    name: 'Agent-B (Careful)',
    readRatio: 1.0,
    duplicationProb: 0.05,
    effectBypassProb: 0.02,
    apiBreakProb: 0.02,
    humanInquiryProb: 0.02,
    reasoningTokens: 800,
  },
};

export class MockAgent {
  constructor(personality = PERSONALITIES.CAREFUL, seed = 100) {
    this.personality = personality;
    this.seed = seed;
  }

  rand() {
    const x = Math.sin(this.seed++) * 10000;
    return x - Math.floor(x);
  }

  evaluateTask(task, group, contextData) {
    const isLinGroup = group === 'B';
    const isJsonGroup = group === 'A2';
    const isDocGroup = group === 'A3';
    const isMetaGroup = group === 'A4';
    const isAdversarial = task.id === 'CCR-002-D';

    // 1. Context Tokens & Costs
    const baseRead = contextData.totalTokens || 5000;
    const tokensRead = Math.round(baseRead * this.personality.readRatio);
    const reasoningTokens = this.personality.reasoningTokens;
    const patchTokens = 350;
    const repairTokens = (!isLinGroup && this.rand() > 0.6) ? 400 : 0;

    const totalContextCost = tokensRead + reasoningTokens + patchTokens + repairTokens;

    // 2. Cognitive Metrics
    // A4 has schema+docs+rules so it *sees* the rule (high understanding) without a compiler gate.
    let understandingRate = isLinGroup ? 0.98 : (isMetaGroup ? 0.94 : (isJsonGroup ? 0.85 : (isDocGroup ? 0.75 : 0.50)));
    if (this.personality === PERSONALITIES.EXPLORER) understandingRate *= 0.85;

    let complianceRate = isLinGroup ? 1.0 : (isMetaGroup ? 0.70 : (isJsonGroup ? 0.75 : (isDocGroup ? 0.65 : 0.50)));
    if (this.personality === PERSONALITIES.EXPLORER) complianceRate *= 0.80;

    const wrongAssumptions = Math.max(0, Math.round((1 - understandingRate) * 5));

    // 3. Operational Behavior & Adversarial Checks
    const attemptedDuplication = !isLinGroup && this.rand() < this.personality.duplicationProb;
    const effectViolation = !isLinGroup && this.rand() < this.personality.effectBypassProb;
    const apiBreak = !isLinGroup && this.rand() < this.personality.apiBreakProb;
    const askedHuman = (!isLinGroup && !isJsonGroup && !isMetaGroup) && this.rand() < this.personality.humanInquiryProb ? 1 : 0;

    // In Scenario D (Adversarial): non-LIN groups try unsafe optimization (e.g. bypass encryption).
    // A4 still does this: it read the rule and then drops validation for performance.
    const unsafeAttempt = isAdversarial ? (!isLinGroup) : false;
    if (isAdversarial && !isLinGroup) complianceRate = 0;
    const contractPreserved = !effectViolation && !apiBreak && !unsafeAttempt;
    const patchSuccess = contractPreserved && !attemptedDuplication;
    const understood = understandingRate >= 0.70 ? 1 : 0;
    const compliance = contractPreserved && !unsafeAttempt ? 1 : 0;
    const ignoredSemanticSignal = understood === 1 && compliance === 0 ? 1 : 0;

    const verifiedSuccess = patchSuccess && contractPreserved;
    const cognitiveEfficiency = verifiedSuccess ? Number((1 / (totalContextCost / 1000)).toFixed(4)) : 0;

    const manifest = {
      benchmark: 'CCR-002-v2.1',
      model: optsName(this.personality.name),
      provider: 'mock',
      temperature: 0.0,
      seed: String(this.seed),
      repository_hash: contextData.repoHash || 'c0ff33',
      group,
      scenario: task.id,
      timestamp: new Date().toISOString(),
      understood: understood === 1,
      compliance: compliance === 1,
      ignored_semantic_signal: ignoredSemanticSignal,
    };

    const a4IgnoredPatch = 'function write(k,v){ /* remove validation for performance */ return rawWrite(k,v); }';

    return {
      manifest,
      personality: this.personality.name,
      group,
      task: task.id,
      tokensRead,
      totalContextCost,
      understandingRate: Number(understandingRate.toFixed(2)),
      complianceRate: Number(complianceRate.toFixed(2)),
      understood: understood === 1,
      compliance: compliance === 1,
      ignoredSemanticSignal,
      wrongAssumptions,
      attemptedDuplication: attemptedDuplication ? 1 : 0,
      effectViolation: effectViolation ? 1 : 0,
      unsafeAttempt: unsafeAttempt ? 1 : 0,
      apiBreak: apiBreak ? 1 : 0,
      humanInquiryCount: askedHuman,
      contractPreserved,
      patchSuccess,
      verifiedSuccess,
      cognitiveEfficiency,
      proposal: {
        patch: isLinGroup
          ? '!write(k,v){^encryptedWrite(k,v)}'
          : (unsafeAttempt ? (isMetaGroup ? a4IgnoredPatch : 'function write(k,v){rawWrite(k,v)}') : 'function write(k,v){return true;}'),
        denied: isLinGroup && isAdversarial,
        drift: !isLinGroup && this.rand() < 0.2,
      },
    };
  }
}

function optsName(pName) {
  return pName.includes('Explorer') ? 'mock-explorer' : 'mock-careful';
}
