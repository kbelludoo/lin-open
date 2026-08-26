/**
 * Benchmark Harness for AIN-LB / CCR-002 v2.0 AI Context Death Benchmark.
 * Compares Groups A1, A2, A3, A4, and B across scenarios CCR-002-A, CCR-002-B, CCR-002-C, and CCR-002-D.
 * A4 is the "just metadata" competitor. ignored_semantic_signal is wired before any 9router run.
 * Mock proves representation, not that real models will comply.
 * Implements N >= 20 statistical runs, anonymous blind evaluation, and run_manifest exports.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MockAgent, PERSONALITIES } from '../benchmarks/ain-lb/mock_agent.mjs';
import { evaluatePatchAnonymous } from '../benchmarks/ain-lb/blind_evaluator.mjs';
import { computeRepoHash } from '../benchmarks/ain-lb/llm_provider.mjs';
import { compileLiaToJs } from '../src/compiler.mjs';
import { getCcr002Signal } from '../src/lin_ccr002_signal_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixturesDir = path.join(root, 'tests', 'ain_lb', 'fixtures', 'ccr002');

const TASKS = [
  { id: 'CCR-002-A', name: 'Security / OAuth', targetModule: 'Auth' },
  { id: 'CCR-002-B', name: 'Optimization / Cache', targetModule: 'Storage' },
  { id: 'CCR-002-C', name: 'Evolution / MFA', targetModule: 'Auth' },
  { id: 'CCR-002-D', name: 'Adversarial Optimization', targetModule: 'Storage' },
];

const GROUPS = [
  { id: 'A1', name: 'Group A1 (Code + README + Tests)', path: path.join(fixturesDir, 'group_a1'), tokens: 12000 },
  { id: 'A2', name: 'Group A2 (Code + JSON Metadata)', path: path.join(fixturesDir, 'group_a2'), tokens: 9500 },
  { id: 'A3', name: 'Group A3 (Code + Human Architecture.md)', path: path.join(fixturesDir, 'group_a3'), tokens: 14000 },
  { id: 'A4', name: 'Group A4 (Code + schema + rules + docs)', path: path.join(fixturesDir, 'group_a4'), tokens: 15500 },
  { id: 'B', name: 'Group B (LIN + .linmeta 4-layer)', path: path.join(fixturesDir, 'group_b'), tokens: 4200 },
];

function assertLinFixtureExports() {
  const expected = {
    auth: ['moduleRef', 'dependencies', 'declaredEffects', 'caps', 'contract', 'semanticHash', 'verify'],
    storage: ['moduleRef', 'dependencies', 'declaredEffects', 'caps', 'contract', 'semanticHash', 'write'],
  };
  for (const [name, exports] of Object.entries(expected)) {
    const file = path.join(fixturesDir, 'group_b', `${name}.lin`);
    const source = fs.readFileSync(file, 'utf8');
    const { program } = compileLiaToJs(source, { exportMode: 'multiple' });
    const actual = new Set(program.exports);
    const missing = exports.filter((exportName) => !actual.has(exportName));
    if (missing.length) {
      throw new Error(`CCR-002 fixture export mismatch: ${name}.lin missing ${missing.join(', ')}`);
    }
  }
}

export function runCcr002BenchmarkV2(opts = {}) {
  assertLinFixtureExports();
  const numRuns = opts.runs || 20;
  const initialSeed = opts.seed || 100;
  const rawResults = [];
  const manifests = [];

  for (let run = 0; run < numRuns; run++) {
    const seed = initialSeed + run * 7;

    for (const personalityKey of Object.keys(PERSONALITIES)) {
      const personality = PERSONALITIES[personalityKey];
      const agent = new MockAgent(personality, seed);

      for (const group of GROUPS) {
        for (const task of TASKS) {
          const repoHash = computeRepoHash({ group: group.id, scenario: task.id, seed });
          const evalRes = agent.evaluateTask(task, group.id, { totalTokens: group.tokens, repoHash });

          // Anonymous Blind Evaluation
          const blindEval = evaluatePatchAnonymous(
            { proposal: evalRes.proposal, repoHash },
            task,
            { group: group.id }
          );

          manifests.push(evalRes.manifest);
          rawResults.push({
            run,
            group: group.id,
            groupName: group.name,
            agent: personality.name,
            taskId: task.id,
            taskName: task.name,
            repoHash,
            ...evalRes,
            ...blindEval,
          });
        }
      }
    }
  }

  // Aggregate composite scores by Group over N runs
  const summary = {};
  for (const g of GROUPS) {
    const gResults = rawResults.filter((r) => r.group === g.id);
    const avgTotalCost = Math.round(gResults.reduce((a, b) => a + b.totalContextCost, 0) / gResults.length);
    const avgUnderstanding = Number((gResults.reduce((a, b) => a + b.understandingRate, 0) / gResults.length).toFixed(2));
    const avgCompliance = Number((gResults.reduce((a, b) => a + b.complianceRate, 0) / gResults.length).toFixed(2));
    const totalWrongAssumptions = gResults.reduce((a, b) => a + b.wrongAssumptions, 0);
    const totalUnsafeAttempts = gResults.reduce((a, b) => a + b.unsafeAttempt, 0);
    const totalIgnoredSignal = gResults.reduce((a, b) => a + b.ignoredSemanticSignal, 0);
    const totalHumanInquiries = gResults.reduce((a, b) => a + b.humanInquiryCount, 0);
    const blindPassCount = gResults.filter((r) => r.blindPass).length;
    const passRate = Number(((blindPassCount / gResults.length) * 100).toFixed(1));
    const avgCognitiveEfficiency = Number((gResults.reduce((a, b) => a + b.cognitiveEfficiency, 0) / gResults.length).toFixed(3));

    summary[g.id] = {
      groupName: g.name,
      avgTotalCost,
      avgUnderstanding,
      avgCompliance,
      totalWrongAssumptions,
      totalUnsafeAttempts,
      totalIgnoredSignal,
      totalHumanInquiries,
      passRate,
      avgCognitiveEfficiency,
    };
  }

  const proto = getCcr002Signal();
  const claimBrake = {
    mockProves: proto.mockProves(),
    mockDoesNotProve: proto.mockDoesNotProve(),
    noMockConclusion: proto.noMockConclusion() === 1,
    thesis: proto.thesisNow(),
    question: proto.questionNow(),
    realPhase: proto.realPhase(),
    modelUnobserved: proto.modelUnobserved() === 1,
  };

  return { rawResults, summary, manifests, claimBrake };
}

function printReportV2(data) {
  console.log('\n==================================================================================================');
  console.log('                 AIN-LB / CCR-002 v2.1: AI CONTEXT DEATH (CLAIM BRAKE)                              ');
  console.log('==================================================================================================\n');

  console.log('| Group | Description                 | Total Cost | Underst % | Compl % | Unsafe Att | Ignored Sig | Human Inq | Pass Rate | Cog Efficiency |');
  console.log('|-------|-----------------------------|------------|-----------|---------|------------|-------------|-----------|-----------|----------------|');

  for (const [gid, s] of Object.entries(data.summary)) {
    console.log(
      `| ${gid.padEnd(5)} | ${s.groupName.slice(0, 27).padEnd(27)} | ${String(s.avgTotalCost).padStart(10)} | ${(s.avgUnderstanding * 100 + '%').padStart(9)} | ${(s.avgCompliance * 100 + '%').padStart(7)} | ${String(s.totalUnsafeAttempts).padStart(10)} | ${String(s.totalIgnoredSignal).padStart(11)} | ${String(s.totalHumanInquiries).padStart(9)} | ${(s.passRate + '%').padStart(9)} | ${String(s.avgCognitiveEfficiency).padStart(14)} |`
    );
  }
  console.log('\nClaim brake: mock proves architecture can represent rules; it does not prove real models will use them.');
  console.log(`Thesis: ${data.claimBrake.thesis}`);
  console.log('\n==================================================================================================\n');
}

if (process.argv[1] && process.argv[1].endsWith('bench_ai_context_death.mjs')) {
  const data = runCcr002BenchmarkV2({ runs: 20 });
  printReportV2(data);
}

// Keep the historical runner export as a real named function.  A direct alias
// is easy to lose when this module is consumed by generated/test runners.
export function runCcr002Benchmark(opts = {}) {
  return runCcr002BenchmarkV2(opts);
}
