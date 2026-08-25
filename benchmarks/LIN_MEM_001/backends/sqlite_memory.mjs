import { DatabaseSync } from "node:sqlite";

export class SqliteMemoryBackend {
  constructor() {
    this.db = new DatabaseSync(":memory:");
    this._initSchema();
    this._prepareStatements();
  }

  _initSchema() {
    this.db.exec(`
      PRAGMA synchronous = OFF;
      PRAGMA journal_mode = MEMORY;

      CREATE TABLE accounts (
        id INTEGER PRIMARY KEY,
        name TEXT,
        tier TEXT,
        limits_json TEXT
      );

      CREATE TABLE policies (
        id INTEGER PRIMARY KEY,
        account_id INTEGER,
        name TEXT,
        rules_json TEXT
      );

      CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        account_id INTEGER,
        policy_id INTEGER,
        username TEXT,
        role TEXT,
        role_level INTEGER,
        status TEXT,
        department TEXT,
        region TEXT
      );

      CREATE TABLE resources (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        account_id INTEGER,
        kind TEXT,
        size_kb INTEGER,
        tags_json TEXT
      );

      CREATE INDEX idx_users_filter ON users(account_id, status, department);
    `);
  }

  _prepareStatements() {
    this.stmtGetAccount = this.db.prepare("SELECT id, name, tier, limits_json FROM accounts WHERE id = ?");
    this.stmtGetPolicy = this.db.prepare("SELECT id, account_id, name, rules_json FROM policies WHERE id = ?");
    this.stmtGetUser = this.db.prepare("SELECT id, account_id, policy_id, username, role, role_level, status, department, region FROM users WHERE id = ?");
    this.stmtGetResource = this.db.prepare("SELECT id, user_id, account_id, kind, size_kb, tags_json FROM resources WHERE id = ?");

    this.stmtFilterUsers = this.db.prepare(
      "SELECT id FROM users WHERE account_id = ? AND status = ? AND department = ? ORDER BY id ASC"
    );

    this.stmtTraverseRule = this.db.prepare(`
      SELECT 
        u.account_id as u_account_id,
        u.role_level as u_role_level,
        u.policy_id as u_policy_id,
        r.account_id as r_account_id,
        r.size_kb as r_size_kb,
        p.rules_json as p_rules_json
      FROM users u
      JOIN resources r ON r.id = ?
      JOIN policies p ON p.id = u.policy_id
      WHERE u.id = ?
    `);
  }

  load(dataset) {
    const insertAccount = this.db.prepare("INSERT INTO accounts (id, name, tier, limits_json) VALUES (?, ?, ?, ?)");
    const insertPolicy = this.db.prepare("INSERT INTO policies (id, account_id, name, rules_json) VALUES (?, ?, ?, ?)");
    const insertUser = this.db.prepare(
      "INSERT INTO users (id, account_id, policy_id, username, role, role_level, status, department, region) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    );
    const insertResource = this.db.prepare(
      "INSERT INTO resources (id, user_id, account_id, kind, size_kb, tags_json) VALUES (?, ?, ?, ?, ?, ?)"
    );

    this.db.exec("BEGIN TRANSACTION;");
    for (const a of dataset.accounts) {
      insertAccount.run(a.id, a.name, a.tier, JSON.stringify(a.limits));
    }
    for (const p of dataset.policies) {
      insertPolicy.run(p.id, p.account_id, p.name, JSON.stringify(p.rules));
    }
    for (const u of dataset.users) {
      insertUser.run(
        u.id,
        u.account_id,
        u.policy_id,
        u.username,
        u.role,
        u.role_level,
        u.status,
        u.metadata.department,
        u.metadata.region
      );
    }
    for (const r of dataset.resources) {
      insertResource.run(r.id, r.user_id, r.account_id, r.kind, r.size_kb, JSON.stringify(r.tags));
    }
    this.db.exec("COMMIT;");
  }

  executeL0(op) {
    let row;
    switch (op.entityType) {
      case "User": {
        row = this.stmtGetUser.get(op.id);
        if (!row) return null;
        return {
          id: row.id,
          account_id: row.account_id,
          policy_id: row.policy_id,
          username: row.username,
          role: row.role,
          role_level: row.role_level,
          status: row.status,
          metadata: { department: row.department, region: row.region }
        };
      }
      case "Resource": {
        row = this.stmtGetResource.get(op.id);
        if (!row) return null;
        return {
          id: row.id,
          user_id: row.user_id,
          account_id: row.account_id,
          kind: row.kind,
          size_kb: row.size_kb,
          tags: JSON.parse(row.tags_json)
        };
      }
      case "Policy": {
        row = this.stmtGetPolicy.get(op.id);
        if (!row) return null;
        return {
          id: row.id,
          account_id: row.account_id,
          name: row.name,
          rules: JSON.parse(row.rules_json)
        };
      }
      case "Account": {
        row = this.stmtGetAccount.get(op.id);
        if (!row) return null;
        return {
          id: row.id,
          name: row.name,
          tier: row.tier,
          limits: JSON.parse(row.limits_json)
        };
      }
      default:
        return null;
    }
  }

  executeL1(op) {
    const a = this.executeL0({ entityType: op.entityType, id: op.idA });
    const b = this.executeL0({ entityType: op.entityType, id: op.idB });
    if (!a || !b) return false;
    return JSON.stringify(a) === JSON.stringify(b);
  }

  executeL2(op) {
    const { account_id, status, department } = op.predicate;
    const rows = this.stmtFilterUsers.all(account_id, status, department);
    return rows.map(r => r.id);
  }

  executeL3(op) {
    const row = this.stmtTraverseRule.get(op.resource_id, op.user_id);
    if (!row) {
      return { allowed: false, reason: "NOT_FOUND" };
    }
    if (row.u_account_id !== row.r_account_id) {
      return { allowed: false, reason: "CROSS_TENANT_FORBIDDEN" };
    }

    const rules = JSON.parse(row.p_rules_json);
    let decision = "DENY";
    for (const rule of rules) {
      if (rule.action === op.action) {
        if (row.u_role_level >= rule.min_role_level && row.r_size_kb <= rule.max_size_kb) {
          decision = rule.effect;
        }
      }
    }

    return {
      allowed: decision === "ALLOW",
      reason: decision === "ALLOW" ? "AUTHORIZED" : "POLICY_REJECTED"
    };
  }

  close() {
    this.db.close();
  }
}
