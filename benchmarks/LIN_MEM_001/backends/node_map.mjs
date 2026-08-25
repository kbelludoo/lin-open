export class NodeMapBackend {
  constructor() {
    this.accounts = new Map();
    this.policies = new Map();
    this.users = new Map();
    this.resources = new Map();
    // Indices for L2
    this.userIndex = new Map(); // key: `${account_id}:${status}:${department}` -> [user_id]
  }

  load(dataset) {
    for (const a of dataset.accounts) {
      this.accounts.set(a.id, a);
    }
    for (const p of dataset.policies) {
      this.policies.set(p.id, p);
    }
    for (const u of dataset.users) {
      this.users.set(u.id, u);
      const key = `${u.account_id}:${u.status}:${u.metadata.department}`;
      if (!this.userIndex.has(key)) {
        this.userIndex.set(key, []);
      }
      this.userIndex.get(key).push(u.id);
    }
    for (const r of dataset.resources) {
      this.resources.set(r.id, r);
    }
  }

  // L0: GET
  executeL0(op) {
    switch (op.entityType) {
      case "User": return this.users.get(op.id) || null;
      case "Resource": return this.resources.get(op.id) || null;
      case "Policy": return this.policies.get(op.id) || null;
      case "Account": return this.accounts.get(op.id) || null;
      default: return null;
    }
  }

  // L1: Structural Equality (naive recursive / JSON comparison)
  executeL1(op) {
    const a = this.executeL0({ entityType: op.entityType, id: op.idA });
    const b = this.executeL0({ entityType: op.entityType, id: op.idB });
    if (!a || !b) return false;
    return JSON.stringify(a) === JSON.stringify(b);
  }

  // L2: Filter
  executeL2(op) {
    const { account_id, status, department } = op.predicate;
    const key = `${account_id}:${status}:${department}`;
    const list = this.userIndex.get(key) || [];
    return [...list].sort((a, b) => a - b);
  }

  // L3: Traverse + Rule Evaluation
  executeL3(op) {
    const user = this.users.get(op.user_id);
    const resource = this.resources.get(op.resource_id);
    if (!user || !resource) {
      return { allowed: false, reason: "NOT_FOUND" };
    }
    if (user.account_id !== resource.account_id) {
      return { allowed: false, reason: "CROSS_TENANT_FORBIDDEN" };
    }
    const policy = this.policies.get(user.policy_id);
    if (!policy) {
      return { allowed: false, reason: "NO_POLICY" };
    }

    let decision = "DENY";
    for (const rule of policy.rules) {
      if (rule.action === op.action) {
        if (user.role_level >= rule.min_role_level && resource.size_kb <= rule.max_size_kb) {
          decision = rule.effect;
        }
      }
    }

    return {
      allowed: decision === "ALLOW",
      reason: decision === "ALLOW" ? "AUTHORIZED" : "POLICY_REJECTED"
    };
  }
}
