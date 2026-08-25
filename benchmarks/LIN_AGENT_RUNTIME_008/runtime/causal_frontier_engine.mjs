// LIN Causal Frontier Engine: Explicit Call-Graph Path Navigation

export class CausalFrontierEngine {
  constructor(substrate, hypothesisLedger) {
    this.substrate = substrate;
    this.ledger = hypothesisLedger;
    this.refutedSet = new Set();
    this.causalHistory = [];
  }

  reset() {
    this.refutedSet.clear();
    this.causalHistory = [];
    this.ledger.clear();
  }

  // Find shortest call path from entry symptom down to target in DAG
  findCallPath(src, target) {
    const queue = [[src, [src]]];
    const visited = new Set([src]);

    while (queue.length > 0) {
      const [curr, path] = queue.shift();
      if (curr === target) return path;

      const callees = this.substrate.dependencyGraph.get(curr) || new Set();
      for (const c of callees) {
        if (!visited.has(c)) {
          visited.add(c);
          queue.push([c, [...path, c]]);
        }
      }
    }
    return [src, target];
  }

  // Collect all transitive callees reachable from start
  getTransitiveCallees(startSymbol) {
    const callees = [];
    const queue = [startSymbol];
    const visited = new Set([startSymbol]);

    while (queue.length > 0) {
      const curr = queue.shift();
      const direct = this.substrate.dependencyGraph.get(curr) || new Set();
      for (const d of direct) {
        if (!visited.has(d)) {
          visited.add(d);
          callees.push(d);
          queue.push(d);
        }
      }
    }
    return callees;
  }

  // Select next candidate on the expanding causal frontier
  expandFrontier(entrySymbol, attempt) {
    const transitiveCallees = this.getTransitiveCallees(entrySymbol);

    if (attempt === 1) {
      // Attempt 1: Direct Entry Node or immediate callee
      if (!this.refutedSet.has(entrySymbol)) {
        const node = this.substrate.symbolIndex.get(entrySymbol);
        return {
          symbol: entrySymbol,
          module: node.module,
          depth: 1,
          path: [entrySymbol],
          role: 'entry'
        };
      }
    }

    // Attempt 2+: Traverse down the call DAG to unrefuted callees / leaf utilities
    const unrefuted = transitiveCallees.filter(c => !this.refutedSet.has(c));

    // Sort by depth descending (prioritize deep leaf utilities on later attempts)
    const rankedCandidates = unrefuted.map(sym => {
      const path = this.findCallPath(entrySymbol, sym);
      const node = this.substrate.symbolIndex.get(sym);
      const isLeaf = (this.substrate.dependencyGraph.get(sym) || new Set()).size === 0;

      // Score prioritizes deeper nodes on higher attempts
      let score = path.length * 1.5;
      if (isLeaf) score += 2.0;

      return {
        symbol: sym,
        module: node ? node.module : 'src/comparator.js',
        depth: path.length,
        path,
        isLeaf,
        score
      };
    });

    rankedCandidates.sort((a, b) => b.score - a.score);

    if (rankedCandidates.length > 0) {
      return rankedCandidates[0];
    }

    // Fallback if all callees refuted
    const node = this.substrate.symbolIndex.get(entrySymbol);
    return {
      symbol: entrySymbol,
      module: node ? node.module : 'src/ranges.js',
      depth: 1,
      path: [entrySymbol],
      role: 'fallback'
    };
  }

  recordRefutation(symbol, errorOutput) {
    this.refutedSet.add(symbol);
    this.causalHistory.push({ symbol, error: String(errorOutput).slice(0, 150) });
  }

  generateCausalNarrative(candidate) {
    let narrative = `[LIN Explicit Causal Path Exploration]\n`;
    narrative += `* Active Call Chain: ${candidate.path.join(' -> ')}\n`;
    narrative += `* Frontier Target: '${candidate.symbol}' in '${candidate.module}' (Causal Depth: ${candidate.depth})\n`;
    if (candidate.isLeaf) {
      narrative += `* Target Role: LEAF UTILITY (Root Cause Foundation Node)\n`;
    }
    if (this.refutedSet.size > 0) {
      narrative += `* Refuted Upstream Wrappers: [${Array.from(this.refutedSet).join(', ')}]\n`;
      narrative += `* Causal Inference: Upstream wrappers were refuted. The root-cause bug originates inside leaf dependency '${candidate.symbol}'.\n`;
    }
    return narrative;
  }
}
