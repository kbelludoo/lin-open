/**
 * CLR-001 LIN-side harness.
 * Runs fixtures through `lin agent-ir`. Records ACCEPT/DENIED + causal fields.
 * Does not invent win scores. Does not run Python/Rust agents.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { getClr } from '../../src/lin_ain_lb_clr_load.mjs';
import { validateAgentIr } from '../../src/lin_agent_ir_ingest_load.mjs';
import { contentHash, semanticEquals } from '../../src/content_hash_load.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const bin = path.join(root, 'bin', 'lin.mjs');

function agentIr(filePath) {
  const r = spawnSync(process.execPath, [bin, 'agent-ir', filePath], { encoding: 'utf8', cwd: root });
  let parsed = null;
  try { parsed = JSON.parse(r.stdout || ''); } catch { parsed = null; }
  return {
    fixture: path.relative(root, filePath).replace(/\\/g, '/'),
    exit: r.status,
    status: parsed && parsed.status ? parsed.status : 'PARSE_FAIL',
    ok: parsed ? parsed.ok : 0,
    field: parsed ? parsed.field : '',
    missing: parsed ? parsed.missing : '',
    repairs: parsed ? parsed.repairs : '',
    node: parsed ? parsed.node : '',
    message: parsed ? parsed.message : String(r.stderr || r.stdout || ''),
    module_ref: parsed && parsed.module_ref ? parsed.module_ref : '',
    hash_nucleus: parsed && parsed.hash_nucleus ? parsed.hash_nucleus : '',
    allowed_effects: parsed && parsed.allowed_effects ? parsed.allowed_effects : [],
    constraints: parsed && parsed.constraints ? parsed.constraints : [],
    intent: parsed && parsed.intent ? parsed.intent : '',
  };
}

function listPhase0(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((n) => n.endsWith('.lin')).sort();
}

function discovery(clr) {
  const dir = path.join(root, clr.phase0Dir());
  const files = listPhase0(dir);
  const expected = String(clr.expectedModules()).split('|');
  const stems = files.map((f) => f.replace(/\.lin$/, ''));
  const found = expected.filter((m) => stems.includes(m.toLowerCase()));
  return {
    expected_modules: expected,
    expected_count: clr.expectedCount(),
    files_on_disk: files,
    correct_files: found.length,
    total: expected.length,
    note: 'file_presence_only; not a model win score',
  };
}

function emptyRegistry(clr) {
  const t = clr.emptyReg();
  return {
    run_id: t.run_id || '',
    timestamp: t.timestamp || '',
    model: t.model || '',
    provider: t.provider || '',
    temperature: t.temperature || '',
    seed: t.seed || '',
    input_task_hash: t.input_task_hash || '',
    repo_hash_before: t.repo_hash_before || '',
    repo_hash_after: t.repo_hash_after || '',
    agent_ir_hash: t.agent_ir_hash || '',
    decision: t.decision || '',
    violations: Array.isArray(t.violations) ? t.violations : [],
    repair_attempts: t.repair_attempts || '',
    tokens_input: t.tokens_input || '',
    tokens_output: t.tokens_output || '',
    latency: t.latency || '',
  };
}

function semanticDupCheck(row) {
  if (row.name !== 'semantic_duplicate') return { used: 0 };
  const fx = JSON.parse(fs.readFileSync(path.join(root, row.fixture), 'utf8'));
  const same = semanticEquals(fx.create_fn, fx.existing_fn) ? 1 : 0;
  const namesDiffer = fx.create_fn.name !== fx.existing_fn.name ? 1 : 0;
  return {
    used: 1,
    hash_via: 'EXISTING_semantic_hash',
    hash_impl: 'src/content_hash.lin',
    create_hash: contentHash(fx.create_fn.name, fx.create_fn.params, fx.create_fn.body),
    existing_hash: contentHash(fx.existing_fn.name, fx.existing_fn.params, fx.existing_fn.body),
    same_hash: same,
    names_differ: namesDiffer,
    note: 'semantic_equivalence_not_name_clash',
  };
}

function encodedQuestions(clr) {
  return {
    answered: clr.qAnswered(),
    items: [
      { id: 'Q1', text: clr.q0(), answer: clr.q0Answer() },
      { id: 'Q2', text: clr.q1(), answer: clr.q1Answer() },
      { id: 'Q3', text: clr.q2(), answer: clr.q2Answer() },
    ],
    note: 'encoded_unanswered_until_real_model',
  };
}

function repairLoop(clr, fixtureRel) {
  const ir0 = JSON.parse(fs.readFileSync(path.join(root, fixtureRel), 'utf8'));
  const steps = [];
  let ir = ir0;
  let attempts = 0;
  const max = Number(clr.repairLoopMax()) || 8;
  while (attempts <= max) {
    const got = validateAgentIr(ir);
    const step = {
      attempt: attempts,
      status: got.status,
      field: got.field || '',
      missing: got.missing || '',
      repairs: got.repairs || '',
      node: got.node || '',
      applied: '',
    };
    if (got.status === 'ACCEPT') {
      steps.push(step);
      return {
        case_id: 'C1',
        source: 'mechanical_no_model',
        invented_llm: 0,
        converged: 1,
        repair_loop_length: attempts,
        status: 'ACCEPT',
        steps,
        hash_via: 'EXISTING_semantic_hash',
      };
    }
    if (got.status !== 'DENIED') {
      steps.push(step);
      return {
        case_id: 'C1',
        source: 'mechanical_no_model',
        invented_llm: 0,
        converged: 0,
        repair_loop_length: attempts,
        status: got.status,
        steps,
        hash_via: 'EXISTING_semantic_hash',
      };
    }
    const repair = clr.firstMechRepair(got.repairs);
    if (!repair) {
      steps.push(step);
      return {
        case_id: 'C1',
        source: 'mechanical_no_model',
        invented_llm: 0,
        converged: 0,
        repair_loop_length: attempts,
        status: 'DENIED',
        reason: 'no_mechanical_repair',
        steps,
        hash_via: 'EXISTING_semantic_hash',
      };
    }
    ir = clr.applyMechRepair(ir, repair);
    step.applied = repair;
    steps.push(step);
    attempts += 1;
  }
  return {
    case_id: 'C1',
    source: 'mechanical_no_model',
    invented_llm: 0,
    converged: 0,
    repair_loop_length: attempts,
    status: 'MAX',
    steps,
    hash_via: 'EXISTING_semantic_hash',
  };
}

function runCases(clr) {
  const rows = [];
  const n = clr.caseCount();
  for (let i = 0; i < n; i++) {
    const spec = clr.caseAt(i);
    const got = agentIr(path.join(root, spec.fixture));
    const row = {
      id: spec.id,
      name: spec.name,
      expect: spec.expect,
      causal: spec.causal,
      expect_node: spec.node,
      fixture: got.fixture,
      status: got.status,
      field: got.field,
      missing: got.missing,
      repairs: got.repairs,
      node: got.node,
      message: got.message,
      module_ref: got.module_ref,
      hash_nucleus: got.hash_nucleus,
      intent: got.intent,
    };
    if (spec.name === 'semantic_duplicate') row.semantic_hash = semanticDupCheck(row);
    rows.push(row);
  }
  return rows;
}

function casesHold(rows) {
  return rows.every((r) => {
    if (r.name === 'dependency_confusion') return r.status === 'DENIED' || r.status === 'REJECT';
    return r.status === r.expect;
  }) ? 1 : 0;
}

function compressionFields(rows, leftover) {
  const present = [];
  if (rows.some((r) => r.module_ref)) present.push('module_ref');
  if (rows.some((r) => r.hash_nucleus === 'EXISTING_semantic_hash') || leftover.hash_nucleus === 'EXISTING_semantic_hash') {
    present.push('semantic_hash');
  }
  if (rows.some((r) => (r.allowed_effects || []).length)) present.push('effects');
  if (leftover.contracts && leftover.contracts.length) present.push('contracts');
  if (rows.some((r) => r.intent)) present.push('agent_ir');
  return {
    keep_spec: 'module_ref|semantic_hash|effects|contracts|agent_ir',
    present,
    hash_nucleus: 'EXISTING_semantic_hash',
    redefine: 0,
    note: 'field_presence_after_wipe; not a compression ratio',
  };
}

export function runClr001() {
  const clr = getClr();
  const leftoverPath = path.join(root, clr.wipeDir(), 'leftover_contracts.json');
  const leftover = JSON.parse(fs.readFileSync(leftoverPath, 'utf8'));
  const accept = agentIr(path.join(root, clr.acceptFixture()));
  const deny = agentIr(path.join(root, clr.denyFixture()));
  const oldCommit = agentIr(path.join(root, clr.advDir(), 'old_commit.json'));
  const broken = agentIr(path.join(root, clr.advDir(), 'broken_new_commit.json'));
  const repair = agentIr(path.join(root, clr.advDir(), 'repair_via_ir.json'));
  const ingest = [accept, deny];
  const adversarial = [oldCommit, broken, repair];
  const cases = runCases(clr);
  const hypHolds = accept.status === 'ACCEPT' && deny.status === 'DENIED';
  return {
    id: clr.clrId(),
    name: clr.clrName(),
    side: clr.side(),
    invent_score: clr.inventScore(),
    fake_agents: clr.fakeAgents(),
    fake_curve: clr.fakeCurve(),
    redefine_hash: clr.redefineHash(),
    hash_nucleus: clr.hashNucleus(),
    wire_existing: { spec: clr.ainLbSpec(), harness: clr.ainLbHarness() },
    cli: clr.cli(),
    phase0: discovery(clr),
    phase1_wipe: {
      chat_memory: leftover.chat_memory,
      remaining: leftover.survives_wipe,
      new_request: leftover.new_request,
    },
    ingest,
    cases,
    five_cases_hold: casesHold(cases),
    c4_tests: clr.c4Tests(),
    key_metric: clr.keyMetric(),
    key_metric_path: clr.keyMetricPath(),
    repair_loop: repairLoop(clr, clr.case0().fixture),
    questions: encodedQuestions(clr),
    registry_fields: String(clr.regFields()).split('|'),
    registry_template: emptyRegistry(clr),
    real_model_round: clr.realModelRound(),
    ninerouter_block: clr.ninerouterBlock(),
    deep_m006: clr.deepM006(),
    hash_via: clr.hashVia(),
    hash_impl: clr.hashImpl(),
    adversarial: {
      protocol: clr.advReset(),
      runs: adversarial,
    },
    compression: compressionFields([...ingest, ...adversarial, ...cases], leftover),
    window_curve: { spec: clr.windowSpec(), measured: clr.windowMeasured() },
    hypothesis: clr.hyp(),
    falsify_if: clr.falsifyIf(),
    hypothesis_holds_on_lin_gate: hypHolds ? 1 : 0,
  };
}

function main() {
  const report = runClr001();
  const text = JSON.stringify(report, null, 2);
  if (text.includes('AI_DEVELOPMENT_SCORE') || /85\s*%/.test(text) || /35\s*%/.test(text)) {
    throw new Error('runner must not invent win scores');
  }
  const t = report.registry_template;
  if (t.model || t.provider || t.decision || t.run_id || t.tokens_input || t.agent_ir_hash) {
    throw new Error('registry template must stay empty until a real model key exists');
  }
  if (report.questions.answered !== 0) {
    throw new Error('CLR questions must stay unanswered until a real model runs');
  }
  if (report.repair_loop.invented_llm !== 0) {
    throw new Error('repair loop must not invent LLM output');
  }
  console.log(text);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
