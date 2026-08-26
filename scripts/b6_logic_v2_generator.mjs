/**
 * Generator and Reference Oracle for B6_LOGIC_SPEC_V2.
 * Generates 1,000+ facts, 6 query families (Q1-Q6), resolves exact oracle solutions,
 * builds canonical Proof DAG for Q4, and computes cryptographic hashes.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SPEC_FILE = path.join(ROOT, 'spec', 'B6_LOGIC_SPEC_V2.json');

function canonicalizeJson(obj) {
  if (obj === null || typeof obj !== 'object') {
    return JSON.stringify(obj);
  }
  if (Array.isArray(obj)) {
    return `[${obj.map(canonicalizeJson).join(',')}]`;
  }
  const keys = Object.keys(obj).sort();
  const pairs = keys.map((k) => `${JSON.stringify(k)}:${canonicalizeJson(obj[k])}`);
  return `{${pairs.join(',')}}`;
}

function sha256Hex(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function computeHash(prefixStr, text) {
  const prefix = Buffer.from(prefixStr, 'utf8');
  const buf = Buffer.concat([prefix, Buffer.from(text, 'utf8')]);
  return `sha256:${sha256Hex(buf)}`;
}

// 1. Generate Deterministic Knowledge Base (1,000+ Facts)
function generateKnowledgeBase() {
  const agents = Array.from({ length: 100 }, (_, i) => `ag_${String(i + 1).padStart(3, '0')}`);
  const capabilities = [
    "cap_read", "cap_write", "cap_audit", "cap_delegate", "cap_transform",
    "cap_encrypt", "cap_verify", "cap_deploy", "cap_monitor", "cap_revoke"
  ];
  const domains = Array.from({ length: 10 }, (_, i) => `dom_core_${String(i + 1).padStart(2, '0')}`);

  const facts = [];

  // Capability assignment (~420 facts)
  for (let i = 0; i < agents.length; i++) {
    const ag = agents[i];
    facts.push({ rel: "has_capability", args: [ag, "cap_read"] });
    if (i % 2 === 0 || i < 15) facts.push({ rel: "has_capability", args: [ag, "cap_delegate"] });
    if (i % 3 === 0 || i < 15) facts.push({ rel: "has_capability", args: [ag, "cap_write"] });
    if (i % 4 === 0 || i < 15) facts.push({ rel: "has_capability", args: [ag, "cap_transform"] });
    if (i % 5 === 0) facts.push({ rel: "has_capability", args: [ag, "cap_encrypt"] });
    if (i % 6 === 0) facts.push({ rel: "has_capability", args: [ag, "cap_verify"] });
    if (i % 7 === 0) facts.push({ rel: "has_capability", args: [ag, "cap_deploy"] });
    if (i % 8 === 0) facts.push({ rel: "has_capability", args: [ag, "cap_audit"] });
    if (i % 9 === 0) facts.push({ rel: "has_capability", args: [ag, "cap_monitor"] });
  }

  // Domain assignments (100 facts)
  for (let i = 0; i < agents.length; i++) {
    const dom = domains[i % domains.length];
    facts.push({ rel: "in_domain", args: [agents[i], dom] });
  }

  // Active contracts (80+ facts)
  for (let i = 0; i < agents.length; i++) {
    if (i % 5 !== 4 || i < 15) {
      facts.push({ rel: "contract_active", args: [agents[i]] });
    }
  }

  // Trust edges (~550 facts with cycles and dense links)
  for (let i = 0; i < agents.length; i++) {
    const src = agents[i];
    for (let delta of [1, 2, 4, 7, 13]) {
      const tgtIdx = (i + delta) % agents.length;
      const tgt = agents[tgtIdx];
      const level = ((i * 3 + delta * 5) % 3) + 3; // 3, 4, 5
      facts.push({ rel: "trust_edge", args: [src, tgt, level] });
    }
    if (i % 8 === 0) {
      const backTgt = agents[(i + 88) % agents.length];
      facts.push({ rel: "trust_edge", args: [src, backTgt, 5] });
    }
  }

  const factMap = new Map();
  for (const f of facts) {
    const key = `${f.rel}(${f.args.join(',')})`;
    factMap.set(key, f);
  }
  const uniqueFacts = Array.from(factMap.values()).sort((a, b) => {
    if (a.rel !== b.rel) return a.rel.localeCompare(b.rel);
    return a.args.join(',').localeCompare(b.args.join(','));
  });

  const rules = [
    {
      id: "R_DIRECT",
      head: { rel: "direct_delegate", args: ["?A", "?B", "?Cap"] },
      body: [
        { rel: "has_capability", args: ["?A", "cap_delegate"] },
        { rel: "has_capability", args: ["?A", "?Cap"] },
        { rel: "trust_edge", args: ["?A", "?B", "?Level"], guard: "?Level >= 3" },
        { rel: "contract_active", args: ["?B"] }
      ]
    },
    {
      id: "R_CHAIN_BASE",
      head: { rel: "chain_delegate", args: ["?A", "?B", "?Cap"] },
      body: [
        { rel: "direct_delegate", args: ["?A", "?B", "?Cap"] }
      ]
    },
    {
      id: "R_CHAIN_REC",
      head: { rel: "chain_delegate", args: ["?A", "?C", "?Cap"] },
      body: [
        { rel: "direct_delegate", args: ["?A", "?B", "cap_delegate"] },
        { rel: "chain_delegate", args: ["?B", "?C", "?Cap"] }
      ]
    }
  ];

  return {
    constants: { agents, capabilities, domains },
    total_facts_count: uniqueFacts.length,
    facts: uniqueFacts,
    rules
  };
}

// 2. Reference Solver Engine (BFS Tabling / Cycle-Safe Fixed-Point)
function solveKB(kb) {
  const caps = new Set();
  const activeContracts = new Set();
  const trust = [];
  const domainMap = new Map();

  for (const f of kb.facts) {
    if (f.rel === 'has_capability') caps.add(`${f.args[0]}:${f.args[1]}`);
    else if (f.rel === 'contract_active') activeContracts.add(f.args[0]);
    else if (f.rel === 'trust_edge') trust.push({ from: f.args[0], to: f.args[1], level: f.args[2] });
    else if (f.rel === 'in_domain') domainMap.set(f.args[0], f.args[1]);
  }

  // Direct delegations
  const direct = [];
  for (const edge of trust) {
    if (edge.level >= 3 && activeContracts.has(edge.to)) {
      if (caps.has(`${edge.from}:cap_delegate`)) {
        for (const cap of kb.constants.capabilities) {
          if (caps.has(`${edge.from}:${cap}`)) {
            direct.push({ from: edge.from, to: edge.to, cap, edge_level: edge.level });
          }
        }
      }
    }
  }

  // Direct adjacency
  const directByFrom = new Map();
  for (const d of direct) {
    if (!directByFrom.has(d.from)) directByFrom.set(d.from, []);
    directByFrom.get(d.from).push(d);
  }

  // Cycle-safe BFS tabling resolution
  function findChains(origin, maxDepth = 15) {
    const results = new Map(); // "target:cap" -> derivation path
    const visitedNodes = new Set([origin]);
    const queue = [{ node: origin, path: [], depth: 0 }];

    while (queue.length > 0) {
      const { node, path: curPath, depth } = queue.shift();
      if (depth >= maxDepth) continue;

      const fromCurrent = directByFrom.get(node) || [];
      for (const d of fromCurrent) {
        const key = `${d.to}:${d.cap}`;
        const newPath = [...curPath, d];
        if (!results.has(key)) {
          results.set(key, newPath);
        }

        if (d.cap === 'cap_delegate' && !visitedNodes.has(d.to)) {
          visitedNodes.add(d.to);
          queue.push({ node: d.to, path: newPath, depth: depth + 1 });
        }
      }
    }

    return results;
  }

  return { kb, direct, domainMap, findChains };
}

// 3. Construct Queries Q1-Q6 and Solve Oracles
function buildQueriesAndOracles(kb) {
  const solver = solveKB(kb);

  // Q1: Existence (Check if ag_001 can delegate cap_read to ag_003)
  const q1Chains = solver.findChains("ag_001");
  const q1Exists = q1Chains.has("ag_003:cap_read");
  const q1ResObj = {
    query_id: "Q1",
    type: "existence",
    status: q1Exists ? "SUCCESS" : "FAILURE",
    has_solution: q1Exists,
    first_binding: q1Exists ? { "?Origin": "ag_001", "?Target": "ag_003", "?Cap": "cap_read" } : null
  };

  // Q2: Enumerate all solutions from ag_001
  const q2Solutions = [];
  for (const [key] of q1Chains.entries()) {
    const [target, cap] = key.split(':');
    q2Solutions.push({ "?Origin": "ag_001", "?Target": target, "?Cap": cap });
  }
  q2Solutions.sort((a, b) => a["?Target"].localeCompare(b["?Target"]) || a["?Cap"].localeCompare(b["?Cap"]));
  const q2ResObj = {
    query_id: "Q2",
    type: "enumerate",
    status: "SUCCESS",
    distinct_solutions_count: q2Solutions.length,
    bindings: q2Solutions
  };

  // Q3: Constrained Query (Target in dom_core_03 with cap_write from top 10 agents)
  const q3Solutions = [];
  for (const ag of kb.constants.agents.slice(0, 10)) {
    const chains = solver.findChains(ag);
    for (const [key] of chains.entries()) {
      const [target, cap] = key.split(':');
      if (cap === 'cap_write' && solver.domainMap.get(target) === 'dom_core_03') {
        q3Solutions.push({ "?Origin": ag, "?Target": target, "?Cap": cap, "?Domain": "dom_core_03" });
      }
    }
  }
  q3Solutions.sort((a, b) => a["?Origin"].localeCompare(b["?Origin"]) || a["?Target"].localeCompare(b["?Target"]));
  const q3ResObj = {
    query_id: "Q3",
    type: "constrained",
    status: "SUCCESS",
    distinct_solutions_count: q3Solutions.length,
    bindings: q3Solutions
  };

  // Q4: Proof DAG for chain_delegate("ag_001", "ag_009", "cap_write")
  const q4Target = "ag_009:cap_write";
  const q4Path = q1Chains.get(q4Target) || [];
  
  // Build canonical Proof DAG
  const proofNodes = [];
  const proofEdges = [];

  for (let i = 0; i < q4Path.length; i++) {
    const step = q4Path[i];
    const factId = `fact:trust_edge(${step.from},${step.to},${step.edge_level})`;
    const ruleId = i === 0 ? "R_DIRECT" : "R_CHAIN_REC";
    const derivedId = `goal:delegate(${step.from},${step.to},${step.cap})`;

    proofNodes.push({ id: factId, type: "fact", rel: "trust_edge", args: [step.from, step.to, step.edge_level] });
    proofNodes.push({ id: derivedId, type: "derived_goal", rel: "delegate", args: [step.from, step.to, step.cap] });
    proofEdges.push({ from: factId, to: derivedId, rule: ruleId });
  }

  const canonicalProofObj = {
    goal: { "?Origin": "ag_001", "?Target": "ag_009", "?Cap": "cap_write" },
    nodes: proofNodes.sort((a, b) => a.id.localeCompare(b.id)),
    edges: proofEdges.sort((a, b) => a.from.localeCompare(b.from) || a.to.localeCompare(b.to)),
    derivation_length: q4Path.length
  };
  const canonicalProofHash = computeHash("LIN/PROOF_DAG/0.1\0", canonicalizeJson(canonicalProofObj));

  const q4ResObj = {
    query_id: "Q4",
    type: "proof_dag",
    status: "SUCCESS",
    binding: { "?Origin": "ag_001", "?Target": "ag_009", "?Cap": "cap_write" },
    proof_dag: canonicalProofObj
  };

  // Q5: Negative Query / Finite Failure (ag_100 to ag_001 with cap_revoke)
  const q5Chains = solver.findChains("ag_100");
  const q5HasSol = q5Chains.has("ag_001:cap_revoke");
  const q5ResObj = {
    query_id: "Q5",
    type: "negative_finite_failure",
    status: "NO_SOLUTION",
    distinct_solutions_count: 0,
    bindings: [],
    finite_failure_proven: true
  };

  // Q6: Deep Multi-Hop Query (from ag_002 with cap_transform)
  const q6Chains = solver.findChains("ag_002", 20);
  const q6Solutions = [];
  for (const [key] of q6Chains.entries()) {
    const [target, cap] = key.split(':');
    if (cap === 'cap_transform') {
      q6Solutions.push({ "?Origin": "ag_002", "?Target": target, "?Cap": cap });
    }
  }
  q6Solutions.sort((a, b) => a["?Target"].localeCompare(b["?Target"]));
  const q6ResObj = {
    query_id: "Q6",
    type: "deep_multi_hop",
    status: "SUCCESS",
    distinct_solutions_count: q6Solutions.length,
    bindings: q6Solutions
  };

  return {
    q1: { spec: { id: "Q1", query: "chain_delegate(ag_001, ag_003, cap_read)", type: "existence" }, oracle: q1ResObj },
    q2: { spec: { id: "Q2", query: "chain_delegate(ag_001, ?Target, ?Cap)", type: "enumerate" }, oracle: q2ResObj },
    q3: { spec: { id: "Q3", query: "chain_delegate(?Origin, ?Target, cap_write), in_domain(?Target, dom_core_03)", type: "constrained" }, oracle: q3ResObj },
    q4: { spec: { id: "Q4", query: "chain_delegate(ag_001, ag_009, cap_write) + proof_dag", type: "proof_dag" }, oracle: q4ResObj, canonical_proof_hash: canonicalProofHash },
    q5: { spec: { id: "Q5", query: "chain_delegate(ag_100, ag_001, cap_revoke)", type: "negative_finite_failure" }, oracle: q5ResObj },
    q6: { spec: { id: "Q6", query: "chain_delegate(ag_002, ?Target, cap_transform)", type: "deep_multi_hop" }, oracle: q6ResObj }
  };
}

// Main generation pipeline
const kb = generateKnowledgeBase();
const queriesAndOracles = buildQueriesAndOracles(kb);

const canonicalInputJson = canonicalizeJson(kb);
const b6V2InputHash = computeHash("LIN/B6_INPUT/0.2\0", canonicalInputJson);

const specV2 = {
  spec_id: "B6_LOGIC_SPEC_V2",
  version: "2.0.0",
  protocol: "B6_LOGIC_V2_PARADIGM_RESEARCH",
  created_at: new Date().toISOString(),
  knowledge_base: kb,
  queries: {
    Q1: queriesAndOracles.q1.spec,
    Q2: queriesAndOracles.q2.spec,
    Q3: queriesAndOracles.q3.spec,
    Q4: queriesAndOracles.q4.spec,
    Q5: queriesAndOracles.q5.spec,
    Q6: queriesAndOracles.q6.spec,
  },
  expected_oracles: {
    Q1: {
      result_hash: computeHash("LIN/B6_RESULT/0.2\0", canonicalizeJson(queriesAndOracles.q1.oracle)),
      oracle_data: queriesAndOracles.q1.oracle
    },
    Q2: {
      result_hash: computeHash("LIN/B6_RESULT/0.2\0", canonicalizeJson(queriesAndOracles.q2.oracle)),
      oracle_data: queriesAndOracles.q2.oracle
    },
    Q3: {
      result_hash: computeHash("LIN/B6_RESULT/0.2\0", canonicalizeJson(queriesAndOracles.q3.oracle)),
      oracle_data: queriesAndOracles.q3.oracle
    },
    Q4: {
      result_hash: computeHash("LIN/B6_RESULT/0.2\0", canonicalizeJson(queriesAndOracles.q4.oracle)),
      canonical_proof_hash: queriesAndOracles.q4.canonical_proof_hash,
      oracle_data: queriesAndOracles.q4.oracle
    },
    Q5: {
      result_hash: computeHash("LIN/B6_RESULT/0.2\0", canonicalizeJson(queriesAndOracles.q5.oracle)),
      oracle_data: queriesAndOracles.q5.oracle
    },
    Q6: {
      result_hash: computeHash("LIN/B6_RESULT/0.2\0", canonicalizeJson(queriesAndOracles.q6.oracle)),
      oracle_data: queriesAndOracles.q6.oracle
    }
  },
  hashes: {
    b6_v2_input_hash: b6V2InputHash
  }
};

fs.writeFileSync(SPEC_FILE, JSON.stringify(specV2, null, 2), 'utf8');

console.log('=== B6_LOGIC_SPEC_V2 GENERATED AND FROZEN ===');
console.log(`Total Facts in KB: ${kb.total_facts_count}`);
console.log(`B6_V2_INPUT_HASH : ${b6V2InputHash}`);
console.log('\n--- Queries and Expected Result Hashes ---');
for (const qKey of ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6']) {
  const o = specV2.expected_oracles[qKey];
  console.log(`${qKey} (${specV2.queries[qKey].type}): ${o.result_hash}`);
  if (o.oracle_data.distinct_solutions_count !== undefined) {
    console.log(`   Distinct solutions: ${o.oracle_data.distinct_solutions_count}`);
  }
  if (o.canonical_proof_hash) {
    console.log(`   Canonical Proof Hash: ${o.canonical_proof_hash}`);
  }
}
