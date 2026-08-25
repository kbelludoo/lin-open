# LIN-MEM-003: Canonical Composite Indexes & Multi-Hop Traversal Substrate

## 1. Object & Research Frontier
Following findings from `LIN-MEM-001` and `LIN-MEM-002`, `LIN-MEM-003` addresses the identified bottleneck:
> **How does an index built directly over canonical 64-bit HashCons Node IDs (Canonical Semantic Index) perform in multi-attribute filtering (L2) and multi-hop relation rule evaluation (L3), compared to traditional tuple/string-based inverted indexes and flat HashMaps, while preserving the 3.2x memory compression?**

---

## 2. Core Architectural Hypothesis
1. **Canonical Key Compression:** In traditional indexing, composite keys `(tenant, status, department)` require composite string/tuple allocations or compound hash codes. In LIN, composite keys are simple tuples of 64-bit canonical node IDs `(u64, DagNodeId, DagNodeId)` which are $O(1)$ to hash and store.
2. **Zero Traversal Filter (L2 Resolution):** Multi-attribute queries resolve through canonical ID lookup in $O(1)$ without scanning the DAG or instantiating intermediate objects.
3. **Multi-Hop Traversal + Rule Synergy (L3 Resolution):** Relations link canonical entities directly, allowing $N$-hop path traversal with instant in-situ rule evaluation.

---

## 3. Evaluated Workload Dimensions
- **Scale:** `100K`, `500K`, `1M` entities.
- **Operations:**
  - **L2_CANONICAL (Composite Filter):** `filter(account_id, status, department) -> Vec<u64>` via Canonical Semantic Index.
  - **L3_MULTIHOP (Multi-Hop Traversal + Rule Engine):** $A \to B \to C \to D$ (User $\to$ Account $\to$ Resource $\to$ Policy) evaluating multi-action permissions.
  - **DENSITY & COLD LOAD:** Exact heap bytes via Tracking Allocator and ingestion time.

---

## 4. Backends Under Comparison
1. **`rust_hashmap_compound`**: Rust HashMap with compound tuple index `(u64, String, String) -> Vec<u64>`.
2. **`rust_arena_compound`**: Rust Arena + String Interning with interned ID compound index `(u64, u32, u32) -> Vec<u64>`.
3. **`lin_semantic_engine_v3`**: LIN Resident Engine with **Canonical Composite Semantic Index** (`(u64, DagNodeId, DagNodeId) -> Vec<u64>`) over HashCons DAG.
