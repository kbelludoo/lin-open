export function renderReport(language, metrics, opts) {
  const lines = []
  lines.push('AIN-LB REPORT')
  lines.push('='.repeat(28))
  lines.push(`Language:        ${language}${opts.mock ? ' (mock)' : ''}`)
  lines.push(`Model:           ${opts.model || '(mock)'}`)
  lines.push(`Attempts:        ${metrics.raw.attempts}`)
  lines.push(`Passing checks:  ${metrics.raw.passing}`)
  lines.push('')
  lines.push(`Tokens:          ${metrics.raw.tokens}`)
  lines.push(`Tokens/task:     ${metrics.raw.tokens_per_task}`)
  lines.push(`Elapsed (ms):    ${metrics.raw.elapsed_ms}`)
  lines.push('')
  lines.push(`Reliability:             ${metrics.raw.reliability}`)
  lines.push(`First-pass success:      ${metrics.raw.first_pass}`)
  lines.push(`Context efficiency:      ${metrics.raw.context_efficiency}`)
  lines.push(`Semantic recovery (T0):  ${metrics.raw.semantic_recovery}`)
  lines.push(`Regression stability:    ${metrics.raw.regression_stability}`)
  lines.push(`Compression ratio:       ${opts.compression ? metrics_compression(opts.compression) : 'n/a'}`)
  lines.push('')
  lines.push(`AI_DEVELOPMENT_SCORE:    ${metrics.composite}`)
  lines.push('='.repeat(28))
  return lines.join('\n')
}

function metrics_compression(c) {
  return c.lin && c.trad ? `${c.lin}/${c.trad} = x${(c.trad / c.lin).toFixed(2)}` : 'n/a'
}

export function saveReport(report, path) {
  // caller handles persistence; here just return for embed
  return report
}
