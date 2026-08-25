// LIN Dynamic Re-Ranking Engine with Topological Boost & Live Invariant Queries

export class DynamicReRanker {
  constructor(substrate, hypothesisLedger) {
    this.substrate = substrate;
    this.ledger = hypothesisLedger;
    this.sessionHistory = new Map(); // symbol -> { successes: 0, attempts: 0 }
  }

  recordAttemptOutcome(symbol, passed) {
    const hist = this.sessionHistory.get(symbol) || { successes: 0, attempts: 0 };
    hist.attempts++;
    if (passed) hist.successes++;
    this.sessionHistory.set(symbol, hist);
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
    return 5; // default far distance
  }

  computeDynamicRankings(entrySymbol, testErrorOutput, refutedCandidates = []) {
    const candidateList = [];
    const allSymbols = Array.from(this.substrate.symbolIndex.keys());

    for (const sym of allSymbols) {
      const node = this.substrate.symbolIndex.get(sym);
      if (!node) continue;

      // 1. If refuted, score is 0
      if (refutedCandidates.includes(sym)) {
        continue;
      }

      // 2. Base Topological Proximity to Entry Symbol (0.30)
      const distToEntry = this.getDAGDistance(entrySymbol, sym);
      const sGraph = Math.max(0.1, 1.0 - (distToEntry * 0.25));

      // 3. Error Trace Lexical Matching (0.25)
      let sError = 0.0;
      if (testErrorOutput.includes(sym)) sError += 0.60;
      if (testErrorOutput.includes(node.module)) sError += 0.40;
      sError = Math.min(1.0, sError);

      // 4. Invariant & Contract Density (0.20)
      const invariants = (this.substrate.invariants || []).filter(i => i.symbol === sym);
      const sInvariant = invariants.length > 0 ? 0.90 : 0.40;

      // 5. Live Session History (0.15)
      const hist = this.sessionHistory.get(sym);
      const sHistory = hist ? (hist.successes / Math.max(1, hist.attempts)) : 0.50;

      // 6. Effect Safety (0.10)
      const sEffect = node.effect === 'Pure' ? 0.95 : 0.50;

      let baseScore = (
        0.30 * sGraph +
        0.25 * sError +
        0.20 * sInvariant +
        0.15 * sHistory +
        0.10 * sEffect
      );

      // 7. Topological Propagation Boost from Recently Refuted Candidates
      if (refutedCandidates.length > 0) {
        const lastRefuted = refutedCandidates[refutedCandidates.length - 1];
        const distToRefuted = this.getDAGDistance(lastRefuted, sym);
        if (distToRefuted > 0) {
          const boost = 0.35 / (1 + distToRefuted);
          baseScore += boost;
        }
      }

      candidateList.push({
        symbol: sym,
        module: node.module,
        effect: node.effect,
        score: Number(baseScore.toFixed(3)),
        invariantsCount: invariants.length
      });
    }

    // Sort descending
    candidateList.sort((a, b) => b.score - a.score);
    return candidateList;
  }
}
