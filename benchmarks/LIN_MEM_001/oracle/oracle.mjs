import fs from "fs";

export class GoldenOracle {
  constructor(dataset) {
    this.accounts = new Map(dataset.accounts.map(a => [a.id, JSON.parse(JSON.stringify(a))]));
    this.policies = new Map(dataset.policies.map(p => [p.id, JSON.parse(JSON.stringify(p))]));
    this.users = new Map(dataset.users.map(u => [u.id, JSON.parse(JSON.stringify(u))]));
    this.resources = new Map(dataset.resources.map(r => [r.id, JSON.parse(JSON.stringify(r))]));
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

  // L1: Structural Equality
  executeL1(op) {
    const a = this.executeL0({ entityType: op.entityType, id: op.idA });
    const b = this.executeL0({ entityType: op.entityType, id: op.idB });
    if (!a || !b) return false;
    return JSON.stringify(a) === JSON.stringify(b);
  }

  // L2: Filter
  executeL2(op) {
    const { account_id, status, department } = op.predicate;
    const matches = [];
    for (const u of this.users.values()) {
      if (u.account_id === account_id && u.status === status && u.metadata.department === department) {
        matches.push(u.id);
      }
    }
    matches.sort((a, b) => a - b);
    return matches;
  }

  // L3: Traverse + Rule Evaluation
  executeL3(op) {
    const user = this.users.get(op.user_id);
    const resource = this.resources.get(op.resource_id);
    if (!user || !resource) {
      return { allowed: false, reason: "NOT_FOUND" };
    }

    // Traversal check: Does user belong to same account as resource?
    if (user.account_id !== resource.account_id) {
      return { allowed: false, reason: "CROSS_TENANT_FORBIDDEN" };
    }

    const policy = this.policies.get(user.policy_id);
    if (!policy) {
      return { allowed: false, reason: "NO_POLICY" };
    }

    // Evaluate rules
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

  runAll(workload) {
    const l0Results = workload.L0.map(op => this.executeL0(op));
    const l1Results = workload.L1.map(op => this.executeL1(op));
    const l2Results = workload.L2.map(op => this.executeL2(op));
    const l3Results = workload.L3.map(op => this.executeL3(op));

    return {
      L0: l0Results,
      L1: l1Results,
      L2: l2Results,
      L3: l3Results
    };
  }
}
