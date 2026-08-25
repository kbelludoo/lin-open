# LIN-REAL-BENCH-001: Historical Real-World Open-Source Bug Benchmark & 7-Stage Component Ablation

## 1. Scientific Mandate
To definitively evaluate whether LIN delivers superior real-world software engineering capabilities beyond synthetic benchmarks:
> **How does Full LIN (Canonical HashCons + Dependency DAG + Contracts % + Effects * + Trauma Ledger + Causal Frontier) compare against Raw LLM, Chat Buffers, and intermediate ablated components across real open-source repositories with historical bugs, zero human hints, and strict metric separation?**

---

## 2. Experimental Design & Principles

### A. Real Open-Source Repositories with Real Historical Commits
- Real repositories from the ecosystem (e.g. `semver`, `minimist`, `dayjs`, `chalk`, `commander`, `mime-types`, etc.).
- Historical buggy commit paired with the exact real-world issue report and test assertion failure.
- Verified against the official historical fix commit for regression and behavior equivalence.

### B. Strictly Blinded Agent Execution
- The agent receives **zero hints** about target files, functions, or line numbers.
- Input provided to agent:
  1. Real Issue Report (Title & Description)
  2. Failing Test Command & Error Trace / Stack
  3. Real Repository on disk (unmodified files)
- LIN autonomously parses the AST, extracts symbols, builds HashCons identities, constructs dependency graphs, and discovers candidates dynamically.

### C. Orthogonal Metric Separation ($L, P, R, H, W, T, \tau$)
1. **$L$ (Root-Cause Localization Rate):** Did the agent edit the exact file & symbol containing the bug origin?
2. **$P$ (Patch Correctness / Test Pass Rate):** Did the failing test suite pass after the patch?
3. **$R$ (Regression Safety Rate):** Did all non-targeted pre-existing test suites continue to pass?
4. **$H$ (Hypothesis Recovery Rate):** If attempt 1 failed, did the agent successfully recover on attempt 2 or 3?
5. **$W$ (Patch Pollution):** Count of wrong files edited, wrong functions modified, and unnecessary lines changed.
6. **$T$ (Token Efficiency):** Prompt tokens, evaluation tokens, and total token footprint per task.
7. **$\tau$ (Cycle Latency):** Wall-clock execution time per resolution attempt.

---

## 3. 7-Stage Component Ablation Matrix

| Condition | Architecture & Enabled Features |
| :--- | :--- |
| **Arm A (RAW)** | Pure LLM with repository text retrieval |
| **Arm B (CHAT)** | LLM with historical failure chat buffer |
| **Arm C (HashCons)** | LLM + Canonical HashCons Substrate Indexing |
| **Arm D (DAG)** | LLM + HashCons + Transitive Dependency DAG |
| **Arm E (Contracts & Effects)** | LLM + DAG + Invariants (`%`) + Effect Safety (`*`) |
| **Arm F (Trauma Ledger)** | LLM + DAG + Contracts + Effects + Trauma Memory |
| **Arm G (Full LIN Frontier)** | Full LIN Runtime (DAG + `%` + `*` + Trauma + Causal Frontier Navigation) |
