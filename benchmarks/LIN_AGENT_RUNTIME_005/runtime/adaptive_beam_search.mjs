// LIN Adaptive Beam Search Engine

import { MultiFeatureRanker } from './multi_feature_ranker.mjs';

export class AdaptiveBeamSearch {
  constructor(substrate, hypothesisLedger) {
    this.substrate = substrate;
    this.ledger = hypothesisLedger;
    this.ranker = new MultiFeatureRanker(substrate);
  }

  identifyEntrySymbol(testErrorOutput) {
    for (const [symbolName] of this.substrate.symbolIndex.entries()) {
      if (testErrorOutput.includes(symbolName)) {
        return symbolName;
      }
    }
    return 'satisfiesRange';
  }

  generateRankedBeam(entrySymbol, testErrorOutput) {
    const candidates = [];
    const visited = new Set();

    // 1. Direct callees
    const directCallees = this.substrate.dependencyGraph.get(entrySymbol) || new Set();
    for (const callee of directCallees) {
      const node = this.substrate.symbolIndex.get(callee);
      if (node && !visited.has(callee)) {
        visited.add(callee);
        const score = this.ranker.computeScore({
          symbol: callee,
          module: node.module,
          role: 'callee',
          entrySymbol,
          testErrorOutput
        });
        candidates.push({ symbol: callee, module: node.module, score, role: 'callee' });
      }
    }

    // 2. Entry symbol
    const entryNode = this.substrate.symbolIndex.get(entrySymbol);
    if (entryNode && !visited.has(entrySymbol)) {
      visited.add(entrySymbol);
      const score = this.ranker.computeScore({
        symbol: entrySymbol,
        module: entryNode.module,
        role: 'entry',
        entrySymbol,
        testErrorOutput
      });
      candidates.push({ symbol: entrySymbol, module: entryNode.module, score, role: 'entry' });
    }

    // 3. Leaf utilities
    for (const callee of Array.from(directCallees)) {
      const leafCallees = this.substrate.dependencyGraph.get(callee) || new Set();
      for (const leaf of leafCallees) {
        const node = this.substrate.symbolIndex.get(leaf);
        if (node && !visited.has(leaf)) {
          visited.add(leaf);
          const score = this.ranker.computeScore({
            symbol: leaf,
            module: node.module,
            role: 'leaf',
            entrySymbol,
            testErrorOutput
          });
          candidates.push({ symbol: leaf, module: node.module, score, role: 'leaf' });
        }
      }
    }

    // Sort descending by multi-feature score
    candidates.sort((a, b) => b.score - a.score);
    return candidates;
  }

  selectAdaptiveCandidate(rankedBeam, attemptIndex) {
    const refuted = new Set(this.ledger.getRefutedHypotheses().map(h => h.symbol));
    const available = rankedBeam.filter(c => !refuted.has(c.symbol));

    if (available.length > 0) {
      return available[0];
    }
    return rankedBeam[(attemptIndex - 1) % rankedBeam.length];
  }
}
