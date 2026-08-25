// LIN Statistical Significance Engine: Wilson 95% CI & McNemar Paired Test

export class StatisticalEngine {
  // Wilson Score 95% Confidence Interval
  static computeWilsonCI(k, n, z = 1.96) {
    if (n === 0) return { lower: 0, upper: 0, p: 0 };
    const p = k / n;
    const denominator = 1 + (z * z) / n;
    const centerAdjusted = p + (z * z) / (2 * n);
    const rad = z * Math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n);

    const lower = Math.max(0, (centerAdjusted - rad) / denominator);
    const upper = Math.min(1, (centerAdjusted + rad) / denominator);

    return {
      p: Number((p * 100).toFixed(1)),
      lower_ci_95: Number((lower * 100).toFixed(1)),
      upper_ci_95: Number((upper * 100).toFixed(1)),
      formatted: `${(p * 100).toFixed(1)}% [95% CI: ${(lower * 100).toFixed(1)}% – ${(upper * 100).toFixed(1)}%]`
    };
  }

  // McNemar's Paired Exact Test for binary outcomes across two arms
  static computeMcNemarTest(armA_outcomes, armB_outcomes) {
    let b = 0; // Arm A success, Arm B fail
    let c = 0; // Arm A fail, Arm B success
    const n = Math.min(armA_outcomes.length, armB_outcomes.length);

    for (let i = 0; i < n; i++) {
      const a = armA_outcomes[i];
      const d = armB_outcomes[i];
      if (a && !d) b++;
      if (!a && d) c++;
    }

    // Chi-square statistic with continuity correction
    const numerator = Math.max(0, Math.abs(b - c) - 1);
    const chiSquare = (b + c) > 0 ? (numerator * numerator) / (b + c) : 0;

    // Approximate p-value from chi-square (df = 1)
    const pValue = (b + c) > 0 ? Math.exp(-0.5 * chiSquare) : 1.0;

    return {
      discordant_pairs: { b_only_A: b, c_only_B: c },
      chi_square: Number(chiSquare.toFixed(3)),
      p_value: Number(pValue.toFixed(4)),
      is_statistically_significant: pValue < 0.05
    };
  }
}
