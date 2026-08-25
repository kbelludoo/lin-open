import fs from "fs";
import path from "path";

// Deterministic PRNG: Mulberry32
export function createPRNG(seed = 424242) {
  let s = seed >>> 0;
  return function next() {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function pick(arr, rand) {
  return arr[Math.floor(rand() * arr.length)];
}

const TIERS = ["FREE", "STARTER", "PRO", "ENTERPRISE"];
const FEATURES_POOL = ["sso", "audit_logs", "custom_domain", "unlimited_backups", "api_access", "sla_999"];
const ROLES = [
  { name: "VIEWER", level: 1 },
  { name: "EDITOR", level: 2 },
  { name: "DEVELOPER", level: 3 },
  { name: "ADMIN", level: 4 },
  { name: "OWNER", level: 5 }
];
const STATUSES = ["ACTIVE", "INACTIVE", "SUSPENDED", "PENDING_VERIFICATION"];
const DEPARTMENTS = ["Engineering", "Product", "Sales", "Security", "Finance", "Legal"];
const REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "sa-east-1"];
const RESOURCE_KINDS = ["DATABASE", "BUCKET", "COMPUTE_INSTANCE", "QUEUE", "SECRET"];
const ACTIONS = ["READ", "WRITE", "DELETE", "ADMINISTER", "EXECUTE"];

export function generateDataset({ scale = 10000, regime = "shared", seed = 424242 }) {
  const rand = createPRNG(seed);
  
  const numAccounts = regime === "shared" ? 10 : Math.max(10, Math.floor(scale * 0.05));
  const numPolicies = regime === "shared" ? 8 : Math.max(8, Math.floor(scale * 0.05));
  const numUsers = Math.floor(scale * 0.40);
  const numResources = scale - numAccounts - numPolicies - numUsers;

  const accounts = [];
  for (let i = 0; i < numAccounts; i++) {
    const tier = regime === "shared" ? TIERS[i % TIERS.length] : pick(TIERS, rand);
    accounts.push({
      id: i + 1,
      name: `Account_${i + 1}`,
      tier,
      limits: {
        max_users: regime === "shared" ? (i + 1) * 100 : Math.floor(rand() * 1000) + 10,
        max_storage_mb: regime === "shared" ? (i + 1) * 10240 : Math.floor(rand() * 100000) + 1024,
        features: regime === "shared" 
          ? FEATURES_POOL.slice(0, (i % FEATURES_POOL.length) + 1)
          : [pick(FEATURES_POOL, rand), pick(FEATURES_POOL, rand)]
      }
    });
  }

  const policies = [];
  for (let i = 0; i < numPolicies; i++) {
    const account_id = (i % numAccounts) + 1;
    const rules = [];
    const numRules = regime === "shared" ? 3 : Math.floor(rand() * 4) + 1;
    for (let r = 0; r < numRules; r++) {
      rules.push({
        action: regime === "shared" ? ACTIONS[r % ACTIONS.length] : pick(ACTIONS, rand),
        effect: r % 2 === 0 ? "ALLOW" : "DENY",
        min_role_level: (r % 5) + 1,
        max_size_kb: regime === "shared" ? (r + 1) * 50000 : Math.floor(rand() * 100000) + 1000
      });
    }
    policies.push({
      id: i + 1,
      account_id,
      name: `Policy_${i + 1}`,
      rules
    });
  }

  const users = [];
  for (let i = 0; i < numUsers; i++) {
    const account_id = (i % numAccounts) + 1;
    const policy_id = (i % numPolicies) + 1;
    const roleObj = regime === "shared" ? ROLES[i % ROLES.length] : pick(ROLES, rand);
    users.push({
      id: i + 1,
      account_id,
      policy_id,
      username: `user_${i + 1}`,
      role: roleObj.name,
      role_level: roleObj.level,
      status: regime === "shared" ? STATUSES[i % STATUSES.length] : pick(STATUSES, rand),
      metadata: {
        department: regime === "shared" ? DEPARTMENTS[i % DEPARTMENTS.length] : pick(DEPARTMENTS, rand),
        region: regime === "shared" ? REGIONS[i % REGIONS.length] : pick(REGIONS, rand)
      }
    });
  }

  const resources = [];
  for (let i = 0; i < numResources; i++) {
    const user_id = (i % numUsers) + 1;
    const user = users[user_id - 1];
    resources.push({
      id: i + 1,
      user_id,
      account_id: user.account_id,
      kind: regime === "shared" ? RESOURCE_KINDS[i % RESOURCE_KINDS.length] : pick(RESOURCE_KINDS, rand),
      size_kb: regime === "shared" ? ((i % 100) + 1) * 1024 : Math.floor(rand() * 50000) + 10,
      tags: regime === "shared" ? ["env:prod", "team:core"] : [`tag_${Math.floor(rand() * 500)}`, "env:prod"]
    });
  }

  return {
    meta: { scale, regime, seed, generated_at: new Date().toISOString() },
    accounts,
    policies,
    users,
    resources
  };
}

if (process.argv[1] && process.argv[1].endsWith("generate.mjs")) {
  const scale = parseInt(process.argv[2] || "10000", 10);
  const regime = process.argv[3] || "shared";
  const seed = parseInt(process.argv[4] || "424242", 10);
  const outPath = process.argv[5] || path.join(path.dirname(process.argv[1]), `dataset_${scale}_${regime}.json`);
  
  console.log(`Generating dataset: scale=${scale}, regime=${regime}, seed=${seed}...`);
  const data = generateDataset({ scale, regime, seed });
  fs.writeFileSync(outPath, JSON.stringify(data, null, 2));
  console.log(`Dataset written to: ${outPath} (${(fs.statSync(outPath).size / 1024 / 1024).toFixed(2)} MB)`);
}
