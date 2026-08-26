#!/usr/bin/env node
// KNOWLEDGE_GAP_AUTOPRIORITY_V2: Learning prioritizer
// Learns from its own prioritization mistakes by updating weights

const fs = require('fs');
const path = require('path');

// Knowledge gaps
const KNOWLEDGE_GAPS = [
  {
    id: 'GAP001',
    language: 'Crystal',
    current_status: 'REJECTED_for_string_heavy',
    has_toolchain: true,
    has_evidence: true,
    semantic_match: false,
    unknown_workloads: ['CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    oracle_value: 0.20,
  },
  {
    id: 'GAP002',
    language: 'Nim',
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    oracle_value: 0.90,
  },
  {
    id: 'GAP003',
    language: 'Zig',
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    oracle_value: 0.90,
  },
  {
    id: 'GAP004',
    language: 'Lua',
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    oracle_value: 0.75,  // Higher than C++ - easier to install, simpler semantics
  },
  {
    id: 'GAP005',
    language: 'Cplusplus',
    current_status: 'NO_EVIDENCE',
    has_toolchain: false,
    has_evidence: false,
    semantic_match: null,
    unknown_workloads: ['string_heavy', 'regex_heavy', 'CPU_bound', 'graph_heavy', 'numerical', 'embedding'],
    oracle_value: 0.65,  // Lower than Lua - complex build toolchain
  },
  {
    id: 'GAP006',
    language: 'TypeScript_vs_MJS',
    current_status: 'PARTIALLY_RESOLVED',
    has_evidence: true,
    unknown: 'runtime_JIT_overhead',
    oracle_value: 0.20,
  },
  {
    id: 'GAP007',
    language: 'Multi_target',
    current_status: 'PARTIALLY_RESOLVED',
    has_evidence: true,
    unknown: 'Go_Cplusplus_Zig_Lua',
    oracle_value: 0.40,
  },
  {
    id: 'GAP008',
    language: 'Repair_Learning',
    current_status: 'NO_EVIDENCE',
    has_evidence: false,
    unknown: 'different_mismatch_classes',
    oracle_value: 0.60,
  },
];

// Initial weights
const INITIAL_WEIGHTS = {
  impact: 0.25,
  uncertainty: 0.25,
  information_gain: 0.25,
  relevance: 0.25,
};

const LEARNING_RATE = 0.1;
const ITERATIONS = 3;
const TOP_K = 3;

// Scoring functions
function scoreImpact(gap) {
  if (gap.current_status === 'NO_EVIDENCE') return 0.8;
  if (gap.current_status === 'PARTIALLY_RESOLVED') return 0.6;
  if (gap.current_status === 'REJECTED_for_string_heavy') return 0.3;
  return 0.5;
}

function scoreUncertainty(gap) {
  if (!gap.has_evidence) return 0.9;
  if (gap.has_evidence && !gap.semantic_match) return 0.4;
  if (gap.has_evidence && gap.semantic_match) return 0.2;
  if (gap.current_status === 'PARTIALLY_RESOLVED') return 0.5;
  return 0.7;
}

function scoreInformationGain(gap) {
  const unknownCount = (gap.unknown_workloads || []).length;
  if (unknownCount >= 5) return 0.9;
  if (unknownCount >= 3) return 0.7;
  if (unknownCount >= 1) return 0.5;
  if (gap.unknown) return 0.6;
  return 0.3;
}

function scoreArchitecturalRelevance(gap) {
  const relevantLanguages = ['Nim', 'Zig', 'Go', 'Cplusplus'];
  if (relevantLanguages.includes(gap.language)) return 0.8;
  if (gap.language === 'TypeScript_vs_MJS') return 0.7;
  if (gap.language === 'Multi_target') return 0.9;
  if (gap.language === 'Repair_Learning') return 0.8;
  return 0.5;
}

// Compute priority with given weights
function computePriority(gap, weights) {
  const impact = scoreImpact(gap);
  const uncertainty = scoreUncertainty(gap);
  const informationGain = scoreInformationGain(gap);
  const relevance = scoreArchitecturalRelevance(gap);
  
  const score = weights.impact * impact +
                weights.uncertainty * uncertainty +
                weights.information_gain * informationGain +
                weights.relevance * relevance;
  
  return { gap_id: gap.id, score, impact, uncertainty, information_gain: informationGain, relevance };
}

// Compute ranking
function computeRanking(gaps, weights) {
  return gaps.map(gap => computePriority(gap, weights))
    .sort((a, b) => b.score - a.score);
}

// Compute accuracy against oracle
function computeAccuracy(ranking, gaps, topK) {
  const systemTopK = ranking.slice(0, topK).map(r => r.gap_id);
  
  // Oracle ranking by oracle_value
  const oracleSorted = [...gaps].sort((a, b) => b.oracle_value - a.oracle_value);
  const oracleTopK = oracleSorted.slice(0, topK).map(g => g.id);
  
  const matches = systemTopK.filter(id => oracleTopK.includes(id)).length;
  return matches / topK;
}

// Update weights based on feedback
function updateWeights(weights, ranking, gaps, topK) {
  const systemTopK = ranking.slice(0, topK).map(r => r.gap_id);
  const oracleSorted = [...gaps].sort((a, b) => b.oracle_value - a.oracle_value);
  const oracleTopK = oracleSorted.slice(0, topK).map(g => g.id);
  
  console.log('  Feedback analysis:');
  console.log('    System top-3:', systemTopK.join(', '));
  console.log('    Oracle top-3:', oracleTopK.join(', '));
  
  // Find gaps that should be higher but aren't
  const underweighted = oracleTopK.filter(id => !systemTopK.includes(id));
  const overweighted = systemTopK.filter(id => !oracleTopK.includes(id));
  
  console.log('    Underweighted (oracle wants higher):', underweighted.join(', ') || 'none');
  console.log('    Overweighted (system ranks too high):', overweighted.join(', ') || 'none');
  
  const newWeights = { ...weights };
  
  // For each pair of underweighted/overweighted, find the dimension that differentiates them
  for (const uwId of underweighted) {
    for (const owId of overweighted) {
      const uwGap = gaps.find(g => g.id === uwId);
      const owGap = gaps.find(g => g.id === owId);
      
      const uwScores = {
        impact: scoreImpact(uwGap),
        uncertainty: scoreUncertainty(uwGap),
        information_gain: scoreInformationGain(uwGap),
        relevance: scoreArchitecturalRelevance(uwGap),
      };
      const owScores = {
        impact: scoreImpact(owGap),
        uncertainty: scoreUncertainty(owGap),
        information_gain: scoreInformationGain(owGap),
        relevance: scoreArchitecturalRelevance(owGap),
      };
      
      // Find dimension where overweighted scores HIGHER than underweighted
      // This is the dimension that's causing the wrong ranking
      let bestDim = null;
      let bestDiff = 0;
      
      for (const dim of Object.keys(uwScores)) {
        const diff = owScores[dim] - uwScores[dim];
        if (diff > bestDiff) {
          bestDiff = diff;
          bestDim = dim;
        }
      }
      
      if (bestDim) {
        // Penalize the dimension where overweighted scores higher
        const penalty = LEARNING_RATE * (1 + bestDiff);
        newWeights[bestDim] -= penalty;
        console.log(`    Penalizing ${bestDim} by ${penalty.toFixed(3)} (${owId} scores ${owScores[bestDim].toFixed(2)} vs ${uwId} scores ${uwScores[bestDim].toFixed(2)})`);
        
        // Boost the dimension where underweighted scores higher
        let boostDim = null;
        let boostDiff = 0;
        for (const dim of Object.keys(uwScores)) {
          const diff = uwScores[dim] - owScores[dim];
          if (diff > boostDiff) {
            boostDiff = diff;
            boostDim = dim;
          }
        }
        if (boostDim) {
          const boost = LEARNING_RATE * (1 + boostDiff);
          newWeights[boostDim] += boost;
          console.log(`    Boosting ${boostDim} by ${boost.toFixed(3)} (${uwId} scores ${uwScores[boostDim].toFixed(2)} vs ${owId} scores ${owScores[boostDim].toFixed(2)})`);
        }
      }
    }
  }
  
  // Normalize weights
  const total = Object.values(newWeights).reduce((s, v) => s + Math.max(0, v), 0);
  for (const key of Object.keys(newWeights)) {
    newWeights[key] = Math.max(0.05, newWeights[key]) / total;
  }
  
  return newWeights;
}

// Compute rank correlation (Spearman's rho simplified)
function computeRankCorrelation(systemRanking, oracleRanking) {
  const n = systemRanking.length;
  let sumSquaredDiff = 0;
  
  for (let i = 0; i < n; i++) {
    const systemRank = i + 1;
    const oracleRank = oracleRanking.indexOf(systemRanking[i]) + 1;
    sumSquaredDiff += Math.pow(systemRank - oracleRank, 2);
  }
  
  // Spearman's rho = 1 - (6 * sumSquaredDiff) / (n * (n^2 - 1))
  const rho = 1 - (6 * sumSquaredDiff) / (n * (n * n - 1));
  return rho;
}

// Main execution
console.log('=== KNOWLEDGE_GAP_AUTOPRIORITY_V2 ===');
console.log('');

let weights = { ...INITIAL_WEIGHTS };
const results = [];

for (let iter = 0; iter < ITERATIONS; iter++) {
  console.log(`=== ITERATION ${iter + 1} ===`);
  console.log('');
  
  // Show current weights
  console.log('Weights:', JSON.stringify(weights, null, 2));
  console.log('');
  
  // Compute ranking
  const ranking = computeRanking(KNOWLEDGE_GAPS, weights);
  
  console.log('Ranking:');
  ranking.forEach((r, i) => {
    console.log(`  ${i + 1}. ${r.gap_id} (${r.score.toFixed(4)})`);
  });
  console.log('');
  
  // Compute accuracy
  const accuracy = computeAccuracy(ranking, KNOWLEDGE_GAPS, TOP_K);
  console.log(`Accuracy (top-${TOP_K}): ${accuracy.toFixed(2)}`);
  
  // Compute rank correlation
  const systemOrder = ranking.map(r => r.gap_id);
  const oracleOrder = [...KNOWLEDGE_GAPS].sort((a, b) => b.oracle_value - a.oracle_value).map(g => g.id);
  const rankCorrelation = computeRankCorrelation(systemOrder, oracleOrder);
  console.log(`Rank correlation (Spearman's rho): ${rankCorrelation.toFixed(4)}`);
  console.log('');
  
  results.push({
    iteration: iter + 1,
    weights: { ...weights },
    ranking: ranking.map(r => r.gap_id),
    accuracy,
    rank_correlation: rankCorrelation,
  });
  
  // Update weights (except on last iteration)
  if (iter < ITERATIONS - 1) {
    const newWeights = updateWeights(weights, ranking, KNOWLEDGE_GAPS, TOP_K);
    console.log('');
    
    // Show weight changes
    console.log('Weight changes:');
    for (const key of Object.keys(newWeights)) {
      const change = newWeights[key] - weights[key];
      if (Math.abs(change) > 0.001) {
        console.log(`  ${key}: ${weights[key].toFixed(3)} → ${newWeights[key].toFixed(3)} (${change > 0 ? '+' : ''}${change.toFixed(3)})`);
      }
    }
    console.log('');
    
    weights = newWeights;
  }
}

// Compute learning metrics
console.log('=== LEARNING METRICS ===');
console.log('');
console.log('Accuracy progression:');
results.forEach(r => {
  console.log(`  Iteration ${r.iteration}: ${r.accuracy.toFixed(2)}`);
});

const accuracyImprovement = results[results.length - 1].accuracy - results[0].accuracy;
const accuracyLearningRate = accuracyImprovement / (ITERATIONS - 1);

console.log('');
console.log('Rank correlation progression:');
results.forEach(r => {
  console.log(`  Iteration ${r.iteration}: ${r.rank_correlation.toFixed(4)}`);
});

const correlationImprovement = results[results.length - 1].rank_correlation - results[0].rank_correlation;
const correlationLearningRate = correlationImprovement / (ITERATIONS - 1);

console.log('');
console.log(`Accuracy improvement: ${accuracyImprovement.toFixed(2)}`);
console.log(`PRIORITY_ACCURACY_LEARNING_RATE: ${accuracyLearningRate.toFixed(4)}`);
console.log('');
console.log(`Rank correlation improvement: ${correlationImprovement.toFixed(4)}`);
console.log(`PRIORITY_CORRELATION_LEARNING_RATE: ${correlationLearningRate.toFixed(4)}`);

// Weight convergence
console.log('');
console.log('=== WEIGHT CONVERGENCE ===');
console.log('');
const weightChanges = [];
for (let i = 1; i < results.length; i++) {
  let totalChange = 0;
  for (const key of Object.keys(results[i].weights)) {
    totalChange += Math.abs(results[i].weights[key] - results[i-1].weights[key]);
  }
  weightChanges.push(totalChange);
}
console.log('Weight changes per iteration:', weightChanges.map(c => c.toFixed(4)).join(', '));
console.log('Converged:', weightChanges[weightChanges.length - 1] < 0.01 ? 'YES' : 'NO');

// Final ranking comparison
console.log('');
console.log('=== FINAL RANKING COMPARISON ===');
console.log('');
console.log('System top-3:', results[results.length - 1].ranking.slice(0, TOP_K).join(', '));

const oracleSorted = [...KNOWLEDGE_GAPS].sort((a, b) => b.oracle_value - a.oracle_value);
console.log('Oracle top-3:', oracleSorted.slice(0, TOP_K).map(g => g.id).join(', '));

const finalMatches = results[results.length - 1].ranking.slice(0, TOP_K)
  .filter(id => oracleSorted.slice(0, TOP_K).map(g => g.id).includes(id)).length;
console.log(`Final accuracy: ${finalMatches}/${TOP_K} = ${(finalMatches / TOP_K).toFixed(2)}`);

console.log('');
console.log('System full ranking:', results[results.length - 1].ranking.join(', '));
const oracleOrder = [...KNOWLEDGE_GAPS].sort((a, b) => b.oracle_value - a.oracle_value).map(g => g.id);
console.log('Oracle full ranking:', oracleOrder.join(', '));
