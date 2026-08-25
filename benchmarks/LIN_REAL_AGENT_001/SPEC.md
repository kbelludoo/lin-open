# LIN-REAL-AGENT-001: Autonomous Software Maintenance Benchmark

## 1. Objective & Hypothesis
**Research Question:**
> Does integrating a resident semantic state engine (LIN Semantic Memory & Invariant Verifier) into an autonomous programming agent improve task success rate, recovery rate upon failure, and context efficiency when resolving real maintenance tasks in multi-module software, compared to raw LLMs and chat-history baselines?

---

## 2. Experimental Groups (4-Arm Controlled Trial)

| Group | Name | Description | Context Representation |
| :--- | :--- | :--- | :--- |
| **A** | `Raw LLM` | Zero-state LLM | Issue prompt + raw file content |
| **B** | `History LLM` | Standard Agent with Chat Buffer | Issue prompt + accumulated text history of attempts and errors |
| **C** | `LIN Memory` | LLM + LIN Semantic Graph | Issue prompt + Canonical Symbol Graph, Dependencies, and Failure Ledger |
| **D** | `LIN + Verifier` | LLM + LIN Memory + Verifier | LIN Memory + Invariant Static Gate & Selective Affected Test Verification |

---

## 3. Strict Controlled Variables
- **Model:** Same LLM across all groups.
- **Seed & Temperature:** Constant (`seed=424242`, `temperature=0.2`).
- **Attempts:** Exactly 3 attempts maximum per task.
- **Repo State:** Clean checkout at frozen commit before each task attempt.
- **Task Suite:** Exactly the same 100 real maintenance tasks.

---

## 4. Task Suite Topology (100 Tasks)
1. **T001–T040 (40 Unit Bugs):** Parsing, regex safety, type coercion, operator logic.
2. **T041–T070 (30 Multi-Module Regressions):** Changes spanning across 2+ interrelated modules with dependent symbol graphs.
3. **T071–T100 (30 Complex Edge Cases):** Prereleases, build metadata, wildcards, caret/tilde boundary conditions.

---

## 5. Metric Definitions

### 5.1 Success & Recovery Decompositions
- `initial_success`: Task resolved on Attempt 1.
- `recovered_success`: Task failed Attempt 1, but resolved on Attempt 2 or 3.
- `persistent_failure`: Task failed all 3 attempts.
- **`Task Success Rate`**: $\frac{\text{initial\_success} + \text{recovered\_success}}{100}$
- **`Recovery Rate`**: $\frac{\text{recovered\_success}}{100 - \text{initial\_success}}$

### 5.2 Context & Tool Efficiency
- **`Semantic Context Efficiency`**: $\frac{\text{semantic\_context\_tokens}}{\text{total\_context\_tokens}}$
- **`Wrong File Edits`**: Count of file edits touching files outside the dependency graph.
- **`Regression Rate`**: Count of previously passing test vectors broken by patches.
