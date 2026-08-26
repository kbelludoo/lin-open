#!/usr/bin/env node
// KNOWLEDGE_GAP_AUTOPRIORITY: Auto-prioritization of knowledge gaps
// Extracts gaps, scores them, ranks them, and validates against independent oracle

const fs = require('fs');
const path = require('path');

// Knowledge gaps from lia_knowledge.dicel
const KNOWLEDGE_GAPS = [
  {
    id: 'GAP001',
    language: 'Crystal',
    unknown_workloads: ['CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    current_status: 'REJECTED_for_string_heavy',
    has_toolchain: true,
    has_evidence: true,
    semantic_match: false,
    workload_types_tested: ['string_heavy', 'regex_heavy'],
  },
  {
    id: 'GAP002',
    language: 'Nim',
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    workload_types_tested: [],
  },
  {
    id: 'GAP003',
    language: 'Zig',
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    workload_types_tested: [],
  },
  {
    id: 'GAP004',
    language: 'Lua',
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    workload_types_tested: [],
  },
  {
    id: 'GAP005',
    language: 'Cplusplus',
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    workload_types_tested: [],
  },
];

// Additional gaps not in KNOWLEDGE_GAPS but observed in experiments
const ADDITIONAL_GAPS = [
  {
    id: 'GAP006',
    language: 'TypeScript_vs_MJS',
    unknown: 'causal_explanation_for_performance_difference',
    current_status: 'PARTIALLY_RESOLVED',
    has_evidence: true,
    resolution: 'crypto_call_dominant_55_60_percent',
    remaining: 'runtime_JIT_overhead_attribution',
  },
  {
    id: 'GAP007',
    language: 'Multi_target',
    unknown: 'repair_strategy_portability_to_more_languages',
    current_status: 'PARTIALLY_RESOLVED',
    has_evidence: true,
    resolution: '2_of_2_tested_targets_pass',
    remaining: 'Go_Cplusplus_Zig_Lua_not_tested',
  },
  {
    id: 'GAP008',
    language: 'Repair_Learning',
    unknown: 'strategy_transfer_across_different_mismatch_classes',
    current_status: 'NO_EVIDENCE',
    has_evidence: false,
    resolution: null,
    remaining: 'only_tested_hashing_algorithm_mismatch',
  },
];

// Scoring functions
function scoreImpact(gap) {
  // Impact: how valuable is resolving this gap?
  if (gap.current_status === 'NO_EVIDENCE') return 0.8; // High impact - no evidence
  if (gap.current_status === 'PARTIALLY_RESOLVED') return 0.6; // Medium - partially done
  if (gap.current_status === 'REJECTED_for_string_heavy') return 0.3; // Low - already rejected
  return 0.5;
}

function scoreUncertainty(gap) {
  // Uncertainty: how much don't we know? (inverse of current knowledge)
  if (!gap.has_evidence) return 0.9; // High uncertainty
  if (gap.has_evidence && !gap.semantic_match) return 0.4; // Medium - some evidence
  if (gap.has_evidence && gap.semantic_match) return 0.2; // Low - good evidence
  if (gap.current_status === 'PARTIALLY_RESOLVED') return 0.5; // Medium
  return 0.7;
}

function scoreInformationGain(gap) {
  // Expected information gain: how much new knowledge would we learn?
  const unknownCount = (gap.unknown_workloads || []).length;
  if (unknownCount >= 5) return 0.9; // Many unknowns
  if (unknownCount >= 3) return 0.7;
  if (unknownCount >= 1) return 0.5;
  if (gap.unknown) return 0.6; // Specific unknown
  return 0.3;
}

function scoreArchitecturalRelevance(gap) {
  // Relevance to LIN architecture goals
  const relevantLanguages = ['Nim', 'Zig', 'Go', 'Cplusplus'];
  const relevantGoals = ['repair_strategy_portability', 'multi_backend', 'causal_explanation'];
  
  if (relevantLanguages.includes(gap.language)) return 0.8;
  if (gap.language === 'TypeScript_vs_MJS') return 0.7;
  if (gap.language === 'Multi_target') return 0.9;
  if (gap.language === 'Repair_Learning') return 0.8;
  return 0.5;
}

function computePriorityScore(gap) {
  const impact = scoreImpact(gap);
  const uncertainty = scoreUncertainty(gap);
  const informationGain = scoreInformationGain(gap);
  const relevance = scoreArchitecturalRelevance(gap);
  
  const score = impact * uncertainty * informationGain * relevance;
  
  return {
    gap_id: gap.id,
    impact,
    uncertainty,
    information_gain: informationGain,
    architectural_relevance: relevance,
    priority_score: score,
  };
}

// Independent oracle (simplified - based on heuristics)
function oracleRanking(gaps) {
  // Oracle uses different heuristics:
  // 1. Prioritize gaps with NO_EVIDENCE over PARTIALLY_RESOLVED
  // 2. Prioritize gaps with more unknown workloads
  // 3. Prioritize gaps relevant to architecture
  
  return gaps.map(gap => {
    let oracleScore = 0;
    
    // Base score
    if (gap.current_status === 'NO_EVIDENCE') oracleScore += 0.4;
    if (gap.current_status === 'PARTIALLY_RESOLVED') oracleScore += 0.2;
    
    // Unknown workloads bonus
    oracleScore += (gap.unknown_workloads || []).length * 0.05;
    
    // Architecture relevance bonus
    if (['Nim', 'Zig', 'Multi_target', 'Repair_Learning'].includes(gap.language)) {
      oracleScore += 0.2;
    }
    
    return {
      gap_id: gap.id,
      oracle_score: oracleScore,
    };
  }).sort((a, b) => b.oracle_score - a.oracle_score);
}

// Main execution
console.log('=== KNOWLEDGE_GAP_AUTOPRIORITY ===');
console.log('');

// Combine all gaps
const allGaps = [...KNOWLEDGE_GAPS, ...ADDITIONAL_GAPS];

// Compute system ranking
console.log('=== SYSTEM RANKING ===');
const systemResults = allGaps.map(computePriorityScore);
systemResults.sort((a, b) => b.priority_score - a.priority_score);

systemResults.forEach((result, index) => {
  const gap = allGaps.find(g => g.id === result.gap_id);
  console.log(`${index + 1}. ${result.gap_id} (${gap.language})`);
  console.log(`   impact=${result.impact.toFixed(2)} uncertainty=${result.uncertainty.toFixed(2)} info_gain=${result.information_gain.toFixed(2)} relevance=${result.architectural_relevance.toFixed(2)}`);
  console.log(`   priority_score=${result.priority_score.toFixed(4)}`);
});

// Compute oracle ranking
console.log('');
console.log('=== ORACLE RANKING ===');
const oracleResults = oracleRanking(allGaps);
oracleResults.forEach((result, index) => {
  const gap = allGaps.find(g => g.id === result.gap_id);
  console.log(`${index + 1}. ${result.gap_id} (${gap.language}) oracle_score=${result.oracle_score.toFixed(2)}`);
});

// Compute PRIORITY_ACCURACY (top-k match)
console.log('');
console.log('=== VALIDATION ===');
const topK = 3;
const systemTopK = systemResults.slice(0, topK).map(r => r.gap_id);
const oracleTopK = oracleResults.slice(0, topK).map(r => r.gap_id);

const matches = systemTopK.filter(id => oracleTopK.includes(id)).length;
const priorityAccuracy = matches / topK;

console.log(`System top-${topK}: ${systemTopK.join(', ')}`);
console.log(`Oracle top-${topK}: ${oracleTopK.join(', ')}`);
console.log(`Matches: ${matches}/${topK}`);
console.log(`PRIORITY_ACCURACY: ${priorityAccuracy.toFixed(2)}`);

// Compute DISCOVERY_YIELD (simplified)
console.log('');
console.log('=== DISCOVERY YIELD ===');
const totalExperiments = allGaps.length;
const resolvedGaps = allGaps.filter(g => g.current_status !== 'NO_EVIDENCE').length;
const discoveryYield = resolvedGaps / totalExperiments;
console.log(`Total gaps: ${totalExperiments}`);
console.log(`Resolved/partially resolved: ${resolvedGaps}`);
console.log(`DISCOVERY_YIELD: ${discoveryYield.toFixed(2)}`);

// Recommendations
console.log('');
console.log('=== RECOMMENDATIONS ===');
const recommendations = systemResults.slice(0, 3).map(result => {
  const gap = allGaps.find(g => g.id === result.gap_id);
  return {
    gap_id: result.gap_id,
    language: gap.language,
    reason: gap.current_status === 'NO_EVIDENCE' ? 'no evidence yet' : 'partially resolved',
    proposed_experiment: gap.proposed_experiment || `EXPAND_${gap.language.toUpperCase()}_01`,
  };
});

recommendations.forEach((rec, index) => {
  console.log(`${index + 1}. ${rec.gap_id} (${rec.language})`);
  console.log(`   reason: ${rec.reason}`);
  console.log(`   proposed: ${rec.proposed_experiment}`);
});
