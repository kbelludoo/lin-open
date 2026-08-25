/**
 * LIN Target Selector & Multi-Language Evaluator.
 * Evaluates candidate compilation targets across performance, binary size,
 * runtime footprint, token density, and semantic fidelity to choose the optimal target.
 */
import { compileLia } from './multi_emit.mjs';
import { TARGETS } from './emit_shared.mjs';

export const PROFILES = {
  PERFORMANCE: 'performance',   // High-throughput native code (rust, c, go)
  AI_DATA: 'ai_data',           // AI/Data science & math (python, julia)
  WEB_EDGE: 'web_edge',         // Browser, edge, serverless (ts, js, lua)
  ENTERPRISE: 'enterprise',     // JVM & .NET enterprise stacks (java, cs, kotlin, scala)
  FUNCTIONAL: 'functional',     // Concurrency, immutability & reasoning (elixir, haskell, prolog)
  CONFIG_INFRA: 'config_infra', // Infrastructure / DevOps (go, hcl)
  SMALLEST_SIZE: 'smallest_size'// Minimal token and byte footprint
};

/**
 * Score each language based on emitted code metrics and chosen profile.
 */
export function evaluateTargets(liaCode, profile = PROFILES.PERFORMANCE, opts = {}) {
  const evaluations = [];

  for (const target of TARGETS) {
    try {
      const emitResult = compileLia(liaCode, { target, ...opts });
      const code = emitResult.code || '';
      const bytes = Buffer.byteLength(code, 'utf8');
      const lines = code.split('\n').length;
      const tokensEst = Math.ceil(code.length / 4);

      let score = 100;

      // Metric Adjustments based on profile
      if (profile === PROFILES.PERFORMANCE) {
        if (['rust', 'c'].includes(target)) score += 50;
        else if (['go', 'crystal', 'julia'].includes(target)) score += 30;
        else if (['java', 'cs', 'kotlin', 'scala'].includes(target)) score += 15;
      } else if (profile === PROFILES.AI_DATA) {
        if (['python', 'julia'].includes(target)) score += 60;
        else if (['rust', 'c'].includes(target)) score += 20;
      } else if (profile === PROFILES.WEB_EDGE) {
        if (['ts', 'js', 'lua'].includes(target)) score += 60;
        else if (['go', 'rust'].includes(target)) score += 20;
      } else if (profile === PROFILES.ENTERPRISE) {
        if (['java', 'cs', 'kotlin', 'scala'].includes(target)) score += 60;
      } else if (profile === PROFILES.FUNCTIONAL) {
        if (['elixir', 'haskell', 'prolog', 'scala'].includes(target)) score += 60;
      } else if (profile === PROFILES.CONFIG_INFRA) {
        if (['go', 'hcl'].includes(target)) score += 60;
      } else if (profile === PROFILES.SMALLEST_SIZE) {
        score -= (bytes / 50); // Heavily reward smaller byte sizes
      }

      // Penalty for bloated emission
      if (bytes > 3000) score -= 15;
      if (bytes < 500) score += 10;

      evaluations.push({
        target,
        score: Math.round(score),
        bytes,
        lines,
        tokensEst,
        lang: emitResult.lang || target,
      });
    } catch (err) {
      evaluations.push({
        target,
        score: -1,
        error: err.message,
      });
    }
  }

  evaluations.sort((a, b) => b.score - a.score);

  return {
    profile,
    recommendedTarget: evaluations[0]?.target || 'ts',
    evaluations,
  };
}
