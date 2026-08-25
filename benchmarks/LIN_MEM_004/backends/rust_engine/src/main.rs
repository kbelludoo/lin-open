use std::alloc::{GlobalAlloc, Layout, System};
use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;
use serde::{Deserialize, Serialize};

// --- TRACKING ALLOCATOR FOR EXACT HEAP SIZING ---
struct TrackingAllocator;
static ALLOCATED: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for TrackingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ret = System.alloc(layout);
        if !ret.is_null() {
            ALLOCATED.fetch_add(layout.size(), Ordering::Relaxed);
        }
        ret
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        ALLOCATED.fetch_sub(layout.size(), Ordering::Relaxed);
        System.dealloc(ptr, layout);
    }
}

#[global_allocator]
static A: TrackingAllocator = TrackingAllocator;

pub fn get_heap_bytes() -> usize {
    ALLOCATED.load(Ordering::Relaxed)
}

// --- DATASET & WORKLOAD SCHEMAS ---

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct AccountLimits {
    pub max_users: u32,
    pub max_storage_mb: u64,
    pub features: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct Account {
    pub id: u64,
    pub name: String,
    pub tier: String,
    pub limits: AccountLimits,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct PolicyRule {
    pub action: String,
    pub effect: String,
    pub min_role_level: u32,
    pub max_size_kb: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct Policy {
    pub id: u64,
    pub account_id: u64,
    pub name: String,
    pub rules: Vec<PolicyRule>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct UserMetadata {
    pub department: String,
    pub region: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct User {
    pub id: u64,
    pub account_id: u64,
    pub policy_id: u64,
    pub username: String,
    pub role: String,
    pub role_level: u32,
    pub status: String,
    pub metadata: UserMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct Resource {
    pub id: u64,
    pub user_id: u64,
    pub account_id: u64,
    pub kind: String,
    pub size_kb: u64,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Dataset {
    pub accounts: Vec<Account>,
    pub policies: Vec<Policy>,
    pub users: Vec<User>,
    pub resources: Vec<Resource>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct L2Predicate {
    pub account_id: u64,
    pub status: String,
    pub department: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct L2Op {
    pub op: String,
    #[serde(rename = "entityType")]
    pub entity_type: String,
    pub predicate: L2Predicate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct L3Op {
    pub op: String,
    pub user_id: u64,
    pub resource_id: u64,
    pub action: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workload {
    pub L2: Vec<L2Op>,
    pub L3: Vec<L3Op>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuleEvalResult {
    pub allowed: bool,
    pub reason: String,
}

// --- 1. RUST HASHMAP COMPOUND BACKEND ---
pub struct RustHashMapCompound {
    accounts: HashMap<u64, Account>,
    policies: HashMap<u64, Policy>,
    users: HashMap<u64, User>,
    resources: HashMap<u64, Resource>,
    compound_index: HashMap<(u64, String, String), Vec<u64>>,
}

impl RustHashMapCompound {
    pub fn new() -> Self {
        Self {
            accounts: HashMap::new(),
            policies: HashMap::new(),
            users: HashMap::new(),
            resources: HashMap::new(),
            compound_index: HashMap::new(),
        }
    }

    pub fn load(&mut self, dataset: &Dataset) {
        for a in &dataset.accounts { self.accounts.insert(a.id, a.clone()); }
        for p in &dataset.policies { self.policies.insert(p.id, p.clone()); }
        for u in &dataset.users {
            let key = (u.account_id, u.status.clone(), u.metadata.department.clone());
            self.compound_index.entry(key).or_default().push(u.id);
            self.users.insert(u.id, u.clone());
        }
        for r in &dataset.resources { self.resources.insert(r.id, r.clone()); }
    }

    #[inline(always)]
    pub fn execute_l2(&self, op: &L2Op) -> Vec<u64> {
        let key = (op.predicate.account_id, op.predicate.status.clone(), op.predicate.department.clone());
        if let Some(list) = self.compound_index.get(&key) {
            let mut res = list.clone();
            res.sort_unstable();
            res
        } else {
            Vec::new()
        }
    }

    #[inline(always)]
    pub fn execute_l3(&self, op: &L3Op) -> RuleEvalResult {
        let user = match self.users.get(&op.user_id) {
            Some(u) => u,
            None => return RuleEvalResult { allowed: false, reason: "NOT_FOUND".into() },
        };
        let resource = match self.resources.get(&op.resource_id) {
            Some(r) => r,
            None => return RuleEvalResult { allowed: false, reason: "NOT_FOUND".into() },
        };
        if user.account_id != resource.account_id {
            return RuleEvalResult { allowed: false, reason: "CROSS_TENANT_FORBIDDEN".into() };
        }
        let policy = match self.policies.get(&user.policy_id) {
            Some(p) => p,
            None => return RuleEvalResult { allowed: false, reason: "NO_POLICY".into() },
        };

        let mut decision = "DENY";
        for rule in &policy.rules {
            if rule.action == op.action {
                if user.role_level >= rule.min_role_level && resource.size_kb <= rule.max_size_kb {
                    decision = &rule.effect;
                }
            }
        }

        RuleEvalResult {
            allowed: decision == "ALLOW",
            reason: if decision == "ALLOW" { "AUTHORIZED".into() } else { "POLICY_REJECTED".into() },
        }
    }
}

// --- 2. RUST ARENA + INTERNED BACKEND ---
pub struct StringPool {
    pool: Vec<String>,
    lookup: HashMap<String, u32>,
}

impl StringPool {
    pub fn new() -> Self {
        Self { pool: Vec::new(), lookup: HashMap::new() }
    }
    pub fn intern(&mut self, s: &str) -> u32 {
        if let Some(&id) = self.lookup.get(s) { return id; }
        let id = self.pool.len() as u32;
        self.pool.push(s.to_string());
        self.lookup.insert(s.to_string(), id);
        id
    }
    pub fn get_id(&self, s: &str) -> Option<u32> {
        self.lookup.get(s).copied()
    }
}

pub struct RustArenaCompound {
    strings: StringPool,
    compound_index: HashMap<(u64, u32, u32), Vec<u64>>,
    raw: RustHashMapCompound,
}

impl RustArenaCompound {
    pub fn new() -> Self {
        Self {
            strings: StringPool::new(),
            compound_index: HashMap::new(),
            raw: RustHashMapCompound::new(),
        }
    }

    pub fn load(&mut self, dataset: &Dataset) {
        for u in &dataset.users {
            let status_id = self.strings.intern(&u.status);
            let dept_id = self.strings.intern(&u.metadata.department);
            self.compound_index.entry((u.account_id, status_id, dept_id)).or_default().push(u.id);
        }
        self.raw.load(dataset);
    }

    #[inline(always)]
    pub fn execute_l2(&self, op: &L2Op) -> Vec<u64> {
        let status_id = match self.strings.get_id(&op.predicate.status) {
            Some(id) => id,
            None => return Vec::new(),
        };
        let dept_id = match self.strings.get_id(&op.predicate.department) {
            Some(id) => id,
            None => return Vec::new(),
        };
        let key = (op.predicate.account_id, status_id, dept_id);
        if let Some(list) = self.compound_index.get(&key) {
            let mut res = list.clone();
            res.sort_unstable();
            res
        } else {
            Vec::new()
        }
    }

    #[inline(always)]
    pub fn execute_l3(&self, op: &L3Op) -> RuleEvalResult {
        self.raw.execute_l3(op)
    }
}

// --- 3. LIN SEMANTIC ENGINE V4 (100% CANONICAL GRAPH + POLICY + RULES) ---

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct DagNodeId(pub u64);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CanonicalRuleNode {
    pub action_id: u32,
    pub is_allow: bool,
    pub min_role_level: u32,
    pub max_size_kb: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum DagSubtree {
    Metadata { department: String, region: String },
    RoleStatus { role: String, role_level: u32, status: String },
    PolicyRule(CanonicalRuleNode),
    PolicyRulesList(Vec<DagNodeId>),
}

pub struct FullHashConsTable {
    nodes: HashMap<DagSubtree, DagNodeId>,
    reverse_rules: HashMap<DagNodeId, Vec<CanonicalRuleNode>>,
    next_id: u64,
}

impl FullHashConsTable {
    pub fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            reverse_rules: HashMap::new(),
            next_id: 1,
        }
    }

    pub fn intern(&mut self, subtree: DagSubtree) -> DagNodeId {
        if let Some(&id) = self.nodes.get(&subtree) { return id; }
        let id = DagNodeId(self.next_id);
        self.next_id += 1;
        self.nodes.insert(subtree, id);
        id
    }

    pub fn register_rules_list(&mut self, list_id: DagNodeId, rules: Vec<CanonicalRuleNode>) {
        self.reverse_rules.insert(list_id, rules);
    }

    #[inline(always)]
    pub fn get_rules(&self, list_id: DagNodeId) -> Option<&[CanonicalRuleNode]> {
        self.reverse_rules.get(&list_id).map(|v| v.as_slice())
    }
}

#[derive(Clone, Copy)]
pub struct LinResidentUser {
    pub id: u64,
    pub account_id: u64,
    pub policy_id: u64,
    pub role_level: u32,
    pub metadata_id: DagNodeId,
    pub role_status_id: DagNodeId,
}

#[derive(Clone, Copy)]
pub struct LinResidentResource {
    pub id: u64,
    pub account_id: u64,
    pub size_kb: u64,
}

#[derive(Clone, Copy)]
pub struct LinResidentPolicy {
    pub id: u64,
    pub account_id: u64,
    pub rules_list_id: DagNodeId,
}

pub struct LinSemanticEngineV4 {
    hashcons: FullHashConsTable,
    action_strings: HashMap<String, u32>,
    users: HashMap<u64, LinResidentUser>,
    resources: HashMap<u64, LinResidentResource>,
    policies: HashMap<u64, LinResidentPolicy>,
    canonical_compound_index: HashMap<(u64, DagNodeId, DagNodeId), Vec<u64>>,
    status_to_dag: HashMap<String, Vec<DagNodeId>>,
    dept_to_dag: HashMap<String, Vec<DagNodeId>>,
}

impl LinSemanticEngineV4 {
    pub fn new() -> Self {
        Self {
            hashcons: FullHashConsTable::new(),
            action_strings: HashMap::new(),
            users: HashMap::new(),
            resources: HashMap::new(),
            policies: HashMap::new(),
            canonical_compound_index: HashMap::new(),
            status_to_dag: HashMap::new(),
            dept_to_dag: HashMap::new(),
        }
    }

    fn intern_action(&mut self, s: &str) -> u32 {
        if let Some(&id) = self.action_strings.get(s) { return id; }
        let id = self.action_strings.len() as u32;
        self.action_strings.insert(s.to_string(), id);
        id
    }

    pub fn load(&mut self, dataset: &Dataset) {
        // 1. Canonicalize Policies and Rules into pure DAG nodes
        for p in &dataset.policies {
            let mut rule_ids = Vec::with_capacity(p.rules.len());
            let mut resolved_rules = Vec::with_capacity(p.rules.len());
            for r in &p.rules {
                let action_id = self.intern_action(&r.action);
                let cr = CanonicalRuleNode {
                    action_id,
                    is_allow: r.effect == "ALLOW",
                    min_role_level: r.min_role_level,
                    max_size_kb: r.max_size_kb,
                };
                let rule_dag_id = self.hashcons.intern(DagSubtree::PolicyRule(cr.clone()));
                rule_ids.push(rule_dag_id);
                resolved_rules.push(cr);
            }
            let list_dag_id = self.hashcons.intern(DagSubtree::PolicyRulesList(rule_ids));
            self.hashcons.register_rules_list(list_dag_id, resolved_rules);

            self.policies.insert(p.id, LinResidentPolicy {
                id: p.id,
                account_id: p.account_id,
                rules_list_id: list_dag_id,
            });
        }

        // 2. Canonicalize Resources
        for r in &dataset.resources {
            self.resources.insert(r.id, LinResidentResource {
                id: r.id,
                account_id: r.account_id,
                size_kb: r.size_kb,
            });
        }

        // 3. Canonicalize Users & Composite Index
        for u in &dataset.users {
            let meta_id = self.hashcons.intern(DagSubtree::Metadata {
                department: u.metadata.department.clone(),
                region: u.metadata.region.clone(),
            });
            let role_status_id = self.hashcons.intern(DagSubtree::RoleStatus {
                role: u.role.clone(),
                role_level: u.role_level,
                status: u.status.clone(),
            });

            let status_list = self.status_to_dag.entry(u.status.clone()).or_default();
            if !status_list.contains(&role_status_id) { status_list.push(role_status_id); }

            let dept_list = self.dept_to_dag.entry(u.metadata.department.clone()).or_default();
            if !dept_list.contains(&meta_id) { dept_list.push(meta_id); }

            let res_user = LinResidentUser {
                id: u.id,
                account_id: u.account_id,
                policy_id: u.policy_id,
                role_level: u.role_level,
                metadata_id: meta_id,
                role_status_id,
            };

            self.canonical_compound_index
                .entry((u.account_id, role_status_id, meta_id))
                .or_default()
                .push(u.id);

            self.users.insert(u.id, res_user);
        }
    }

    #[inline(always)]
    pub fn execute_l2(&self, op: &L2Op) -> Vec<u64> {
        let status_ids = match self.status_to_dag.get(&op.predicate.status) {
            Some(list) => list,
            None => return Vec::new(),
        };
        let dept_ids = match self.dept_to_dag.get(&op.predicate.department) {
            Some(list) => list,
            None => return Vec::new(),
        };

        let mut matches = Vec::new();
        for &s_id in status_ids {
            for &d_id in dept_ids {
                let key = (op.predicate.account_id, s_id, d_id);
                if let Some(list) = self.canonical_compound_index.get(&key) {
                    matches.extend_from_slice(list);
                }
            }
        }
        matches.sort_unstable();
        matches
    }

    #[inline(always)]
    pub fn execute_l3(&self, op: &L3Op) -> RuleEvalResult {
        let user = match self.users.get(&op.user_id) {
            Some(u) => u,
            None => return RuleEvalResult { allowed: false, reason: "NOT_FOUND".into() },
        };
        let resource = match self.resources.get(&op.resource_id) {
            Some(r) => r,
            None => return RuleEvalResult { allowed: false, reason: "NOT_FOUND".into() },
        };
        if user.account_id != resource.account_id {
            return RuleEvalResult { allowed: false, reason: "CROSS_TENANT_FORBIDDEN".into() };
        }
        let policy = match self.policies.get(&user.policy_id) {
            Some(p) => p,
            None => return RuleEvalResult { allowed: false, reason: "NO_POLICY".into() },
        };

        let target_action_id = match self.action_strings.get(&op.action) {
            Some(&id) => id,
            None => return RuleEvalResult { allowed: false, reason: "POLICY_REJECTED".into() },
        };

        // Pure zero-copy resident rule evaluation directly over canonical rules list
        let rules = match self.hashcons.get_rules(policy.rules_list_id) {
            Some(r) => r,
            None => return RuleEvalResult { allowed: false, reason: "NO_POLICY".into() },
        };

        let mut decision_allow = false;
        for rule in rules {
            if rule.action_id == target_action_id {
                if user.role_level >= rule.min_role_level && resource.size_kb <= rule.max_size_kb {
                    decision_allow = rule.is_allow;
                }
            }
        }

        RuleEvalResult {
            allowed: decision_allow,
            reason: if decision_allow { "AUTHORIZED".into() } else { "POLICY_REJECTED".into() },
        }
    }

    pub fn unique_dag_nodes(&self) -> usize {
        self.hashcons.nodes.len()
    }
}

// --- HARNESS RUNNER ---

fn compute_percentiles(mut latencies: Vec<u128>) -> (f64, f64, f64, f64, f64) {
    if latencies.is_empty() { return (0.0, 0.0, 0.0, 0.0, 0.0); }
    latencies.sort_unstable();
    let n = latencies.len();
    let p50 = latencies[(n as f64 * 0.50) as usize] as f64 / 1000.0;
    let p90 = latencies[(n as f64 * 0.90) as usize] as f64 / 1000.0;
    let p95 = latencies[(n as f64 * 0.95) as usize] as f64 / 1000.0;
    let p99 = latencies[(n as f64 * 0.99) as usize] as f64 / 1000.0;
    let sum: u128 = latencies.iter().sum();
    let avg = (sum as f64 / n as f64) / 1000.0;
    (p50, p90, p95, p99, avg)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 {
        eprintln!("Usage: rust_engine_v4 <mode> <dataset_json> <workload_json> [out_json]");
        std::process::exit(1);
    }

    let mode = &args[1];
    let dataset_path = &args[2];
    let workload_path = &args[3];
    let out_json_path = args.get(4);

    let dfile = File::open(dataset_path).expect("failed to open dataset");
    let dataset: Dataset = serde_json::from_reader(BufReader::new(dfile)).expect("failed to parse dataset");
    let total_entities = dataset.accounts.len() + dataset.policies.len() + dataset.users.len() + dataset.resources.len();
    let total_relations = dataset.users.len() * 2 + dataset.resources.len() * 2;

    let wfile = File::open(workload_path).expect("failed to open workload");
    let workload: Workload = serde_json::from_reader(BufReader::new(wfile)).expect("failed to parse workload");

    let heap_before = get_heap_bytes();
    let load_start = Instant::now();

    let mut hashmap = RustHashMapCompound::new();
    let mut arena = RustArenaCompound::new();
    let mut lin = LinSemanticEngineV4::new();

    match mode.as_str() {
        "hashmap" => hashmap.load(&dataset),
        "arena_interned" => arena.load(&dataset),
        "lin_semantic_engine" => lin.load(&dataset),
        other => panic!("Unknown mode: {}", other),
    }

    let load_duration_ms = load_start.elapsed().as_secs_f64() * 1000.0;
    let heap_after = get_heap_bytes();
    let allocated_bytes = heap_after.saturating_sub(heap_before);

    // Warmup
    for op in workload.L3.iter().take(500) {
        match mode.as_str() {
            "hashmap" => { let _ = hashmap.execute_l3(op); }
            "arena_interned" => { let _ = arena.execute_l3(op); }
            _ => { let _ = lin.execute_l3(op); }
        }
    }

    // Execute L2
    let mut l2_latencies = Vec::with_capacity(workload.L2.len());
    let mut l2_results = Vec::with_capacity(workload.L2.len());
    let l2_start = Instant::now();
    for op in &workload.L2 {
        let t0 = Instant::now();
        let res = match mode.as_str() {
            "hashmap" => hashmap.execute_l2(op),
            "arena_interned" => arena.execute_l2(op),
            _ => lin.execute_l2(op),
        };
        l2_latencies.push(t0.elapsed().as_nanos());
        l2_results.push(res);
    }
    let l2_duration_s = l2_start.elapsed().as_secs_f64();
    let l2_ops_sec = workload.L2.len() as f64 / l2_duration_s;
    let (l2_p50, l2_p90, l2_p95, l2_p99, l2_avg) = compute_percentiles(l2_latencies);

    // Execute L3
    let mut l3_latencies = Vec::with_capacity(workload.L3.len());
    let mut l3_results = Vec::with_capacity(workload.L3.len());
    let l3_start = Instant::now();
    for op in &workload.L3 {
        let t0 = Instant::now();
        let res = match mode.as_str() {
            "hashmap" => hashmap.execute_l3(op),
            "arena_interned" => arena.execute_l3(op),
            _ => lin.execute_l3(op),
        };
        l3_latencies.push(t0.elapsed().as_nanos());
        l3_results.push(res);
    }
    let l3_duration_s = l3_start.elapsed().as_secs_f64();
    let l3_ops_sec = workload.L3.len() as f64 / l3_duration_s;
    let (l3_p50, l3_p90, l3_p95, l3_p99, l3_avg) = compute_percentiles(l3_latencies);

    let bytes_per_entity = if total_entities > 0 { allocated_bytes as f64 / total_entities as f64 } else { 0.0 };
    let bytes_per_relation = if total_relations > 0 { allocated_bytes as f64 / total_relations as f64 } else { 0.0 };

    let summary = serde_json::json!({
        "backend": mode,
        "cold_load_ms": load_duration_ms,
        "resident_heap_bytes": allocated_bytes,
        "total_entities": total_entities,
        "total_relations": total_relations,
        "bytes_per_entity": bytes_per_entity,
        "bytes_per_relation": bytes_per_relation,
        "unique_dag_nodes": if mode == "lin_semantic_engine" { lin.unique_dag_nodes() } else { 0 },
        "L2": { "ops_per_sec": l2_ops_sec, "p50_us": l2_p50, "p90_us": l2_p90, "p95_us": l2_p95, "p99_us": l2_p99, "avg_us": l2_avg },
        "L3": { "ops_per_sec": l3_ops_sec, "p50_us": l3_p50, "p90_us": l3_p90, "p95_us": l3_p95, "p99_us": l3_p99, "avg_us": l3_avg },
        "results": {
            "L2": l2_results,
            "L3": l3_results,
        }
    });

    if let Some(path) = out_json_path {
        let f = File::create(path).expect("failed to create output file");
        serde_json::to_writer_pretty(f, &summary).expect("failed to write output JSON");
    } else {
        println!("{}", serde_json::to_string_pretty(&summary).unwrap());
    }
}
