// LIN Semantic Beam Search Ranker

export class SemanticBeamSearch {
  constructor(substrate, hypothesisLedger) {
    this.substrate = substrate;
    this.ledger = hypothesisLedger;
  }

  identifyEntrySymbol(testErrorOutput) {
    for (const [symbolName] of this.substrate.symbolIndex.entries()) {
      if (testErrorOutput.includes(symbolName)) {
        return symbolName;
      }
    }
    return 'satisfiesRange';
  }

  generateBeam(entrySymbol) {
    const beam = [];
    const visited = new Set();

    // 1. Direct callees (children) - where implementation logic lives
    const directCallees = this.substrate.dependencyGraph.get(entrySymbol) || new Set();
    for (const callee of directCallees) {
      const node = this.substrate.symbolIndex.get(callee);
      if (node && !visited.has(callee)) {
        visited.add(callee);
        beam.push({ symbol: callee, module: node.module, score: 0.90, role: 'callee' });
      }
    }

    // 2. Entry symbol itself
    const entryNode = this.substrate.symbolIndex.get(entrySymbol);
    if (entryNode && !visited.has(entrySymbol)) {
      visited.add(entrySymbol);
      beam.push({ symbol: entrySymbol, module: entryNode.module, score: 0.85, role: 'entry' });
    }

    // 3. Transitive upstream callers (parents)
    const transitiveCallers = this.substrate.getAffectedSubtree(entrySymbol);
    for (const caller of transitiveCallers) {
      const node = this.substrate.symbolIndex.get(caller);
      if (node && !visited.has(caller)) {
        visited.add(caller);
        beam.push({ symbol: caller, module: node.module, score: 0.70, role: 'caller' });
      }
    }

    // 4. Secondary depth callees (leaf utilities)
    for (const callee of Array.from(directCallees)) {
      const leafCallees = this.substrate.dependencyGraph.get(callee) || new Set();
      for (const leaf of leafCallees) {
        const node = this.substrate.symbolIndex.get(leaf);
        if (node && !visited.has(leaf)) {
          visited.add(leaf);
          beam.push({ symbol: leaf, module: node.module, score: 0.60, role: 'leaf' });
        }
      }
    }

    return beam;
  }

  selectCandidateForAttempt(beam, attemptIndex) {
    const refuted = new Set(this.ledger.getRefutedHypotheses().map(h => h.symbol));

    // Filter out refuted candidates
    const available = beam.filter(c => !refuted.has(c.symbol));

    if (available.length > 0) {
      // Pick next highest scored candidate
      return available[0];
    }

    // Fallback if all in beam refuted
    return beam[(attemptIndex - 1) % beam.length];
  }
}
