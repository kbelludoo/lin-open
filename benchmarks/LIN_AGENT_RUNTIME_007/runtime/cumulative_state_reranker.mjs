// LIN Cumulative State Search Evolution Engine with Depth Awareness

export class CumulativeStateReRanker {
  constructor(substrate, hypothesisLedger) {
    this.substrate = substrate;
    this.ledger = hypothesisLedger;
    this.currentScoreMap = new Map(); // symbol -> float
  }

  resetTaskState() {
    this.currentScoreMap.clear();
    this.ledger.clear();
  }

  getDAGDistance(src, target) {
    if (src === target) return 0;
    const queue = [[src, 0]];
    const visited = new Set([src]);

    while (queue.length > 0) {
      const [curr, dist] = queue.shift();
      const callees = this.substrate.dependencyGraph.get(curr) || new Set();
      const callers = this.substrate.getAffectedSubtree(curr);
      const neighbors = new Set([...callees, ...callers]);

      for (const n of neighbors) {
        if (n === target) return dist + 1;
        if (!visited.has(n)) {
          visited.add(n);
          queue.push([n, dist + 1]);
        }
      }
    }
    return 5;
  }

  initializeBaseScores(entrySymbol, testErrorOutput) {
    this.currentScoreMap.clear();
    const allSymbols = Array.from(this.substrate.symbolIndex.keys());

    for (const sym of allSymbols) {
      const node = this.substrate.symbolIndex.get(sym);
      if (!node) continue;

      // 1. Topological proximity to entry
      const dist = this.getDAGDistance(entrySymbol, sym);
      const sGraph = Math.max(0.1, 1.0 - (dist * 0.22));

      // 2. Lexical error match
      let sError = 0.0;
      if (testErrorOutput.includes(sym)) sError += 0.60;
      if (testErrorOutput.includes(node.module)) sError += 0.40;
      sError = Math.min(1.0, sError);

      // 3. Invariant density
      const invariants = (this.substrate.invariants || []).filter(i => i.symbol === sym);
      const sInv = invariants.length > 0 ? 0.90 : 0.40;

      // 4. Effect safety
      const sEffect = node.effect === 'Pure' ? 0.95 : 0.50;

      const score0 = (
        0.35 * sGraph +
        0.30 * sError +
        0.25 * sInv +
        0.10 * sEffect
      );

      this.currentScoreMap.set(sym, Number(score0.toFixed(3)));
    }
  }

  // True Cumulative Update: Score_{t+1}[C] = Score_t[C] + Delta
  updateCumulativeStateOnRefutation(refutedSymbol) {
    // 1. Prune refuted symbol to 0
    this.currentScoreMap.set(refutedSymbol, 0.0);

    // 2. Topological gradient boost to unrefuted neighbours
    for (const [sym, currScore] of this.currentScoreMap.entries()) {
      if (sym === refutedSymbol || currScore === 0.0) continue;

      const dist = this.getDAGDistance(refutedSymbol, sym);
      if (dist > 0 && dist <= 3) {
        const delta = 0.35 / (1 + dist);
        this.currentScoreMap.set(sym, Number((currScore + delta).toFixed(3)));
      }
    }
  }

  getRankedCandidates() {
    const candidates = [];
    for (const [sym, score] of this.currentScoreMap.entries()) {
      if (score === 0.0) continue; // Pruned
      const node = this.substrate.symbolIndex.get(sym);
      if (node) {
        candidates.push({
          symbol: sym,
          module: node.module,
          effect: node.effect,
          score
        });
      }
    }

    candidates.sort((a, b) => b.score - a.score);
    return candidates;
  }
}
