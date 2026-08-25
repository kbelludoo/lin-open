# LIN-MEM-002: Structural Sharing Scaling & Composite Semantic Execution

## 1. Central Research Question
> **Does the performance and density advantage of the LIN Semantic Memory Engine scale proportionally with the degree of structural sharing and graph scale (100K -> 500K -> 1M entities)?**

## 2. Refined Core Hypotheses
1. **Amortization Hypothesis:** The cold canonicalization tax (~1.6x load time) is amortized within $N$ warm queries, after which composite semantic operations achieve net operational gains.
2. **Sharing-Proportionality Hypothesis:** Under High Structural Sharing (Regime Shared), HashCons DAG collapses subtrees into $O(1)$ canonical nodes, lowering memory footprint and accelerating composite traversals (L2/L3) relative to Regime Unique.
3. **Substrate Cohesion Hypothesis:** In composite multi-step operations (traversing relations while evaluating nested policy rules), executing directly over resident canonical IR outperforms dissociated stores and flat struct models.

## 3. Scale & Regime Matrix
- **Scales:** `100K`, `500K`, `1M` entities.
- **Regimes:**
  - **Unique (Low Sharing):** High-entropy fields, minimal subtree duplication.
  - **Shared (High Sharing):** Constrained domain spaces (tenants, roles, policies, departments).
- **Workloads Focused:**
  - **L2:** Semantic Multi-Attribute Filtering (`FILTER`).
  - **L3:** Relation Traversal + In-situ Policy Rule Evaluation (`TRAVERSE + RULE`).
  - **L4 (Differential):** Delta Ratio = Metric(Shared) / Metric(Unique).

## 4. Measured Backends
1. **Node.js `Map`**
2. **SQLite `:memory:`**
3. **Rust `HashMap`** (Flat struct baseline)
4. **Rust Arena + Interning**
5. **LIN Semantic Engine** (Resident HashCons DAG)
