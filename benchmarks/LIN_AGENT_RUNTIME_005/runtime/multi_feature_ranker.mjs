// LIN Multi-Feature Candidate Scoring Engine

export class MultiFeatureRanker {
  constructor(substrate, historyTracker = new Map()) {
    this.substrate = substrate;
    this.historyTracker = historyTracker; // symbol -> success count
  }

  computeScore({ symbol, module, role, entrySymbol, testErrorOutput, invariants = [] }) {
    // 1. Topological Graph Proximity (0.30)
    let sGraph = 0.50;
    if (role === 'callee') sGraph = 0.95;
    else if (role === 'entry') sGraph = 0.85;
    else if (role === 'leaf') sGraph = 0.70;
    else if (role === 'caller') sGraph = 0.60;

    // 2. Test Error Lexical Matching (0.25)
    let sError = 0.0;
    if (testErrorOutput.includes(symbol)) sError += 0.60;
    if (testErrorOutput.includes(module) || testErrorOutput.includes(module.replace('src/', ''))) sError += 0.40;
    sError = Math.min(1.0, sError);

    // 3. Invariant & Contract Relevance (0.20)
    let sInvariant = 0.50;
    if (invariants.length > 0) sInvariant = 0.85;

    // 4. Historical Success Weight (0.15)
    const histHits = this.historyTracker.get(symbol) || 0;
    const sHistory = Math.min(1.0, 0.40 + (histHits * 0.20));

    // 5. Effect Safety (0.10)
    const node = this.substrate.symbolIndex.get(symbol);
    const sEffect = (node && node.effect === 'Pure') ? 0.90 : 0.60;

    // Multi-feature weighted synthesis
    const finalScore = (
      0.30 * sGraph +
      0.25 * sError +
      0.20 * sInvariant +
      0.15 * sHistory +
      0.10 * sEffect
    );

    return Number(finalScore.toFixed(3));
  }
}
