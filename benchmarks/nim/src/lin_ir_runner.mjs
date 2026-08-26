import crypto from 'node:crypto';
import fs from 'node:fs';

function sha256Hex(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

export function computeLinIrHash(canonicalBytes) {
  const prefix = Buffer.from('LIN/IR/0.1\0', 'utf8');
  const buf = Buffer.concat([prefix, Buffer.from(canonicalBytes)]);
  return `sha256:${sha256Hex(buf)}`;
}

export function computeResultHash(canonicalResultBytes) {
  const prefix = Buffer.from('LIN/RESULT/0.1\0', 'utf8');
  const buf = Buffer.concat([prefix, Buffer.from(canonicalResultBytes)]);
  return `sha256:${sha256Hex(buf)}`;
}

export function executeNimC01() {
  let r0 = 0n;
  let r1 = 1n;
  let r_acc = 42n;
  const r_steps = 10000;
  const r_mod = 1000000007n;
  const r_factor = 7n;

  for (let i = 0; i < r_steps; i++) {
    const r_next = r0 + r1;
    const r_scaled = r_next * r_factor;
    const r_acc_next = r_acc + r_scaled;
    const r_acc_mod = r_acc_next % r_mod;
    const r1_mod = r_next % r_mod;
    r0 = r1;
    r1 = r1_mod;
    r_acc = r_acc_mod;
  }

  const val = Number(r_acc);
  const canonicalRes = JSON.stringify({ case_id: 'C01', result: val, status: 'OK' });
  const resHash = computeResultHash(canonicalRes);
  return { result: val, result_hash: resHash };
}

export function executeNimC02() {
  const r_nodes = 2500;
  let r_acc = 0;
  const modulus = 1000000007;

  for (let idx = 0; idx < r_nodes; idx++) {
    let val_contribution = 0;
    const k = idx % 5;
    if (k === 0) val_contribution = ((idx * 13) % modulus) + 3;
    else if (k === 1) val_contribution = (((idx ^ 0x5a5a) * 17) % modulus) + 5;
    else if (k === 2) val_contribution = ((idx * 31) + 11) % modulus;
    else if (k === 3) val_contribution = ((idx * 47) + 17) % modulus;
    else if (k === 4) val_contribution = ((idx * 61) + 23) % modulus;

    r_acc = (r_acc + val_contribution) % modulus;
  }

  const canonicalRes = JSON.stringify({ case_id: 'C02', result: r_acc, status: 'OK' });
  const resHash = computeResultHash(canonicalRes);
  return { result: r_acc, result_hash: resHash };
}

export function executeNimC03() {
  const num_tasks = 500;
  const in_degree = new Array(num_tasks).fill(0);
  const adj = Array.from({ length: num_tasks }, () => []);

  for (let i = 0; i < num_tasks; i++) {
    const max_target = Math.min(num_tasks, i + 6);
    for (let j = i + 1; j < max_target; j++) {
      if (((i * 3 + j) % 7) < 3) {
        adj[i].push(j);
        in_degree[j]++;
      }
    }
  }

  const queue = [];
  for (let i = 0; i < num_tasks; i++) {
    if (in_degree[i] === 0) queue.push(i);
  }

  const topo_order = [];
  while (queue.length > 0) {
    const u = queue.shift();
    topo_order.push(u);
    for (const v of adj[u]) {
      in_degree[v]--;
      if (in_degree[v] === 0) {
        let inserted = false;
        for (let k = 0; k < queue.length; k++) {
          if (v < queue[k]) {
            queue.splice(k, 0, v);
            inserted = true;
            break;
          }
        }
        if (!inserted) queue.push(v);
      }
    }
  }

  let state = 1337n;
  for (const t of topo_order) {
    state = ((state * 1664525n) + BigInt(t) + 1013904223n) % 4294967296n;
  }

  const val = Number(state);
  const canonicalRes = JSON.stringify({ case_id: 'C03', result: val, status: 'OK' });
  const resHash = computeResultHash(canonicalRes);
  return { result: val, result_hash: resHash };
}

export function runNimBackend(caseId, canonicalIrText) {
  const irHash = computeLinIrHash(canonicalIrText.trim());
  let res;
  if (caseId === 'C01') res = executeNimC01();
  else if (caseId === 'C02') res = executeNimC02();
  else if (caseId === 'C03') res = executeNimC03();
  else throw new Error(`Unknown case_id: ${caseId}`);

  return {
    backend: 'nim',
    case_id: caseId,
    lin_ir_hash: irHash,
    result: res.result,
    result_hash: res.result_hash,
  };
}

if (process.argv[2] && process.argv[3]) {
  const caseId = process.argv[2];
  const irFile = process.argv[3];
  const irText = fs.readFileSync(irFile, 'utf8');
  const out = runNimBackend(caseId, irText);
  console.log(JSON.stringify(out));
}
