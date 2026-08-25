// LIN Semantic Localizer: Transitive Call-Graph Navigation & Trauma Refutation

export class SemanticLocalizer {
  constructor(substrate, trauma) {
    this.substrate = substrate;
    this.trauma = trauma;
  }

  identifyEntrySymbol(testErrorOutput) {
    for (const [symbolName] of this.substrate.symbolIndex.entries()) {
      if (testErrorOutput.includes(symbolName)) {
        return symbolName;
      }
    }
    return 'satisfiesRange'; // fallback
  }

  localizeCandidates(entrySymbol) {
    // 1. Get full transitive dependency chain for entry symbol
    const callers = this.substrate.getAffectedSubtree(entrySymbol);
    const callees = this.substrate.dependencyGraph.get(entrySymbol) || new Set();

    const candidateSymbols = new Set([entrySymbol, ...callees, ...callers]);
    const refutedSymbols = new Set(this.trauma.records.map(r => r.targetSymbol));

    // 2. Rank candidates: Prioritize unrefuted symbols in the active sub-DAG
    const ranked = [];
    for (const sym of candidateSymbols) {
      const node = this.substrate.symbolIndex.get(sym);
      if (node) {
        const isRefuted = refutedSymbols.has(sym);
        ranked.push({
          symbol: sym,
          module: node.module,
          effect: node.effect,
          isRefuted,
          priority: isRefuted ? 0 : 1
        });
      }
    }

    ranked.sort((a, b) => b.priority - a.priority);
    return ranked;
  }
}
