import fs from "fs";
import path from "path";
import { createPRNG, pick } from "../dataset/generate.mjs";

export function generateWorkload({ dataset, opCount = 10000, seed = 424242 }) {
  const rand = createPRNG(seed);
  const { accounts, policies, users, resources } = dataset;

  // 1. L0: Point Lookups
  const l0Ops = [];
  for (let i = 0; i < opCount; i++) {
    const r = rand();
    if (r < 0.5) {
      const u = users[Math.floor(rand() * users.length)];
      l0Ops.push({ op: "GET", entityType: "User", id: u.id });
    } else if (r < 0.8) {
      const res = resources[Math.floor(rand() * resources.length)];
      l0Ops.push({ op: "GET", entityType: "Resource", id: res.id });
    } else if (r < 0.9) {
      const p = policies[Math.floor(rand() * policies.length)];
      l0Ops.push({ op: "GET", entityType: "Policy", id: p.id });
    } else {
      const a = accounts[Math.floor(rand() * accounts.length)];
      l0Ops.push({ op: "GET", entityType: "Account", id: a.id });
    }
  }

  // 2. L1: Structural Equality Checks
  const l1Ops = [];
  for (let i = 0; i < opCount; i++) {
    const isSame = rand() < 0.5;
    if (isSame) {
      const idx = Math.floor(rand() * users.length);
      l1Ops.push({ op: "EQ", entityType: "User", idA: users[idx].id, idB: users[idx].id });
    } else {
      const idxA = Math.floor(rand() * users.length);
      const idxB = (idxA + 1 + Math.floor(rand() * (users.length - 1))) % users.length;
      l1Ops.push({ op: "EQ", entityType: "User", idA: users[idxA].id, idB: users[idxB].id });
    }
  }

  // 3. L2: Multi-Attribute Filters
  const l2Ops = [];
  const ROLES = ["VIEWER", "EDITOR", "DEVELOPER", "ADMIN", "OWNER"];
  const STATUSES = ["ACTIVE", "INACTIVE", "SUSPENDED", "PENDING_VERIFICATION"];
  const DEPARTMENTS = ["Engineering", "Product", "Sales", "Security", "Finance", "Legal"];
  
  for (let i = 0; i < opCount; i++) {
    const account_id = accounts[Math.floor(rand() * accounts.length)].id;
    const status = pick(STATUSES, rand);
    const department = pick(DEPARTMENTS, rand);
    l2Ops.push({
      op: "FILTER",
      entityType: "User",
      predicate: { account_id, status, department }
    });
  }

  // 4. L3: Relation Traversal + Rule Evaluation
  // User -> Account + User -> Policy -> Evaluate(Resource action & size against Policy rules)
  const l3Ops = [];
  const ACTIONS = ["READ", "WRITE", "DELETE", "ADMINISTER", "EXECUTE"];
  for (let i = 0; i < opCount; i++) {
    const user = users[Math.floor(rand() * users.length)];
    const resource = resources[Math.floor(rand() * resources.length)];
    const action = pick(ACTIONS, rand);
    l3Ops.push({
      op: "TRAVERSE_RULE",
      user_id: user.id,
      resource_id: resource.id,
      action
    });
  }

  return {
    meta: { opCount, seed, generated_at: new Date().toISOString() },
    L0: l0Ops,
    L1: l1Ops,
    L2: l2Ops,
    L3: l3Ops
  };
}

if (process.argv[1] && process.argv[1].endsWith("generate.mjs")) {
  const datasetPath = process.argv[2];
  const opCount = parseInt(process.argv[3] || "10000", 10);
  const seed = parseInt(process.argv[4] || "424242", 10);
  const outPath = process.argv[5] || path.join(path.dirname(process.argv[1]), "workload.json");

  if (!datasetPath) {
    console.error("Usage: node workload/generate.mjs <datasetPath> [opCount] [seed] [outPath]");
    process.exit(1);
  }

  console.log(`Generating workload for dataset ${datasetPath} (ops=${opCount})...`);
  const dataset = JSON.parse(fs.readFileSync(datasetPath, "utf-8"));
  const workload = generateWorkload({ dataset, opCount, seed });
  fs.writeFileSync(outPath, JSON.stringify(workload, null, 2));
  console.log(`Workload written to: ${outPath}`);
}
