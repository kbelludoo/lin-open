use std::collections::HashMap;
use std::collections::hash_map::DefaultHasher;
use std::fs::File;
use std::hash::{Hash, Hasher};
use std::io::BufReader;
use std::time::Instant;
use serde::{Deserialize, Serialize};

// --- DATASET DEFINITIONS ---

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

// --- WORKLOAD DEFINITIONS ---

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct L0Op {
    pub op: String,
    #[serde(rename = "entityType")]
    pub entity_type: String,
    pub id: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct L1Op {
    pub op: String,
    #[serde(rename = "entityType")]
    pub entity_type: String,
    #[serde(rename = "idA")]
    pub id_a: u64,
    #[serde(rename = "idB")]
    pub id_b: u64,
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
    pub L0: Vec<L0Op>,
    pub L1: Vec<L1Op>,
    pub L2: Vec<L2Op>,
    pub L3: Vec<L3Op>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuleEvalResult {
    pub allowed: bool,
    pub reason: String,
}

// --- MEMORY HELPER ---
fn get_proc_rss() -> usize {
    if let Ok(statm) = std::fs::read_to_string("/proc/self/statm") {
        let parts: Vec<&str> = statm.split_whitespace().collect();
        if parts.len() >= 2 {
            if let Ok(pages) = parts[1].parse::<usize>() {
                return pages * 4096;
            }
        }
    }
    0
}

// --- 1. RUST HASHMAP BACKEND ---
pub struct RustHashMapBackend {
    accounts: HashMap<u64, Account>,
    policies: HashMap<u64, Policy>,
    users: HashMap<u64, User>,
    resources: HashMap<u64, Resource>,
    user_filter_idx: HashMap<(u64, String, String), Vec<u64>>,
}

impl RustHashMapBackend {
    pub fn new() -> Self {
        Self {
            accounts: HashMap::new(),
            policies: HashMap::new(),
            users: HashMap::new(),
            resources: HashMap::new(),
            user_filter_idx: HashMap::new(),
        }
    }

    pub fn load(&mut self, dataset: Dataset) {
        for a in dataset.accounts {
            self.accounts.insert(a.id, a);
        }
        for p in dataset.policies {
            self.policies.insert(p.id, p);
        }
        for u in dataset.users {
            let key = (u.account_id, u.status.clone(), u.metadata.department.clone());
            self.user_filter_idx.entry(key).or_default().push(u.id);
            self.users.insert(u.id, u);
        }
        for r in dataset.resources {
            self.resources.insert(r.id, r);
        }
    }

    pub fn get_user(&self, id: u64) -> Option<&User> { self.users.get(&id) }
    pub fn get_resource(&self, id: u64) -> Option<&Resource> { self.resources.get(&id) }
    pub fn get_policy(&self, id: u64) -> Option<&Policy> { self.policies.get(&id) }
    pub fn get_account(&self, id: u64) -> Option<&Account> { self.accounts.get(&id) }

    pub fn execute_l0(&self, op: &L0Op) -> Option<serde_json::Value> {
        match op.entity_type.as_str() {
            "User" => self.get_user(op.id).map(|v| serde_json::to_value(v).unwrap()),
            "Resource" => self.get_resource(op.id).map(|v| serde_json::to_value(v).unwrap()),
            "Policy" => self.get_policy(op.id).map(|v| serde_json::to_value(v).unwrap()),
            "Account" => self.get_account(op.id).map(|v| serde_json::to_value(v).unwrap()),
            _ => None,
        }
    }

    pub fn execute_l1(&self, op: &L1Op) -> bool {
        match op.entity_type.as_str() {
            "User" => {
                match (self.get_user(op.id_a), self.get_user(op.id_b)) {
                    (Some(a), Some(b)) => a == b,
                    _ => false,
                }
            }
            _ => false,
        }
    }

    pub fn execute_l2(&self, op: &L2Op) -> Vec<u64> {
        let key = (op.predicate.account_id, op.predicate.status.clone(), op.predicate.department.clone());
        if let Some(list) = self.user_filter_idx.get(&key) {
            let mut res = list.clone();
            res.sort_unstable();
            res
        } else {
            Vec::new()
        }
    }

    pub fn execute_l3(&self, op: &L3Op) -> RuleEvalResult {
        let user = match self.get_user(op.user_id) {
            Some(u) => u,
            None => return RuleEvalResult { allowed: false, reason: "NOT_FOUND".into() },
        };
        let resource = match self.get_resource(op.resource_id) {
            Some(r) => r,
            None => return RuleEvalResult { allowed: false, reason: "NOT_FOUND".into() },
        };
        if user.account_id != resource.account_id {
            return RuleEvalResult { allowed: false, reason: "CROSS_TENANT_FORBIDDEN".into() };
        }
        let policy = match self.get_policy(user.policy_id) {
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

// --- 2. RUST ARENA + STRING INTERNING BACKEND ---
pub struct StringPool {
    pool: Vec<String>,
    lookup: HashMap<String, u32>,
}

impl StringPool {
    pub fn new() -> Self {
        Self { pool: Vec::new(), lookup: HashMap::new() }
    }
    pub fn intern(&mut self, s: &str) -> u32 {
        if let Some(&id) = self.lookup.get(s) {
            return id;
        }
        let id = self.pool.len() as u32;
        self.pool.push(s.to_string());
        self.lookup.insert(s.to_string(), id);
        id
    }
    pub fn get(&self, id: u32) -> &str {
        &self.pool[id as usize]
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub struct InternedUser {
    pub id: u64,
    pub account_id: u64,
    pub policy_id: u64,
    pub username_id: u32,
    pub role_id: u32,
    pub role_level: u32,
    pub status_id: u32,
    pub department_id: u32,
    pub region_id: u32,
}

pub struct RustArenaInternedBackend {
    strings: StringPool,
    users: Vec<Option<InternedUser>>,
    raw_dataset: RustHashMapBackend,
}

impl RustArenaInternedBackend {
    pub fn new() -> Self {
        Self {
            strings: StringPool::new(),
            users: Vec::new(),
            raw_dataset: RustHashMapBackend::new(),
        }
    }

    pub fn load(&mut self, dataset: Dataset) {
        let max_id = dataset.users.iter().map(|u| u.id).max().unwrap_or(0) as usize;
        self.users.resize(max_id + 1, None);

        for u in &dataset.users {
            let iu = InternedUser {
                id: u.id,
                account_id: u.account_id,
                policy_id: u.policy_id,
                username_id: self.strings.intern(&u.username),
                role_id: self.strings.intern(&u.role),
                role_level: u.role_level,
                status_id: self.strings.intern(&u.status),
                department_id: self.strings.intern(&u.metadata.department),
                region_id: self.strings.intern(&u.metadata.region),
            };
            self.users[u.id as usize] = Some(iu);
        }
        self.raw_dataset.load(dataset);
    }

    pub fn execute_l0(&self, op: &L0Op) -> Option<serde_json::Value> {
        self.raw_dataset.execute_l0(op)
    }

    pub fn execute_l1(&self, op: &L1Op) -> bool {
        if op.entity_type == "User" {
            let u1 = self.users.get(op.id_a as usize).and_then(|x| *x);
            let u2 = self.users.get(op.id_b as usize).and_then(|x| *x);
            match (u1, u2) {
                (Some(a), Some(b)) => a == b,
                _ => false,
            }
        } else {
            self.raw_dataset.execute_l1(op)
        }
    }

    pub fn execute_l2(&self, op: &L2Op) -> Vec<u64> {
        self.raw_dataset.execute_l2(op)
    }

    pub fn execute_l3(&self, op: &L3Op) -> RuleEvalResult {
        self.raw_dataset.execute_l3(op)
    }
}

// --- 3. RUST HASH-CONSED DAG / LIN SEMANTIC ENGINE ---
// Structural hash-consing for subtrees:
// - User -> (core_props, metadata_node_id, role_status_node_id)
// - HashCons table deduplicates identical subtrees into unified 64-bit node IDs

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum DagSubtree {
    Metadata { department: String, region: String },
    RoleStatus { role: String, role_level: u32, status: String },
    Limits { max_users: u32, max_storage_mb: u64, features: Vec<String> },
    PolicyRules { rules: Vec<PolicyRule> },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct DagNodeId(pub u64);

pub struct HashConsTable {
    nodes: HashMap<DagSubtree, DagNodeId>,
    reverse: HashMap<DagNodeId, DagSubtree>,
    next_id: u64,
}

impl HashConsTable {
    pub fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            reverse: HashMap::new(),
            next_id: 1,
        }
    }

    pub fn intern(&mut self, subtree: DagSubtree) -> DagNodeId {
        if let Some(&id) = self.nodes.get(&subtree) {
            return id;
        }
        let id = DagNodeId(self.next_id);
        self.next_id += 1;
        self.nodes.insert(subtree.clone(), id);
        self.reverse.insert(id, subtree);
        id
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct CanonicalUserNode {
    pub id: u64,
    pub account_id: u64,
    pub policy_id: u64,
    pub structural_hash: u64, // O(1) equality signature
    pub metadata_dag_id: DagNodeId,
    pub role_status_dag_id: DagNodeId,
}

pub struct LinSemanticEngineBackend {
    hash_cons: HashConsTable,
    users: HashMap<u64, CanonicalUserNode>,
    raw_dataset: RustHashMapBackend,
}

impl LinSemanticEngineBackend {
    pub fn new() -> Self {
        Self {
            hash_cons: HashConsTable::new(),
            users: HashMap::new(),
            raw_dataset: RustHashMapBackend::new(),
        }
    }

    pub fn load(&mut self, dataset: Dataset) {
        for u in &dataset.users {
            let meta_id = self.hash_cons.intern(DagSubtree::Metadata {
                department: u.metadata.department.clone(),
                region: u.metadata.region.clone(),
            });
            let role_status_id = self.hash_cons.intern(DagSubtree::RoleStatus {
                role: u.role.clone(),
                role_level: u.role_level,
                status: u.status.clone(),
            });

            // Compute canonical structural hash
            let mut hasher = DefaultHasher::new();
            u.id.hash(&mut hasher);
            u.account_id.hash(&mut hasher);
            u.policy_id.hash(&mut hasher);
            meta_id.0.hash(&mut hasher);
            role_status_id.0.hash(&mut hasher);
            let structural_hash = hasher.finish();

            let canonical = CanonicalUserNode {
                id: u.id,
                account_id: u.account_id,
                policy_id: u.policy_id,
                structural_hash,
                metadata_dag_id: meta_id,
                role_status_dag_id: role_status_id,
            };
            self.users.insert(u.id, canonical);
        }
        self.raw_dataset.load(dataset);
    }

    pub fn execute_l0(&self, op: &L0Op) -> Option<serde_json::Value> {
        self.raw_dataset.execute_l0(op)
    }

    // L1: Structural Equality with O(1) fast-path + collision safety fallback
    pub fn execute_l1(&self, op: &L1Op) -> bool {
        if op.entity_type == "User" {
            let u1 = self.users.get(&op.id_a);
            let u2 = self.users.get(&op.id_b);
            match (u1, u2) {
                (Some(a), Some(b)) => {
                    // Fast path: structural hash
                    if a.structural_hash != b.structural_hash {
                        return false;
                    }
                    // Collision check: verify node pointer IDs
                    a.id == b.id
                        && a.account_id == b.account_id
                        && a.policy_id == b.policy_id
                        && a.metadata_dag_id == b.metadata_dag_id
                        && a.role_status_dag_id == b.role_status_dag_id
                }
                _ => false,
            }
        } else {
            self.raw_dataset.execute_l1(op)
        }
    }

    pub fn execute_l2(&self, op: &L2Op) -> Vec<u64> {
        self.raw_dataset.execute_l2(op)
    }

    pub fn execute_l3(&self, op: &L3Op) -> RuleEvalResult {
        self.raw_dataset.execute_l3(op)
    }

    pub fn unique_dag_nodes(&self) -> usize {
        self.hash_cons.nodes.len()
    }
}

// --- BENCHMARK HARNESS RUNNER ---

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
        eprintln!("Usage: rust_engine <mode> <dataset_json> <workload_json> [out_json]");
        eprintln!("Modes: hashmap | arena_interned | hashcons_dag | lin_semantic_engine");
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

    let rss_before_load = get_proc_rss();
    let load_start = Instant::now();

    // Instantiate selected backend
    let mut hashmap_backend = RustHashMapBackend::new();
    let mut arena_backend = RustArenaInternedBackend::new();
    let mut lin_backend = LinSemanticEngineBackend::new();

    match mode.as_str() {
        "hashmap" => hashmap_backend.load(dataset),
        "arena_interned" => arena_backend.load(dataset),
        "hashcons_dag" | "lin_semantic_engine" => lin_backend.load(dataset),
        other => panic!("Unknown mode: {}", other),
    }

    let load_duration_ms = load_start.elapsed().as_secs_f64() * 1000.0;
    let rss_after_load = get_proc_rss();
    let resident_memory_bytes = rss_after_load.saturating_sub(rss_before_load);

    // Warmup run
    for op in workload.L0.iter().take(500) {
        match mode.as_str() {
            "hashmap" => { let _ = hashmap_backend.execute_l0(op); }
            "arena_interned" => { let _ = arena_backend.execute_l0(op); }
            _ => { let _ = lin_backend.execute_l0(op); }
        }
    }

    // --- EXECUTE L0 ---
    let mut l0_latencies = Vec::with_capacity(workload.L0.len());
    let mut l0_results = Vec::with_capacity(workload.L0.len());
    let l0_start = Instant::now();
    for op in &workload.L0 {
        let t0 = Instant::now();
        let res = match mode.as_str() {
            "hashmap" => hashmap_backend.execute_l0(op),
            "arena_interned" => arena_backend.execute_l0(op),
            _ => lin_backend.execute_l0(op),
        };
        l0_latencies.push(t0.elapsed().as_nanos());
        l0_results.push(res);
    }
    let l0_duration_s = l0_start.elapsed().as_secs_f64();
    let l0_ops_sec = workload.L0.len() as f64 / l0_duration_s;
    let (l0_p50, l0_p90, l0_p95, l0_p99, l0_avg) = compute_percentiles(l0_latencies);

    // --- EXECUTE L1 ---
    let mut l1_latencies = Vec::with_capacity(workload.L1.len());
    let mut l1_results = Vec::with_capacity(workload.L1.len());
    let l1_start = Instant::now();
    for op in &workload.L1 {
        let t0 = Instant::now();
        let res = match mode.as_str() {
            "hashmap" => hashmap_backend.execute_l1(op),
            "arena_interned" => arena_backend.execute_l1(op),
            _ => lin_backend.execute_l1(op),
        };
        l1_latencies.push(t0.elapsed().as_nanos());
        l1_results.push(res);
    }
    let l1_duration_s = l1_start.elapsed().as_secs_f64();
    let l1_ops_sec = workload.L1.len() as f64 / l1_duration_s;
    let (l1_p50, l1_p90, l1_p95, l1_p99, l1_avg) = compute_percentiles(l1_latencies);

    // --- EXECUTE L2 ---
    let mut l2_latencies = Vec::with_capacity(workload.L2.len());
    let mut l2_results = Vec::with_capacity(workload.L2.len());
    let l2_start = Instant::now();
    for op in &workload.L2 {
        let t0 = Instant::now();
        let res = match mode.as_str() {
            "hashmap" => hashmap_backend.execute_l2(op),
            "arena_interned" => arena_backend.execute_l2(op),
            _ => lin_backend.execute_l2(op),
        };
        l2_latencies.push(t0.elapsed().as_nanos());
        l2_results.push(res);
    }
    let l2_duration_s = l2_start.elapsed().as_secs_f64();
    let l2_ops_sec = workload.L2.len() as f64 / l2_duration_s;
    let (l2_p50, l2_p90, l2_p95, l2_p99, l2_avg) = compute_percentiles(l2_latencies);

    // --- EXECUTE L3 ---
    let mut l3_latencies = Vec::with_capacity(workload.L3.len());
    let mut l3_results = Vec::with_capacity(workload.L3.len());
    let l3_start = Instant::now();
    for op in &workload.L3 {
        let t0 = Instant::now();
        let res = match mode.as_str() {
            "hashmap" => hashmap_backend.execute_l3(op),
            "arena_interned" => arena_backend.execute_l3(op),
            _ => lin_backend.execute_l3(op),
        };
        l3_latencies.push(t0.elapsed().as_nanos());
        l3_results.push(res);
    }
    let l3_duration_s = l3_start.elapsed().as_secs_f64();
    let l3_ops_sec = workload.L3.len() as f64 / l3_duration_s;
    let (l3_p50, l3_p90, l3_p95, l3_p99, l3_avg) = compute_percentiles(l3_latencies);

    let bytes_per_entity = if total_entities > 0 { resident_memory_bytes as f64 / total_entities as f64 } else { 0.0 };
    let bytes_per_relation = if total_relations > 0 { resident_memory_bytes as f64 / total_relations as f64 } else { 0.0 };

    let summary = serde_json::json!({
        "backend": mode,
        "cold_load_ms": load_duration_ms,
        "resident_memory_bytes": resident_memory_bytes,
        "total_entities": total_entities,
        "total_relations": total_relations,
        "bytes_per_entity": bytes_per_entity,
        "bytes_per_relation": bytes_per_relation,
        "unique_dag_nodes": if mode.contains("hashcons") || mode.contains("lin") { lin_backend.unique_dag_nodes() } else { 0 },
        "L0": { "ops_per_sec": l0_ops_sec, "p50_us": l0_p50, "p90_us": l0_p90, "p95_us": l0_p95, "p99_us": l0_p99, "avg_us": l0_avg },
        "L1": { "ops_per_sec": l1_ops_sec, "p50_us": l1_p50, "p90_us": l1_p90, "p95_us": l1_p95, "p99_us": l1_p99, "avg_us": l1_avg },
        "L2": { "ops_per_sec": l2_ops_sec, "p50_us": l2_p50, "p90_us": l2_p90, "p95_us": l2_p95, "p99_us": l2_p99, "avg_us": l2_avg },
        "L3": { "ops_per_sec": l3_ops_sec, "p50_us": l3_p50, "p90_us": l3_p90, "p95_us": l3_p95, "p99_us": l3_p99, "avg_us": l3_avg },
        "results": {
            "L0": l0_results,
            "L1": l1_results,
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
