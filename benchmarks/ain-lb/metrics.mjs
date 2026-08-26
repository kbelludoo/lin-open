const WEIGHTS = { reliability: 0.3, first_pass: 0.2, context_efficiency: 0.2, semantic_recovery: 0.2, regression_stability: 0.1 }

export function computeMetrics(runs, opts) {
  const attempts = runs.length
  const passing = runs.filter((r) => r.check?.ok === true).length
  const firstPassCount = runs.filter((r) => r.check?.ok === true).length
  const tokens = runs.reduce((s, r) => s + (r.tokens || 0), 0)
  const elapsed = runs.reduce((s, r) => s + (r.elapsedMs || 0), 0)

  const reliability = attempts ? passing / attempts : 0
  const first_pass = attempts ? firstPassCount / attempts : 0
  const context_efficiency = tokens ? clamp(1 / (tokens / 1000)) : 0
  const semantic_recovery = opts?.recoveryPass === true ? 1 : 0
  const regression_stability = opts?.regressionStable === true ? 1 : 0

  const raw = {
    attempts,
    passing,
    tokens,
    elapsed_ms: Math.round(elapsed),
    tokens_per_task: attempts ? Math.round(tokens / attempts) : 0,
    reliability: round(reliability),
    first_pass: round(first_pass),
    context_efficiency: round(context_efficiency),
    semantic_recovery: round(semantic_recovery),
    regression_stability: round(regression_stability),
  }

  const composite = WEIGHTS.reliability * reliability
    + WEIGHTS.first_pass * first_pass
    + WEIGHTS.context_efficiency * context_efficiency
    + WEIGHTS.semantic_recovery * semantic_recovery
    + WEIGHTS.regression_stability * regression_stability

  return { raw, composite: round(composite), weights: WEIGHTS }
}

export function modelVariance(runs) {
  const passes = runs.map((r) => (r.check?.ok === true ? 1 : 0))
  const n = passes.length
  if (!n) return { pass_rate: 0, std_dev: 0, median_tokens: 0, attempts: 0 }
  const passRate = passes.reduce((a, b) => a + b, 0) / n
  const variance = passes.reduce((a, b) => a + (b - passRate) ** 2, 0) / n
  const sortedTokens = runs.map((r) => r.tokens || 0).sort((a, b) => a - b)
  const mid = Math.floor(sortedTokens.length / 2)
  const medianTokens = sortedTokens.length % 2
    ? sortedTokens[mid]
    : (sortedTokens[mid - 1] + sortedTokens[mid]) / 2
  return { pass_rate: round(passRate), std_dev: round(Math.sqrt(variance)), median_tokens: medianTokens, attempts: n }
}

export function repairEfficiency(runs) {
  // attempts/tokens/time until first success (LIN: invariant-break -> explicit cause; trad: compiler error -> interpret)
  const ordered = [...runs].sort((a, b) => a.attempt - b.attempt)
  const firstOk = ordered.findIndex((r) => r.check?.ok === true)
  if (firstOk === -1) return { attempts_until_success: runs.length, tokens_until_success: runs.reduce((s, r) => s + (r.tokens || 0), 0), time_ms: runs.reduce((s, r) => s + (r.elapsedMs || 0), 0), succeeded: false }
  const slice = ordered.slice(0, firstOk + 1)
  return {
    attempts_until_success: slice.length,
    tokens_until_success: slice.reduce((s, r) => s + (r.tokens || 0), 0),
    time_ms: slice.reduce((s, r) => s + (r.elapsedMs || 0), 0),
    succeeded: true,
  }
}

export function compressionRatio(linTokens, tradTokens) {
  return tradTokens ? round(tradTokens / linTokens) : 0
}

export function round(n, d = 3) {
  const f = 10 ** d
  return Math.round(n * f) / f
}

export function clamp(n) {
  return Math.max(0, Math.min(1, n))
}
