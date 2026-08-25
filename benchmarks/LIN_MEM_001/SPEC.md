# LIN-MEM-001: Semantic Memory Engine Benchmark Contract

## 1. Object and Thesis

**Hypothesis under test:**
> A canonicalized semantic representation with structural hash-consing and resident memory execution can serve simultaneously as storage, index, and execution substrate, reducing memory footprint and operational latency when structural sharing is present, without sacrificing determinism or correctness.

This benchmark does **not** assume LIN is superior a priori. It empirically isolates where and by how much structural canonicalization outperforms or lags behind standard in-memory architectures.

---

## 2. Experimental Dimensions

### 2.1 Dataset Scales
- `100K` entities
- `500K` entities
- `1M` entities

### 2.2 Redundancy Regimes (Testing Structural Sharing)
1. **Regime A (Low Redundancy / Unique Trees):**
   - High entropy, unique attributes, minimal subtree duplication.
2. **Regime B (High Redundancy / Shared Structures):**
   - 10 fixed tenants, 5 user roles, 8 standardized security policies, 20 status combinations.
   - Evaluates pure HashCons deduplication factor:
     $$\text{Deduplication Factor} = \frac{\text{Memory}(\text{Naive})}{\text{Memory}(\text{HashCons})}$$

### 2.3 Execution Phases
- **COLD Phase:**
  - Process startup, file/buffer read, graph ingestion, index/arena build.
  - Measures: Ingestion time (ms), Ingestion throughput (entities/sec), Peak cold RSS.
- **WARM Phase (Resident Execution):**
  - Dataset is already pinned in RAM.
  - Isolated measurement of pure operational latency and throughput without I/O or ingestion artifacts.

---

## 3. Workload Levels

### Level 0 (L0) — Point Lookup (`GET`)
- **Operation:** `get_entity(id) -> Entity`
- **Tests:** Direct index lookup overhead in resident memory.

### Level 1 (L1) — Deep Structural Equality (`EQ`)
- **Operation:** `eq(entity_a, entity_b) -> bool`
- **Tests:** O(1) HashCons pointer/hash comparison vs O(N) deep recursive subtree traversal. Includes collision verification step.

### Level 2 (L2) — Semantic Multi-Attribute Filter (`FILTER`)
- **Operation:** `filter(type == T, status == S, tenant == X) -> List<EntityId>`
- **Tests:** Query traversal without intermediate object materialization or DTO instantiation.

### Level 3 (L3) — Relation Traversal + Rule Evaluation (`TRAVERSE + RULE`)
- **Operation:**
  - Traversal: A -> belongs_to -> B -> has_policy -> C
  - Rule Evaluation: eval_rule(A, C.policy) where policy enforces conditions on permissions, quotas, and roles.
- **Tests:** Unified substrate efficiency: traversing graph edges and executing domain rules directly on resident IR.

### Level 4 (L4) — Structural Sharing Ratio Analysis (`SHARED`)
- **Operation:** Differential memory and latency comparison between Regime A and Regime B across all levels.

---

## 4. Backends Under Test

1. **`node_map`**: Node.js v24 `Map<string, Object>` in-memory graph.
2. **`sqlite_memory`**: SQLite (`:memory:`) with normalized relational schema and B-Tree indexes.
3. **`rust_hashmap`**: Rust `std::collections::HashMap<u64, Entity>` (flat struct baseline).
4. **`rust_arena_interned`**: Rust typed bump arena + string interning baseline.
5. **`rust_hashcons_dag`**: Rust Canonical DAG with HashConsing and collision validation.
6. **`lin_semantic_engine`**: LIN Resident Semantic Memory Engine.

---

## 5. Success & Validation Gates

- **Gate C1 (Correctness):** 100% output equivalence against Golden Oracle across all queries.
- **Gate C2 (Determinism):** Zero output drift across multiple repeated runs with the same seed.
- **Gate C3 (Collision Integrity):** Zero false positives on structural equality.
- **Gate C4 (Density Metric):** Exact measurement of `bytes/entity` and `bytes/relation`.
