import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SPEC_PATH = path.join(ROOT, 'spec', 'B6_LOGIC_SPEC_V1.json');

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

function computeInputHash(canonicalText) {
  const prefix = Buffer.from('LIN/B6_INPUT/0.1\0', 'utf8');
  const buf = Buffer.concat([prefix, Buffer.from(canonicalText, 'utf8')]);
  return `sha256:${sha256Hex(buf)}`;
}

function computeResultHash(canonicalText) {
  const prefix = Buffer.from('LIN/B6_RESULT/0.1\0', 'utf8');
  const buf = Buffer.concat([prefix, Buffer.from(canonicalText, 'utf8')]);
  return `sha256:${sha256Hex(buf)}`;
}

function solveB6Oracle(spec) {
  const kb = spec.knowledge_base;

  // Index facts
  const caps = new Set(); // "Agent:Cap"
  const activeContracts = new Set(); // "Agent"
  const trust = []; // { A, B, Level }

  for (const f of kb.facts) {
    if (f.rel === 'has_capability') {
      caps.add(`${f.args[0]}:${f.args[1]}`);
    } else if (f.rel === 'contract_active') {
      activeContracts.add(f.args[0]);
    } else if (f.rel === 'trust_edge') {
      trust.push({ from: f.args[0], to: f.args[1], level: f.args[2] });
    }
  }

  // 1. Direct delegations
  const direct = [];
  for (const edge of trust) {
    if (edge.level >= 3 && activeContracts.has(edge.to)) {
      if (caps.has(`${edge.from}:cap_delegate`)) {
        // Find all capabilities of edge.from
        for (const cap of kb.constants.capabilities) {
          if (caps.has(`${edge.from}:${cap}`)) {
            direct.push({ from: edge.from, to: edge.to, cap });
          }
        }
      }
    }
  }

  // 2. Chain delegations (Transitive closure over cap_delegate)
  const chain = new Set(); // "from:to:cap"
  for (const d of direct) {
    chain.add(`${d.from}:${d.to}:${d.cap}`);
  }

  let changed = true;
  while (changed) {
    changed = false;
    const current = Array.from(chain).map((s) => {
      const parts = s.split(':');
      return { from: parts[0], to: parts[1], cap: parts[2] };
    });

    for (const d of direct) {
      if (d.cap === 'cap_delegate') {
        const intermediate = d.to;
        for (const c of current) {
          if (c.from === intermediate) {
            const key = `${d.from}:${c.to}:${c.cap}`;
            if (!chain.has(key)) {
              chain.add(key);
              changed = true;
            }
          }
        }
      }
    }
  }

  // Extract bindings and sort lexicographically
  const bindings = Array.from(chain).map((s) => {
    const parts = s.split(':');
    return {
      "?Origin": parts[0],
      "?Target": parts[1],
      "?Cap": parts[2],
    };
  }).sort((a, b) => {
    if (a['?Origin'] !== b['?Origin']) return a['?Origin'].localeCompare(b['?Origin']);
    if (a['?Target'] !== b['?Target']) return a['?Target'].localeCompare(b['?Target']);
    return a['?Cap'].localeCompare(b['?Cap']);
  });

  const canonicalResultObj = {
    spec_id: "B6_LOGIC_V1",
    distinct_solutions_count: bindings.length,
    status: "SUCCESS",
    bindings,
  };

  const canonicalResultJson = canonicalizeJson(canonicalResultObj);
  const resultHash = computeResultHash(canonicalResultJson);

  return {
    bindings,
    count: bindings.length,
    canonical_json: canonicalResultJson,
    result_hash: resultHash,
  };
}

const spec = JSON.parse(fs.readFileSync(SPEC_PATH, 'utf8'));
const canonicalInput = canonicalizeJson(spec.knowledge_base);
const inputHash = computeInputHash(canonicalInput);
const oracleRes = solveB6Oracle(spec);

console.log('=== B6_LOGIC_V1 FORMAL SPECIFICATION AUDIT ===');
console.log('B6_INPUT_HASH :', inputHash);
console.log('Distinct Solutions Count:', oracleRes.count);
console.log('B6_RESULT_HASH:', oracleRes.result_hash);
console.log('\nBindings:');
console.log(JSON.stringify(oracleRes.bindings, null, 2));
